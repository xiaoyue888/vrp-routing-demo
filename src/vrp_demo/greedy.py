"""Transparent greedy feasible nearest-neighbour baseline."""

from __future__ import annotations

from time import perf_counter

from .distance import build_matrices
from .models import Customer, RouteResult, Scenario, StopResult
from .result_utils import assemble_solution


def solve_greedy(
    scenario: Scenario,
    matrices: tuple[list[list[int]], list[list[int]]] | None = None,
):
    started = perf_counter()
    distance_matrix, time_matrix = matrices or build_matrices(scenario)
    remaining = {
        customer.customer_id: (index, customer)
        for index, customer in enumerate(scenario.customers, start=1)
    }
    routes: list[RouteResult] = []
    served_ids: list[str] = []

    for vehicle_number in range(1, scenario.fleet.vehicle_count + 1):
        current_index = 0
        current_time = float(scenario.fleet.shift_start)
        current_load = 0
        stops: list[StopResult] = []
        route_distance = 0.0
        route_travel = 0.0

        while remaining:
            candidates: list[tuple[float, str, int, Customer, float, float, float]] = []
            for customer_index, customer in remaining.values():
                if current_load + customer.demand > scenario.fleet.vehicle_capacity:
                    continue
                leg_distance = distance_matrix[current_index][customer_index] / 1_000
                leg_travel = time_matrix[current_index][customer_index]
                arrival = current_time + leg_travel
                service_start = max(arrival, float(customer.window_start))
                departure = service_start + customer.service_minutes
                return_time = time_matrix[customer_index][0]
                if service_start > customer.window_end:
                    continue
                if departure + return_time > scenario.fleet.shift_end:
                    continue
                candidates.append(
                    (
                        leg_distance,
                        customer.customer_id,
                        customer_index,
                        customer,
                        arrival,
                        service_start,
                        departure,
                    )
                )

            if not candidates:
                break

            (
                leg_distance,
                customer_id,
                customer_index,
                customer,
                arrival,
                service_start,
                departure,
            ) = min(candidates)
            leg_travel = time_matrix[current_index][customer_index]
            current_load += customer.demand
            stops.append(
                StopResult(
                    customer_id=customer_id,
                    x_km=customer.x_km,
                    y_km=customer.y_km,
                    arrival_minute=round(arrival, 2),
                    service_start_minute=round(service_start, 2),
                    departure_minute=round(departure, 2),
                    demand=customer.demand,
                    load_after=current_load,
                )
            )
            route_distance += leg_distance
            route_travel += leg_travel
            current_index = customer_index
            current_time = departure
            served_ids.append(customer_id)
            del remaining[customer_id]

        if stops:
            return_distance = distance_matrix[current_index][0] / 1_000
            return_travel = time_matrix[current_index][0]
            route_distance += return_distance
            route_travel += return_travel
            routes.append(
                RouteResult(
                    vehicle_id=f"V{vehicle_number}",
                    stops=stops,
                    distance_km=round(route_distance, 3),
                    travel_minutes=round(route_travel, 2),
                    duration_minutes=round(current_time + return_travel - scenario.fleet.shift_start, 2),
                    delivered_demand=current_load,
                    capacity_utilization=current_load / scenario.fleet.vehicle_capacity,
                )
            )

    runtime_ms = (perf_counter() - started) * 1_000
    return assemble_solution(
        method="greedy",
        scenario=scenario,
        routes=routes,
        served_ids=served_ids,
        runtime_ms=runtime_ms,
        solver_metadata={"algorithm": "Deterministic constructive heuristic"},
        time_matrix=time_matrix,
    )
