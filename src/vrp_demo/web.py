"""Small HTTP adapter for the interactive demo.

The adapter deliberately uses the standard library: it serves the static UI and
exposes JSON endpoints without adding a deployment framework or persistence.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import threading
import time
from collections import defaultdict, deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, ValidationError

from .csv_io import CSVValidationError, customers_from_csv_text
from .models import Fleet, Point, Scenario, StrictModel
from .road_network import RoadNetworkError, map_payload, road_network_data
from .scenarios import built_in_scenario, random_scenario
from .service import run_comparison

MAX_REQUEST_BYTES = 1_000_000
PACKAGE_UI_DIRECTORY = Path(__file__).resolve().parent / "ui"
SOURCE_UI_DIRECTORY = Path(__file__).resolve().parents[2] / "ui"
UI_DIRECTORY = (
    PACKAGE_UI_DIRECTORY
    if PACKAGE_UI_DIRECTORY.is_dir()
    else SOURCE_UI_DIRECTORY
)
SOLVER_SLOTS = threading.BoundedSemaphore(2)
RATE_LOCK = threading.Lock()
RATE_EVENTS: dict[str, deque[float]] = defaultdict(deque)
RATE_LIMIT = 12
RATE_WINDOW_SECONDS = 60
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4190
DEFAULT_CASE_STUDY_URL = "http://127.0.0.1:4173/vehicle-routing.html"


class RunRequest(StrictModel):
    source: Literal["built_in", "generate", "csv"] = "built_in"
    customer_count: int = Field(default=20, ge=5, le=100)
    vehicle_count: int = Field(default=3, ge=1, le=50)
    vehicle_capacity: int = Field(default=14, ge=1, le=1_000_000)
    average_speed_kmph: float = Field(default=30, gt=0, le=200)
    shift_minutes: int = Field(default=360, ge=30, le=10_080)
    seed: int = Field(default=20260915, ge=0, le=2_147_483_647)
    solver_time_limit_seconds: int = Field(default=2, ge=1, le=10)
    csv_text: str | None = Field(default=None, max_length=900_000)
    routing_mode: Literal["road", "euclidean"] = "euclidean"


def road_routing_enabled() -> bool:
    """Keep the public demo offline unless road routing is explicitly enabled."""
    return os.environ.get("VRP_ENABLE_ROAD_ROUTING", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def deployment_host() -> str:
    """Use a cloud-safe host only when deployment explicitly configures one."""
    return os.environ.get("VRP_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST


def deployment_port() -> int:
    """Read Render's PORT while retaining the normal local port."""
    raw_value = os.environ.get("PORT")
    if raw_value is None:
        return DEFAULT_PORT
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise ValueError("PORT must be an integer between 1 and 65535.") from exc
    if not 1 <= port <= 65_535:
        raise ValueError("PORT must be an integer between 1 and 65535.")
    return port


def case_study_url() -> str:
    """Return a validated HTTP(S) case-study URL for the Demo back link."""
    value = os.environ.get("VRP_CASE_STUDY_URL", DEFAULT_CASE_STUDY_URL).strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or "\r" in value or "\n" in value:
        return DEFAULT_CASE_STUDY_URL
    return value


def scenario_from_request(request: RunRequest) -> Scenario:
    fleet = Fleet(
        vehicle_count=request.vehicle_count,
        vehicle_capacity=request.vehicle_capacity,
        shift_start=0,
        shift_end=request.shift_minutes,
    )
    if request.source == "built_in":
        scenario = built_in_scenario()
        return scenario.model_copy(
            update={
                "fleet": fleet,
                "average_speed_kmph": request.average_speed_kmph,
                "seed": request.seed,
            }
        )
    if request.source == "generate":
        scenario = random_scenario(
            seed=request.seed,
            customer_count=request.customer_count,
            vehicle_count=request.vehicle_count,
            vehicle_capacity=request.vehicle_capacity,
        )
        return scenario.model_copy(
            update={
                "fleet": fleet,
                "average_speed_kmph": request.average_speed_kmph,
            }
        )
    if not request.csv_text:
        raise CSVValidationError("Choose a CSV file before running the comparison.")
    customers = customers_from_csv_text(request.csv_text)
    return Scenario(
        name="Uploaded coordinate scenario",
        depot=Point(x_km=0, y_km=0),
        customers=customers,
        fleet=fleet,
        average_speed_kmph=request.average_speed_kmph,
        seed=request.seed,
    )


