"""Independent checks for routes returned by either algorithm."""

from __future__ import annotations

from .distance import build_matrices
from .models import Scenario, SolutionResult


def validate_solution(
    scenario: Scenario,
    solution: SolutionResult,
    matrices: tuple[list[list[int]], list[list[int]]] | None = None,
) -> list[str]:
    errors: list[str] = []
    customers = {customer.customer_id: customer for customer in scenario.customers}
    node_by_id = {
        customer.customer_id: index
        for index, customer in enumerate(scenario.customers, start=1)
    }
    _, time_matrix = matrices or build_matrices(scenario)
    seen: set[str] = set()

    for route in solution.routes:
        load = 0
        current_index = 0
        time = float(scenario.fleet.shift_start)
        for stop in route.stops:
            if stop.customer_id in seen:
                errors.append(f"{stop.customer_id}: served more than once")
                continue
            seen.add(stop.customer_id)
            customer = customers.get(stop.customer_id)
            if customer is None:
                errors.append(f"{stop.customer_id}: unknown customer")
                continue
            customer_index = node_by_id[customer.customer_id]
            time += time_matrix[current_index][customer_index]
            service_start = max(time, customer.window_start)
            if service_start > customer.window_end + 1e-6:
                errors.append(f"{customer.customer_id}: service starts after time window")
            time = service_start + customer.service_minutes
            load += customer.demand
            if load > scenario.fleet.vehicle_capacity:
                errors.append(f"{route.vehicle_id}: vehicle capacity exceeded")
            current_index = customer_index
        time += time_matrix[current_index][0]
        if time > scenario.fleet.shift_end + 1e-6:
            errors.append(f"{route.vehicle_id}: returns after shift end")

    if seen != set(solution.served_customer_ids):
        errors.append("served_customer_ids does not match route contents")
    expected_unserved = set(customers) - seen
    if expected_unserved != set(solution.unserved_customers):
        errors.append("unserved_customers does not match route contents")
    return errors
