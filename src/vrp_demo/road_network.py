"""Road-network travel data for the synthetic portfolio scenarios.

Coordinates are projected into central Singapore and sent to an OSRM-compatible
service only when road mode is explicitly enabled. The module is provider-neutral,
and the endpoint must be configured through ``VRP_OSRM_URL``.
"""

from __future__ import annotations

import json
import math
import os
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .models import Scenario, SolutionResult

MAP_CENTER = (1.3521, 103.8198)
TABLE_CHUNK_SIZE = 40
_CACHE_LOCK = threading.Lock()
_CACHE: OrderedDict[str, "RoadNetworkData"] = OrderedDict()


class RoadNetworkError(RuntimeError):
    """Raised when the routing provider cannot return a complete road matrix."""


@dataclass(frozen=True)
class RoadNetworkData:
    distance_matrix: list[list[int]]
    time_matrix: list[list[int]]
    coordinates: list[tuple[float, float]]  # (latitude, longitude), snapped to roads
    provider_url: str

    @property
    def matrices(self) -> tuple[list[list[int]], list[list[int]]]:
        return self.distance_matrix, self.time_matrix


def osrm_base_url() -> str:
    """Return an explicitly configured HTTP(S) OSRM-compatible endpoint."""

    value = os.environ.get("VRP_OSRM_URL", "").strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RoadNetworkError(
            "Road routing requires VRP_OSRM_URL to point to an HTTP(S) "
            "OSRM-compatible service."
        )
    return value


def scenario_coordinates(scenario: Scenario) -> list[tuple[float, float]]:
    """Map local synthetic kilometre offsets onto a real, road-dense city area."""

    latitude, longitude = MAP_CENTER
    longitude_km = 111.32 * math.cos(math.radians(latitude))
    return [
        (latitude + point.y_km / 110.574, longitude + point.x_km / longitude_km)
        for point in [scenario.depot, *scenario.customers]
    ]


def road_network_data(scenario: Scenario) -> RoadNetworkData:
    coordinates = scenario_coordinates(scenario)
    base_url = osrm_base_url()
    cache_key = base_url + "|" + "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in coordinates)
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            _CACHE.move_to_end(cache_key)
            return cached

    distance_matrix, time_matrix, snapped = _table_matrix(base_url, coordinates)
    result = RoadNetworkData(distance_matrix, time_matrix, snapped, base_url)
    with _CACHE_LOCK:
        _CACHE[cache_key] = result
        _CACHE.move_to_end(cache_key)
        while len(_CACHE) > 24:
            _CACHE.popitem(last=False)
    return result


def _table_matrix(
    base_url: str,
    coordinates: list[tuple[float, float]],
) -> tuple[list[list[int]], list[list[int]], list[tuple[float, float]]]:
    count = len(coordinates)
    distances = [[0] * count for _ in range(count)]
    times = [[0] * count for _ in range(count)]
    snapped: list[tuple[float, float] | None] = [None] * count
    chunks = [list(range(start, min(start + TABLE_CHUNK_SIZE, count))) for start in range(0, count, TABLE_CHUNK_SIZE)]

    for sources in chunks:
        for destinations in chunks:
            combined = list(dict.fromkeys([*sources, *destinations]))
            positions = {original: position for position, original in enumerate(combined)}
            coordinate_text = ";".join(
                f"{coordinates[index][1]:.6f},{coordinates[index][0]:.6f}" for index in combined
            )
            query = urlencode(
                {
                    "sources": ";".join(str(positions[index]) for index in sources),
                    "destinations": ";".join(str(positions[index]) for index in destinations),
                    "annotations": "duration,distance",
                }
            )
            payload = _request_json(f"{base_url}/table/v1/driving/{coordinate_text}?{query}")
            if payload.get("code") != "Ok":
                raise RoadNetworkError(payload.get("message") or "The road matrix request was rejected.")
            block_distances = payload.get("distances")
            block_times = payload.get("durations")
            if not block_distances or not block_times:
                raise RoadNetworkError("The road routing service returned an incomplete matrix.")
            for source_offset, source_index in enumerate(sources):
                for destination_offset, destination_index in enumerate(destinations):
                    distance = block_distances[source_offset][destination_offset]
                    duration = block_times[source_offset][destination_offset]
                    if distance is None or duration is None:
                        raise RoadNetworkError("At least one synthetic point is unreachable by road.")
                    distances[source_index][destination_index] = round(distance)
                    times[source_index][destination_index] = math.ceil(duration / 60)
            for item, original_index in zip(payload.get("sources", []), sources):
                location = item.get("location") if item else None
                if location:
                    snapped[original_index] = (location[1], location[0])
            for item, original_index in zip(payload.get("destinations", []), destinations):
                location = item.get("location") if item else None
                if location:
                    snapped[original_index] = (location[1], location[0])

    return distances, times, [value or coordinates[index] for index, value in enumerate(snapped)]


def map_payload(
    scenario: Scenario,
    road_data: RoadNetworkData,
    baseline: SolutionResult,
    optimized: SolutionResult,
) -> dict:
    customer_index = {
        customer.customer_id: index for index, customer in enumerate(scenario.customers, start=1)
    }

    def route_geometry(solution: SolutionResult) -> list[dict]:
        def fetch(route) -> dict:
            indices = [0, *(customer_index[stop.customer_id] for stop in route.stops), 0]
            coordinates = [road_data.coordinates[index] for index in indices]
            return {
                "vehicle_id": route.vehicle_id,
                "geometry": _route_line(road_data.provider_url, coordinates),
            }

        if not solution.routes:
            return []
        with ThreadPoolExecutor(max_workers=min(4, len(solution.routes))) as executor:
            return list(executor.map(fetch, solution.routes))

    return {
        "mode": "road",
        "provider": "OpenStreetMap + OSRM",
        "distance_basis": "Fastest-route road distance and duration",
        "depot": _coordinate_payload(road_data.coordinates[0]),
        "customers": {
            customer.customer_id: _coordinate_payload(road_data.coordinates[index])
            for index, customer in enumerate(scenario.customers, start=1)
        },
        "routes": {
            "baseline": route_geometry(baseline),
            "optimized": route_geometry(optimized),
        },
    }


def _route_line(base_url: str, coordinates: list[tuple[float, float]]) -> list[list[float]]:
    coordinate_text = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in coordinates)
    query = urlencode({"overview": "full", "geometries": "geojson", "steps": "false"})
    payload = _request_json(f"{base_url}/route/v1/driving/{coordinate_text}?{query}")
    routes = payload.get("routes") or []
    if payload.get("code") != "Ok" or not routes:
        raise RoadNetworkError(payload.get("message") or "A road route geometry could not be created.")
    return [[latitude, longitude] for longitude, latitude in routes[0]["geometry"]["coordinates"]]


def _coordinate_payload(coordinate: tuple[float, float]) -> dict[str, float]:
    return {"lat": round(coordinate[0], 6), "lon": round(coordinate[1], 6)}


def _request_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "CVRPTW-Portfolio-Demo/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RoadNetworkError("The road routing service is temporarily unavailable.") from exc
