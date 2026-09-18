"""Run the built-in scenario and emit UI-ready JSON."""

from __future__ import annotations

import argparse

from .scenarios import built_in_scenario, random_scenario
from .service import run_comparison


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare greedy and OR-Tools CVRPTW routes.")
    parser.add_argument("--random", action="store_true", help="Use a generated scenario.")
    parser.add_argument("--seed", type=int, default=20260915)
    parser.add_argument("--customers", type=int, default=20)
    parser.add_argument("--time-limit", type=int, default=2)
    args = parser.parse_args()
    scenario = (
        random_scenario(seed=args.seed, customer_count=args.customers)
        if args.random
        else built_in_scenario()
    )
    result = run_comparison(scenario, solver_time_limit_seconds=args.time_limit)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
