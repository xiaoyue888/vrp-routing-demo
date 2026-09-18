"""Common result aggregation and conservative unserved-order explanations."""

from __future__ import annotations

from .distance import euclidean_km, travel_minutes
from .models import Customer, RouteResult, Scenario, SolutionResult


def explain_unserved(
    customer: Customer,
    scenario: Scenario,
    method: str,
    time_matrix: list[list[int]] | None = None,
) -> str:
    if customer.demand > scenario.fleet.vehicle_capacity:
        return "Demand exceeds every vehicle's capacity."
    if time_matrix is None:
        outbound = travel_minutes(euclidean_km(scenario.depot, customer), scenario.average_speed_kmph)
        return_trip = travel_minutes(euclidean_km(customer, scenario.depot), scenario.average_speed_kmph)
    else:
        customer_index = scenario.customers.index(customer) + 1
        outbound = time_matrix[0][customer_index]
        return_trip = time_matrix[customer_index][0]
    earliest_service = max(scenario.fleet.shift_start + outbound, customer.window_start)
    if earliest_service > customer.window_end:
        return "The customer cannot be reached before its time window closes."
    if earliest_service + customer.service_minutes + return_trip > scenario.fleet.shift_end:
        return "The visit cannot be completed with a return to the depot before shift end."
    if method == "greedy":
        return "Not selected by the greedy construction within the available fleet and constraints."
    return "Dropped because the available fleet cannot serve this order within all active constraints."


def assemble_solution(
    *,
    method: str,
    scenario: Scenario,
    routes: list[RouteResult],
    served_ids: list[str],
    runtime_ms: float,
    validation_messages: list[str] | None = None,
    solver_metadata: dict[str, str | float | bool] | None = None,
    time_matrix: list[list[int]] | None = None,
) -> SolutionResult:
    served = set(served_ids)
    unserved = {
        customer.customer_id: explain_unserved(customer, scenario, method, time_matrix)
        for customer in scenario.customers
        if customer.customer_id not in served
    }
    if not routes and not served:
        status = "no_solution"
    elif unserved:
        status = "partial"
    else:
        status = "complete"
    used_routes = [route for route in routes if route.stops]
    utilization = (
        sum(route.capacity_utilization for route in used_routes) / len(used_routes)
        if used_routes
        else 0.0
    )
    return SolutionResult(
        method=method,
        status=status,
        routes=used_routes,
        served_customer_ids=sorted(served),
        unserved_customers=unserved,
        total_distance_km=round(sum(route.distance_km for route in used_routes), 3),
        total_travel_minutes=round(sum(route.travel_minutes for route in used_routes), 2),
        vehicles_used=len(used_routes),
        served_orders=len(served),
        unserved_orders=len(unserved),
        average_capacity_utilization=round(utilization, 4),
        runtime_ms=round(runtime_ms, 3),
        validation_messages=validation_messages or [],
        solver_metadata=solver_metadata or {},
    )
