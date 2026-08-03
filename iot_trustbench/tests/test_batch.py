import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from iot_trustbench.core.sensor_simulator import generate_reading
from iot_trustbench.core.data_validator import validate_reading
from iot_trustbench.core.safety_engine import classify_event
from iot_trustbench.database.db import init_db, insert_scenario, insert_test_result


SCENARIO_TYPES = [
    "normal",
    "emergency",
    "sensor_fault",
    "spoofing",
    "offline",
    "uncertain",
]


async def run_batch_tests(count_per_type: int = 20) -> list:
    """Run batch tests for all six scenario types."""
    await init_db()
    results: list = []

    for scenario_type in SCENARIO_TYPES:
        for i in range(count_per_type):
            start = time.time()
            reading = generate_reading(scenario_type)
            validation = validate_reading(reading)
            decision = classify_event(reading, validation)
            elapsed_ms = (time.time() - start) * 1000

            is_correct = decision.classification.value == scenario_type
            scenario_id = await insert_scenario(
                name=f"Auto Test {scenario_type} #{i + 1}",
                scenario_type=scenario_type,
                expected_class=scenario_type,
            )
            await insert_test_result(
                scenario_id,
                scenario_type,
                decision.classification.value,
                is_correct,
                elapsed_ms,
            )
            results.append(
                {
                    "type": scenario_type,
                    "expected": scenario_type,
                    "predicted": decision.classification.value,
                    "correct": is_correct,
                }
            )

    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    accuracy = correct / total if total > 0 else 0

    class_stats: dict = {}
    for r in results:
        exp = r["expected"]
        if exp not in class_stats:
            class_stats[exp] = {"correct": 0, "total": 0}
        class_stats[exp]["total"] += 1
        if r["correct"]:
            class_stats[exp]["correct"] += 1

    dangerous = sum(
        1
        for r in results
        if r["expected"] == "emergency" and r["predicted"] == "normal"
    )

    print(f"\n{'=' * 50}")
    print("BATCH TEST RESULTS")
    print(f"{'=' * 50}")
    print(f"Total tests: {total}")
    print(f"Correct: {correct}")
    print(f"Accuracy: {accuracy:.1%}")
    print(f"Dangerous errors (emergency->normal): {dangerous}")
    print("\nPer-class accuracy:")
    for cls, stats in class_stats.items():
        cls_acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        print(f"  {cls}: {cls_acc:.1%} ({stats['correct']}/{stats['total']})")
    print(f"{'=' * 50}\n")

    return results


if __name__ == "__main__":
    asyncio.run(run_batch_tests())
