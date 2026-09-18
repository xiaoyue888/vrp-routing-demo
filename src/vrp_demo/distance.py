"""Deterministic geometry and travel-time helpers."""

from __future__ import annotations

import math

from .models import Point, Scenario


def euclidean_km(a: Point, b: Point) -> float:
    return math.hypot(a.x_km - b.x_km, a.y_km - b.y_km)


def travel_minutes(distance_km: float, speed_kmph: float) -> float:
    return distance_km / speed_kmph * 60.0


def build_matrices(scenario: Scenario) -> tuple[list[list[int]], list[list[int]]]:
    """Return integer metre and minute matrices for OR-Tools.

    Travel minutes are rounded up so a route is never made artificially feasible
    through downward rounding.
    """

    points: list[Point] = [scenario.depot, *scenario.customers]
    distance_matrix: list[list[int]] = []
    time_matrix: list[list[int]] = []
    for source in points:
        distance_row: list[int] = []
        time_row: list[int] = []
        for target in points:
            distance = euclidean_km(source, target)
            distance_row.append(round(distance * 1_000))
            time_row.append(math.ceil(travel_minutes(distance, scenario.average_speed_kmph)))
        distance_matrix.append(distance_row)
        time_matrix.append(time_row)
    return distance_matrix, time_matrix
