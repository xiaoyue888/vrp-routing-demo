"""Application-level entrypoint used by the CLI and future UI."""

from __future__ import annotations

from .greedy import solve_greedy
from .models import ComparisonResult, Scenario
from .ortools_solver import solve_ortools
from .validation import validate_solution


def run_comparison(
    scenario: Scenario,
    solver_time_limit_seconds: int = 2,
    matrices: tuple[list[list[int]], list[list[int]]] | None = None,
) -> ComparisonResult:
    baseline = solve_greedy(scenario, matrices)
    optimized = solve_ortools(scenario, solver_time_limit_seconds, matrices)
    baseline.validation_messages.extend(validate_solution(scenario, baseline, matrices))
    optimized.validation_messages.extend(validate_solution(scenario, optimized, matrices))
    return ComparisonResult(scenario=scenario, baseline=baseline, optimized=optimized)
