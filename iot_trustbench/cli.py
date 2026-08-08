"""Command-line interface for IoT-TrustBench.

Provides a ``iot-trustbench`` console command to run the API server
and to run quick batch evaluations from the terminal without needing
to construct HTTP requests.
"""

import argparse
import sys

from iot_trustbench.core.sensor_simulator import generate_reading
from iot_trustbench.core.data_validator import validate_reading
from iot_trustbench.core.safety_engine import classify_event

ALL_SCENARIO_TYPES = [
    "normal",
    "emergency",
    "sensor_fault",
    "spoofing",
    "offline",
    "uncertain",
]


def _run_batch(scenario_type: str, count: int) -> None:
    """Run ``count`` simulated readings of one type and report accuracy."""
    from iot_trustbench.api.app import ALL_SCENARIO_TYPES as VALID_TYPES

    if scenario_type not in VALID_TYPES:
        print(
            f"error: unknown scenario type '{scenario_type}'; "
            f"choose from {', '.join(VALID_TYPES)}",
            file=sys.stderr,
        )
        sys.exit(2)

    correct = 0
    examples: dict = {}
    for _ in range(count):
        reading = generate_reading(scenario_type)
        validation = validate_reading(reading)
        decision = classify_event(reading, validation)
        ok = decision.classification.value == scenario_type
        correct += int(ok)
        examples.setdefault(decision.classification.value, 0)
        examples[decision.classification.value] += 1

    accuracy = correct / count if count else 0.0
    print(f"scenario_type: {scenario_type}")
    print(f"runs: {count}")
    print(f"correct: {correct}")
    print(f"accuracy: {accuracy:.3f}")
    print("distribution: " + ", ".join(
        f"{k}={v}" for k, v in sorted(examples.items())
    ))


def _run_all(count_per_type: int) -> None:
    """Run batch evaluation across all six scenario types."""
    print(f"batch evaluation over {count_per_type} runs per type\n")
    for scenario_type in ALL_SCENARIO_TYPES:
        _run_batch(scenario_type, count_per_type)
        print()


def main(argv=None) -> int:
    """CLI entry point. Returns process exit code."""
    parser = argparse.ArgumentParser(
        prog="iot-trustbench",
        description="IoT-TrustBench: deterministic IoT safety evaluation",
    )
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="run the FastAPI server (uvicorn)")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", help="enable auto-reload")

    batch = sub.add_parser("batch", help="run batch evaluation on simulated data")
    batch.add_argument(
        "scenario_type",
        nargs="?",
        help="one of normal, emergency, sensor_fault, spoofing, offline, uncertain",
    )
    batch.add_argument(
        "--count",
        type=int,
        default=20,
        help="number of runs per type (default: 20)",
    )

    args = parser.parse_args(argv)

    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "iot_trustbench.api.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0

    if args.command == "batch":
        if args.count <= 0:
            print("error: --count must be positive", file=sys.stderr)
            return 2
        if args.scenario_type:
            _run_batch(args.scenario_type, args.count)
        else:
            _run_all(args.count)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
