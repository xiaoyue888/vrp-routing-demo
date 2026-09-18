"""Validated input and output contracts shared by both solvers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Point(StrictModel):
    x_km: float = Field(ge=-1_000, le=1_000)
    y_km: float = Field(ge=-1_000, le=1_000)


class Customer(Point):
    customer_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    demand: int = Field(gt=0, le=1_000_000)
    service_minutes: int = Field(ge=0, le=1_440)
    window_start: int = Field(ge=0, le=10_080)
    window_end: int = Field(gt=0, le=10_080)

    @model_validator(mode="after")
    def window_is_ordered(self) -> "Customer":
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be greater than window_start")
        return self


class Fleet(StrictModel):
    vehicle_count: int = Field(gt=0, le=50)
    vehicle_capacity: int = Field(gt=0, le=1_000_000)
    shift_start: int = Field(ge=0, le=10_080)
    shift_end: int = Field(gt=0, le=10_080)

    @model_validator(mode="after")
    def shift_is_ordered(self) -> "Fleet":
        if self.shift_end <= self.shift_start:
            raise ValueError("shift_end must be greater than shift_start")
        return self


class Scenario(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    depot: Point
    customers: list[Customer] = Field(min_length=1, max_length=100)
    fleet: Fleet
    average_speed_kmph: float = Field(gt=0, le=200)
    seed: int = Field(ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def customer_ids_are_unique(self) -> "Scenario":
        ids = [customer.customer_id for customer in self.customers]
        duplicates = sorted({customer_id for customer_id in ids if ids.count(customer_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate customer_id values: {', '.join(duplicates)}")
        return self


class StopResult(StrictModel):
    customer_id: str
    x_km: float
    y_km: float
    arrival_minute: float
    service_start_minute: float
    departure_minute: float
    demand: int
    load_after: int


class RouteResult(StrictModel):
    vehicle_id: str
    stops: list[StopResult]
    distance_km: float = Field(ge=0)
    travel_minutes: float = Field(ge=0)
    duration_minutes: float = Field(ge=0)
    delivered_demand: int = Field(ge=0)
    capacity_utilization: float = Field(ge=0, le=1)


class SolutionResult(StrictModel):
    method: Literal["greedy", "ortools"]
    status: Literal["complete", "partial", "no_solution"]
    routes: list[RouteResult]
    served_customer_ids: list[str]
    unserved_customers: dict[str, str]
    total_distance_km: float = Field(ge=0)
    total_travel_minutes: float = Field(ge=0)
    vehicles_used: int = Field(ge=0)
    served_orders: int = Field(ge=0)
    unserved_orders: int = Field(ge=0)
    average_capacity_utilization: float = Field(ge=0, le=1)
    runtime_ms: float = Field(ge=0)
    validation_messages: list[str] = Field(default_factory=list)
    solver_metadata: dict[str, str | float | bool] = Field(default_factory=dict)


class ComparisonResult(StrictModel):
    scenario: Scenario
    baseline: SolutionResult
    optimized: SolutionResult
