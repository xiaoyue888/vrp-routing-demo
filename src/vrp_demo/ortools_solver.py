"""Focused single-depot CVRPTW model implemented with OR-Tools."""

from __future__ import annotations

from time import perf_counter

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .distance import build_matrices
from .models import RouteResult, Scenario, StopResult
from .result_utils import assemble_solution


def solve_ortools(
    scenario: Scenario,
    time_limit_seconds: int = 2,
    matrices: tuple[list[list[int]], list[list[int]]] | None = None,
):
    if not 1 <= time_limit_seconds <= 30:
        raise ValueError("time_limit_seconds must be between 1 and 30")

    started = perf_counter()
    distance_matrix, time_matrix = matrices or build_matrices(scenario)
    node_count = len(scenario.customers) + 1
    manager = pywrapcp.RoutingIndexManager(node_count, scenario.fleet.vehicle_count, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index: int, to_index: int) -> int:
        return distance_matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    distance_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(distance_callback_index)

    demands = [0, *(customer.demand for customer in scenario.customers)]

    def demand_callback(from_index: int) -> int:
        return demands[manager.IndexToNode(from_index)]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        [scenario.fleet.vehicle_capacity] * scenario.fleet.vehicle_count,
        True,
        "Capacity",
    )

    service_minutes = [0, *(customer.service_minutes for customer in scenario.customers)]

    def time_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return service_minutes[from_node] + time_matrix[from_node][to_node]

    time_callback_index = routing.RegisterTransitCallback(time_callback)
    horizon = scenario.fleet.shift_end
    routing.AddDimension(time_callback_index, horizon, horizon, False, "Time")
    time_dimension = routing.GetDimensionOrDie("Time")

    forced_unserved_nodes: set[int] = set()
    for node, customer in enumerate(scenario.customers, start=1):
        window_start = max(customer.window_start, scenario.fleet.shift_start)
        window_end = min(customer.window_end, scenario.fleet.shift_end)
        if window_start > window_end:
            forced_unserved_nodes.add(node)
            continue
        time_dimension.CumulVar(manager.NodeToIndex(node)).SetRange(window_start, window_end)

    for vehicle_id in range(scenario.fleet.vehicle_count):
        start_index = routing.Start(vehicle_id)
        end_index = routing.End(vehicle_id)
        time_dimension.CumulVar(start_index).SetRange(
            scenario.fleet.shift_start, scenario.fleet.shift_start
        )
        time_dimension.CumulVar(end_index).SetRange(
            scenario.fleet.shift_start, scenario.fleet.shift_end
        )
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(end_index))

    max_edge = max(max(row) for row in distance_matrix)
    drop_penalty = max(1_000_000, max_edge * (node_count + 2) * 100)
    for node in range(1, node_count):
        node_index = manager.NodeToIndex(node)
        routing.AddDisjunction([node_index], drop_penalty)
        if node in forced_unserved_nodes:
            routing.solver().Add(routing.ActiveVar(node_index) == 0)

    parameters = pywrapcp.DefaultRoutingSearchParameters()
    parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )
    parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    parameters.time_limit.FromSeconds(time_limit_seconds)
    parameters.log_search = False

    assignment = routing.SolveWithParameters(parameters)
    runtime_ms = (perf_counter() - started) * 1_000
    solver_metadata = {
        "algorithm": "OR-Tools guided local search",
        "search_budget_seconds": float(time_limit_seconds),
        "search_limit_reached": runtime_ms >= time_limit_seconds * 950,
    }
    if assignment is None:
        return assemble_solution(
            method="ortools",
            scenario=scenario,
            routes=[],
            served_ids=[],
            runtime_ms=runtime_ms,
            validation_messages=["OR-Tools did not return an assignment within the configured limit."],
            solver_metadata=solver_metadata,
            time_matrix=time_matrix,
        )

    routes: list[RouteResult] = []
    served_ids: list[str] = []
    for vehicle_number in range(scenario.fleet.vehicle_count):
        index = routing.Start(vehicle_number)
        start_time = assignment.Value(time_dimension.CumulVar(index))
        stops: list[StopResult] = []
        distance_metres = 0
        travel_time = 0
        load = 0

        while not routing.IsEnd(index):
            current_service_start = assignment.Value(time_dimension.CumulVar(index))
            next_index = assignment.Value(routing.NextVar(index))
            from_node = manager.IndexToNode(index)
            to_node = manager.IndexToNode(next_index)
            actual_arrival = (
                current_service_start + service_minutes[from_node] + time_matrix[from_node][to_node]
            )
            distance_metres += distance_matrix[from_node][to_node]
            travel_time += time_matrix[from_node][to_node]
            index = next_index
            node = manager.IndexToNode(index)
            if node == 0:
                continue
            customer = scenario.customers[node - 1]
            service_start = assignment.Value(time_dimension.CumulVar(index))
            load += customer.demand
            served_ids.append(customer.customer_id)
            stops.append(
                StopResult(
                    customer_id=customer.customer_id,
                    x_km=customer.x_km,
                    y_km=customer.y_km,
                    arrival_minute=actual_arrival,
                    service_start_minute=service_start,
                    departure_minute=service_start + customer.service_minutes,
                    demand=customer.demand,
                    load_after=load,
                )
            )

        if stops:
            end_time = assignment.Value(time_dimension.CumulVar(index))
            routes.append(
                RouteResult(
                    vehicle_id=f"V{vehicle_number + 1}",
                    stops=stops,
                    distance_km=round(distance_metres / 1_000, 3),
                    travel_minutes=float(travel_time),
                    duration_minutes=float(end_time - start_time),
                    delivered_demand=load,
                    capacity_utilization=load / scenario.fleet.vehicle_capacity,
                )
            )

    return assemble_solution(
        method="ortools",
        scenario=scenario,
        routes=routes,
        served_ids=served_ids,
        runtime_ms=runtime_ms,
        solver_metadata=solver_metadata,
        time_matrix=time_matrix,
    )
