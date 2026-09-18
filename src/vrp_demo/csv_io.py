"""Strict CSV parsing for synthetic customer scenarios."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from pydantic import ValidationError

from .models import Customer

CSV_COLUMNS = (
    "customer_id",
    "x_km",
    "y_km",
    "demand",
    "service_minutes",
    "window_start",
    "window_end",
)


class CSVValidationError(ValueError):
    pass


def customers_from_csv_text(csv_text: str) -> list[Customer]:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if reader.fieldnames is None:
        raise CSVValidationError("CSV is empty or has no header row.")
    actual = tuple(reader.fieldnames)
    if actual != CSV_COLUMNS:
        raise CSVValidationError("CSV columns do not match the required schema. Download the example and keep its header row unchanged.")

    customers: list[Customer] = []
    errors: list[str] = []
    for row_number, row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue
        try:
            customers.append(Customer.model_validate(row))
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            )
            errors.append(f"row {row_number}: {details}")
    if not customers and not errors:
        errors.append("CSV contains no customer rows.")
    if len(customers) > 100:
        errors.append("CSV supports at most 100 customers.")
    ids = [customer.customer_id for customer in customers]
    duplicates = sorted({customer_id for customer_id in ids if ids.count(customer_id) > 1})
    if duplicates:
        errors.append(f"duplicate customer_id values: {', '.join(duplicates)}")
    if errors:
        raise CSVValidationError(" | ".join(errors))
    return customers


def load_customers_csv(path: str | Path) -> list[Customer]:
    return customers_from_csv_text(Path(path).read_text(encoding="utf-8"))
