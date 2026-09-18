"""Synthetic, privacy-safe scenario fixtures and generators."""

from __future__ import annotations

import random

from .models import Customer, Fleet, Point, Scenario


def built_in_scenario() -> Scenario:
    """A small deterministic scenario suitable for an immediate first run."""

    rows = [
        ("C01", 1.5, 3.0, 3, 8, 15, 100),
        ("C02", 3.0, 4.5, 4, 10, 35, 135),
        ("C03", 5.5, 4.0, 2, 8, 55, 155),
        ("C04", 6.5, 1.5, 5, 12, 80, 210),
        ("C05", -2.0, 4.0, 3, 8, 20, 115),
        ("C06", -4.5, 5.0, 4, 10, 45, 155),
        ("C07", -6.0, 1.0, 2, 8, 70, 195),
        ("C08", -3.0, -3.5, 5, 12, 95, 235),
        ("C09", 1.0, -5.5, 3, 8, 100, 245),
        ("C10", 4.5, -3.0, 4, 10, 120, 270),
        ("C11", 7.0, -1.0, 2, 8, 135, 290),
        ("C12", 0.0, 7.0, 3, 10, 75, 205),
    ]
    customers = [
        Customer(
            customer_id=customer_id,
            x_km=x,
            y_km=y,
            demand=demand,
            service_minutes=service,
            window_start=window_start,
            window_end=window_end,
        )
        for customer_id, x, y, demand, service, window_start, window_end in rows
    ]
    return Scenario(
        name="Built-in synthetic city",
        depot=Point(x_km=0, y_km=0),
        customers=customers,
        fleet=Fleet(vehicle_count=3, vehicle_capacity=14, shift_start=0, shift_end=360),
        average_speed_kmph=30,
        seed=20260915,
    )


def random_scenario(
    *,
    seed: int,
    customer_count: int = 20,
    vehicle_count: int = 4,
    vehicle_capacity: int = 20,
) -> Scenario:
    if not 5 <= customer_count <= 100:
        raise ValueError("customer_count must be between 5 and 100")
    rng = random.Random(seed)
    customers: list[Customer] = []
    for index in range(1, customer_count + 1):
        window_start = rng.randrange(0, 241, 15)
        window_width = rng.choice([90, 120, 150])
        customers.append(
            Customer(
                customer_id=f"C{index:03d}",
                x_km=round(rng.uniform(-10, 10), 3),
                y_km=round(rng.uniform(-10, 10), 3),
                demand=rng.randint(1, 6),
                service_minutes=rng.choice([5, 10, 15]),
                window_start=window_start,
                window_end=min(360, window_start + window_width),
            )
        )
    return Scenario(
        name=f"Random synthetic scenario (seed {seed})",
        depot=Point(x_km=0, y_km=0),
        customers=customers,
        fleet=Fleet(
            vehicle_count=vehicle_count,
            vehicle_capacity=vehicle_capacity,
            shift_start=0,
            shift_end=360,
        ),
        average_speed_kmph=30,
        seed=seed,
    )
