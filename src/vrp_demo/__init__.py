"""Computational core for the vehicle-routing portfolio demo."""

from .models import ComparisonResult, Customer, Fleet, Point, Scenario, SolutionResult
from .scenarios import built_in_scenario, random_scenario
from .service import run_comparison

__all__ = [
    "ComparisonResult",
    "Customer",
    "Fleet",
    "Point",
    "Scenario",
    "SolutionResult",
    "built_in_scenario",
    "random_scenario",
    "run_comparison",
]
