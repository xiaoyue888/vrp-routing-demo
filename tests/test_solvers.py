from vrp_demo.greedy import solve_greedy
from vrp_demo.models import Customer, Fleet, Point, Scenario
from vrp_demo.ortools_solver import solve_ortools
from vrp_demo.scenarios import built_in_scenario
from vrp_demo.service import run_comparison
from vrp_demo.validation import validate_solution


def test_built_in_comparison_is_feasible_and_valid():
    scenario = built_in_scenario()
    result = run_comparison(scenario, solver_time_limit_seconds=1)
    assert result.baseline.status == "complete"
    assert result.optimized.status == "complete"
    assert result.baseline.served_orders == len(scenario.customers)
    assert result.optimized.served_orders == len(scenario.customers)
    assert result.baseline.validation_messages == []
    assert result.optimized.validation_messages == []
    assert result.optimized.total_distance_km <= result.baseline.total_distance_km


def test_capacity_infeasibility_is_reported_by_both_methods():
    scenario = Scenario(
        name="Oversized order",
        depot=Point(x_km=0, y_km=0),
        customers=[
            Customer(
                customer_id="TOO_BIG",
                x_km=1,
                y_km=0,
                demand=11,
                service_minutes=5,
                window_start=0,
                window_end=100,
            )
        ],
        fleet=Fleet(vehicle_count=1, vehicle_capacity=10, shift_start=0, shift_end=120),
        average_speed_kmph=30,
        seed=1,
    )
    baseline = solve_greedy(scenario)
    optimized = solve_ortools(scenario, time_limit_seconds=1)
    for result in (baseline, optimized):
        assert result.status == "no_solution"
        assert result.unserved_orders == 1
        assert "exceeds" in result.unserved_customers["TOO_BIG"]
        assert validate_solution(scenario, result) == []


def test_tight_time_window_is_reported():
    scenario = Scenario(
        name="Unreachable order",
        depot=Point(x_km=0, y_km=0),
        customers=[
            Customer(
                customer_id="FAR",
                x_km=100,
                y_km=0,
                demand=1,
                service_minutes=5,
                window_start=0,
                window_end=10,
            )
        ],
        fleet=Fleet(vehicle_count=1, vehicle_capacity=10, shift_start=0, shift_end=300),
        average_speed_kmph=30,
        seed=1,
    )
    result = solve_ortools(scenario, time_limit_seconds=1)
    assert result.status == "no_solution"
    assert "cannot be reached" in result.unserved_customers["FAR"]


def test_partial_service_is_not_presented_as_complete():
    scenario = Scenario(
        name="Mixed feasibility",
        depot=Point(x_km=0, y_km=0),
        customers=[
            Customer(
                customer_id="NEAR",
                x_km=1,
                y_km=0,
                demand=2,
                service_minutes=5,
                window_start=0,
                window_end=100,
            ),
            Customer(
                customer_id="BIG",
                x_km=2,
                y_km=0,
                demand=20,
                service_minutes=5,
                window_start=0,
                window_end=100,
            ),
        ],
        fleet=Fleet(vehicle_count=1, vehicle_capacity=10, shift_start=0, shift_end=120),
        average_speed_kmph=30,
        seed=1,
    )
    result = solve_ortools(scenario, time_limit_seconds=1)
    assert result.status == "partial"
    assert result.served_customer_ids == ["NEAR"]
    assert result.unserved_orders == 1


def test_customer_window_outside_shift_is_dropped_without_solver_failure():
    scenario = Scenario(
        name="Window outside shift",
        depot=Point(x_km=0, y_km=0),
        customers=[
            Customer(
                customer_id="LATE",
                x_km=1,
                y_km=0,
                demand=1,
                service_minutes=5,
                window_start=240,
                window_end=300,
            )
        ],
        fleet=Fleet(vehicle_count=1, vehicle_capacity=10, shift_start=0, shift_end=180),
        average_speed_kmph=30,
        seed=1,
    )
    result = solve_ortools(scenario, time_limit_seconds=1)
    assert result.status == "no_solution"
    assert result.unserved_orders == 1
    assert validate_solution(scenario, result) == []
