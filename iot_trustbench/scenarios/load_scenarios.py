import json
import asyncio
import os
from iot_trustbench.database.db import init_db, insert_scenario


async def load_scenarios():
    await init_db()
    scenario_file = os.path.join(os.path.dirname(__file__), "test_scenarios.json")
    with open(scenario_file) as f:
        scenarios = json.load(f)

    count = 0
    for s in scenarios:
        await insert_scenario(
            name=s["name"],
            scenario_type=s["scenario_type"],
            expected_class=s["expected_class"],
            description=s["description"],
        )
        count += 1
    print(f"Loaded {count} scenarios into database.")


if __name__ == "__main__":
    asyncio.run(load_scenarios())
