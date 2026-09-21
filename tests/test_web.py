import pytest
from pydantic import ValidationError

from vrp_demo.csv_io import CSVValidationError
from vrp_demo.road_network import RoadNetworkError, osrm_base_url
from vrp_demo.web import (
    DEFAULT_CASE_STUDY_URL,
    UI_DIRECTORY,
    RunRequest,
    _friendly_error,
    case_study_url,
    deployment_host,
    deployment_port,
    execute_request,
    scenario_from_request,
    scenario_summary,
)


def test_ui_directory_contains_deployable_entrypoint():
    assert UI_DIRECTORY.is_dir()
    assert (UI_DIRECTORY / "app.html").is_file()
    assert (UI_DIRECTORY / "app.js").is_file()
    assert (UI_DIRECTORY / "app.css").is_file()


def test_execute_built_in_request_returns_comparison_contract():
    payload = {
        "source": "built_in",
        "customer_count": 12,
        "vehicle_count": 3,
        "vehicle_capacity": 14,
        "average_speed_kmph": 30,
        "shift_minutes": 360,
        "seed": 20260915,
        "solver_time_limit_seconds": 1,
        "csv_text": None,
        "routing_mode": "euclidean",
    }
    result = execute_request(payload)
    assert set(result) == {"scenario", "baseline", "optimized", "map_data"}
    assert result["map_data"]["mode"] == "euclidean"
    assert result["baseline"]["served_orders"] == 12
    assert result["optimized"]["served_orders"] == 12
    assert result["baseline"]["total_distance_km"] == pytest.approx(74.494)
    assert result["optimized"]["total_distance_km"] == pytest.approx(64.402)


def test_public_request_defaults_to_offline_distance():
    assert RunRequest().routing_mode == "euclidean"


def test_road_routing_requires_explicit_server_opt_in(monkeypatch):
    monkeypatch.delenv("VRP_ENABLE_ROAD_ROUTING", raising=False)
    with pytest.raises(ValueError, match="not enabled"):
        execute_request({"routing_mode": "road"})


def test_road_routing_requires_explicit_provider_url(monkeypatch):
    monkeypatch.delenv("VRP_OSRM_URL", raising=False)
    with pytest.raises(RoadNetworkError, match="requires VRP_OSRM_URL"):
        osrm_base_url()


@pytest.mark.parametrize("value", ["", "router.example", "ftp://router.example"])
def test_invalid_road_provider_url_is_rejected(monkeypatch, value):
    monkeypatch.setenv("VRP_OSRM_URL", value)
    with pytest.raises(RoadNetworkError, match=r"HTTP\(S\)"):
        osrm_base_url()


def test_road_provider_url_accepts_http_and_removes_trailing_slash(monkeypatch):
    monkeypatch.setenv("VRP_OSRM_URL", "https://router.example/")
    assert osrm_base_url() == "https://router.example"


def test_deployment_defaults_stay_local(monkeypatch):
    monkeypatch.delenv("VRP_HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    assert deployment_host() == "127.0.0.1"
    assert deployment_port() == 4190


def test_deployment_reads_cloud_host_and_port(monkeypatch):
    monkeypatch.setenv("VRP_HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "10000")
    assert deployment_host() == "0.0.0.0"
    assert deployment_port() == 10000


@pytest.mark.parametrize("value", ["abc", "0", "65536"])
def test_invalid_deployment_port_is_rejected(monkeypatch, value):
    monkeypatch.setenv("PORT", value)
    with pytest.raises(ValueError, match="between 1 and 65535"):
        deployment_port()


def test_case_study_url_accepts_https_and_rejects_unsafe_values(monkeypatch):
    monkeypatch.setenv("VRP_CASE_STUDY_URL", "https://portfolio.example/vehicle-routing.html")
    assert case_study_url() == "https://portfolio.example/vehicle-routing.html"
    monkeypatch.setenv("VRP_CASE_STUDY_URL", "javascript:alert(1)")
    assert case_study_url() == DEFAULT_CASE_STUDY_URL


def test_csv_source_requires_content():
    request = RunRequest(source="csv")
    with pytest.raises(CSVValidationError, match="Choose a CSV"):
        scenario_from_request(request)


def test_request_size_limits_are_validated():
    with pytest.raises(ValidationError):
        RunRequest(source="generate", customer_count=101)


def test_public_solver_limit_matches_ui_limit():
    with pytest.raises(ValidationError) as caught:
        RunRequest(solver_time_limit_seconds=30)
    assert "no more than 10" in _friendly_error(caught.value)


def test_scenario_summary_uses_exact_generated_demand():
    payload = {
        "source": "generate",
        "customer_count": 20,
        "vehicle_count": 2,
        "vehicle_capacity": 10,
        "average_speed_kmph": 30,
        "shift_minutes": 360,
        "seed": 42,
        "solver_time_limit_seconds": 1,
        "csv_text": None,
    }
    summary = scenario_summary(payload)
    assert summary["customer_count"] == 20
    assert summary["minimum_vehicles_by_capacity"] > 2
    assert summary["max_orders_by_capacity"] < 20