def execute_request(payload: dict) -> dict:
    request = RunRequest.model_validate(payload)
    if request.routing_mode == "road" and not road_routing_enabled():
        raise ValueError("Road routing is not enabled in this deployment.")
    scenario = scenario_from_request(request)
    use_road_network = request.routing_mode == "road" and request.source != "csv"
    road_data = road_network_data(scenario) if use_road_network else None
    result = run_comparison(
        scenario,
        request.solver_time_limit_seconds,
        road_data.matrices if road_data else None,
    )
    response = result.model_dump(mode="json")
    if road_data:
        response["map_data"] = map_payload(
            scenario, road_data, result.baseline, result.optimized
        )
    else:
        response["map_data"] = {
            "mode": "euclidean",
            "provider": "Offline synthetic geometry",
            "distance_basis": "Straight-line distance at configured average speed",
        }
    return response


def scenario_summary(payload: dict) -> dict:
    request = RunRequest.model_validate(payload)
    scenario = scenario_from_request(request)
    total_demand = sum(customer.demand for customer in scenario.customers)
    total_capacity = scenario.fleet.vehicle_count * scenario.fleet.vehicle_capacity
    running_demand = 0
    max_orders = 0
    for demand in sorted(customer.demand for customer in scenario.customers):
        if running_demand + demand > total_capacity:
            break
        running_demand += demand
        max_orders += 1
    return {
        "customer_count": len(scenario.customers),
        "total_demand": total_demand,
        "minimum_vehicles_by_capacity": math.ceil(total_demand / scenario.fleet.vehicle_capacity),
        "max_orders_by_capacity": max_orders,
    }


class DemoRequestHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".csv": "text/csv; charset=utf-8"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIRECTORY), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        path = urlsplit(self.path).path
        if path == "/healthz":
            self._send_json(
                HTTPStatus.OK,
                {"status": "ok", "routing_mode": "euclidean"},
            )
            return
        if path == "/case-study":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", case_study_url())
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path in ("/", "/index.html"):
            self.path = "/app.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path not in ("/api/run", "/api/suggest"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint not found."})
            return
        if self.path == "/api/run" and not _rate_limit_allows(self.client_address[0]):
            self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "Too many requests. Wait a minute and try again."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("Request must be between 1 byte and 1 MB.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object.")
            if self.path == "/api/suggest":
                self._send_json(HTTPStatus.OK, scenario_summary(payload))
                return
            if not SOLVER_SLOTS.acquire(blocking=False):
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Both solver slots are busy. Try again shortly."})
                return
            try:
                result = execute_request(payload)
            finally:
                SOLVER_SLOTS.release()
            self._send_json(HTTPStatus.OK, result)
        except (CSVValidationError, ValidationError, ValueError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": _friendly_error(exc)})
        except RoadNetworkError as exc:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
        except Exception:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "The comparison could not be completed. Check the local server log."},
            )

    def list_directory(self, path):
        self.send_error(HTTPStatus.NOT_FOUND, "Directory listing is disabled")
        return None

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' https://unpkg.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; font-src https://fonts.gstatic.com; img-src 'self' data: https://tile.openstreetmap.org https://unpkg.com; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'",
        )
        super().end_headers()

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        labels = {
            "customer_count": "Customers",
            "vehicle_count": "Vehicles",
            "vehicle_capacity": "Capacity per vehicle",
            "average_speed_kmph": "Average speed",
            "shift_minutes": "Shift length",
            "seed": "Random seed",
            "solver_time_limit_seconds": "Solver time limit",
            "csv_text": "CSV file",
        }
        messages = []
        for error in exc.errors():
            field = str(error["loc"][0]) if error["loc"] else "Input"
            label = labels.get(field, field.replace("_", " ").title())
            error_type = error["type"]
            context = error.get("ctx", {})
            if error_type == "greater_than_equal":
                message = f"must be at least {context.get('ge')}"
            elif error_type == "greater_than":
                message = f"must be greater than {context.get('gt')}"
            elif error_type == "less_than_equal":
                message = f"must be no more than {context.get('le')}"
            elif error_type == "less_than":
                message = f"must be less than {context.get('lt')}"
            elif error_type.endswith("_parsing"):
                message = "must be a valid number"
            else:
                message = "has an invalid value"
            messages.append(f"{label} {message}.")
        return " ".join(messages)
    return str(exc)


def _rate_limit_allows(client_ip: str) -> bool:
    now = time.monotonic()
    with RATE_LOCK:
        events = RATE_EVENTS[client_ip]
        while events and now - events[0] > RATE_WINDOW_SECONDS:
            events.popleft()
        if len(events) >= RATE_LIMIT:
            return False
        events.append(now)
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local CVRPTW interactive demo.")
    try:
        default_port = deployment_port()
    except ValueError as exc:
        parser.error(str(exc))
    parser.add_argument("--host", default=deployment_host())
    parser.add_argument("--port", type=int, default=default_port)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DemoRequestHandler)
    print(f"CVRPTW demo available at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
