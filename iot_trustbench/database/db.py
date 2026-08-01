import aiosqlite
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

DB_PATH = "iot_trustbench.db"


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            scenario_type TEXT NOT NULL,
            expected_class TEXT NOT NULL,
            description TEXT,
            sensor_config TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id INTEGER,
            temperature REAL,
            humidity REAL,
            smoke REAL,
            gas REAL,
            motion INTEGER,
            door_status TEXT,
            power_status TEXT,
            device_id TEXT,
            timestamp TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id INTEGER,
            telemetry_id INTEGER,
            classification TEXT,
            confidence REAL,
            evidence TEXT,
            requires_human_verification INTEGER,
            reasoning TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_id) REFERENCES scenarios(id),
            FOREIGN KEY (telemetry_id) REFERENCES telemetry(id)
        );

        CREATE TABLE IF NOT EXISTS llm_explanations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER,
            explanation TEXT,
            prompt_used TEXT,
            backend TEXT,
            generation_time_ms REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (decision_id) REFERENCES decisions(id)
        );

        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id INTEGER,
            expected_class TEXT,
            predicted_class TEXT,
            is_correct INTEGER,
            execution_time_ms REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
        );

        CREATE TABLE IF NOT EXISTS hardware_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            temperature REAL,
            humidity REAL,
            smoke REAL,
            gas REAL,
            motion INTEGER,
            door_status TEXT,
            power_status TEXT,
            classification TEXT,
            confidence REAL,
            evidence TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS hardware_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            device_type TEXT DEFAULT 'esp32',
            location TEXT,
            last_seen TIMESTAMP,
            status TEXT DEFAULT 'active'
        );
    """)
    await db.commit()
    await db.close()


async def insert_scenario(name: str, scenario_type: str, expected_class: str,
                          description: str = "", sensor_config: str = "") -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO scenarios (name, scenario_type, expected_class, description, sensor_config) VALUES (?, ?, ?, ?, ?)",
        (name, scenario_type, expected_class, description, sensor_config)
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


async def insert_telemetry(scenario_id: int, reading: dict) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO telemetry (scenario_id, temperature, humidity, smoke, gas,
           motion, door_status, power_status, device_id, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (scenario_id, reading["temperature"], reading["humidity"],
         reading["smoke"], reading["gas"], int(reading["motion"]),
         reading["door_status"], reading["power_status"],
         reading["device_id"], reading["timestamp"])
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


async def insert_decision(scenario_id: int, telemetry_id: int, decision: dict) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO decisions (scenario_id, telemetry_id, classification, confidence,
           evidence, requires_human_verification, reasoning)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (scenario_id, telemetry_id, decision["classification"],
         decision["confidence"], json.dumps(decision["evidence"]),
         int(decision["requires_human_verification"]), decision["reasoning"])
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


async def insert_llm_explanation(decision_id: int, explanation: dict) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO llm_explanations (decision_id, explanation, prompt_used, backend, generation_time_ms)
           VALUES (?, ?, ?, ?, ?)""",
        (decision_id, explanation["explanation"], explanation.get("prompt_used", ""),
         explanation.get("backend", "local"), explanation.get("generation_time_ms", 0))
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


async def insert_test_result(scenario_id: int, expected: str, predicted: str,
                             is_correct: bool, execution_time_ms: float = 0) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO test_results (scenario_id, expected_class, predicted_class,
           is_correct, execution_time_ms) VALUES (?, ?, ?, ?, ?)""",
        (scenario_id, expected, predicted, int(is_correct), execution_time_ms)
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


async def get_all_scenarios() -> List[Dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM scenarios ORDER BY id")
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


async def get_scenario_by_id(scenario_id: int) -> Optional[Dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,))
    row = await cursor.fetchone()
    await db.close()
    return dict(row) if row else None


async def get_recent_decisions(limit: int = 50) -> List[Dict]:
    db = await get_db()
    cursor = await db.execute(
        """SELECT d.*, t.temperature, t.humidity, t.smoke, t.gas, t.device_id
           FROM decisions d
           JOIN telemetry t ON d.telemetry_id = t.id
           ORDER BY d.id DESC LIMIT ?""",
        (limit,)
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


async def get_test_results() -> List[Dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM test_results ORDER BY id")
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


async def get_evaluation_metrics() -> Dict[str, Any]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM test_results")
    rows = await cursor.fetchall()
    await db.close()

    if not rows:
        return {"total": 0, "accuracy": 0, "by_class": {}, "dangerous_errors": 0}

    total = len(rows)
    correct = sum(1 for r in rows if r["is_correct"])
    accuracy = correct / total if total > 0 else 0

    classes = {}
    dangerous_errors = 0
    for row in rows:
        expected = row["expected_class"]
        predicted = row["predicted_class"]
        if expected not in classes:
            classes[expected] = {"tp": 0, "fp": 0, "fn": 0, "total": 0}
        classes[expected]["total"] += 1
        if expected == predicted:
            classes[expected]["tp"] += 1
        else:
            classes[expected]["fn"] += 1
            if predicted not in classes:
                classes[predicted] = {"tp": 0, "fp": 0, "fn": 0, "total": 0}
            classes[predicted]["fp"] += 1
            if expected == "emergency" and predicted == "normal":
                dangerous_errors += 1

    by_class = {}
    for cls, stats in classes.items():
        precision = stats["tp"] / (stats["tp"] + stats["fp"]) if (stats["tp"] + stats["fp"]) > 0 else 0
        recall = stats["tp"] / (stats["tp"] + stats["fn"]) if (stats["tp"] + stats["fn"]) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        by_class[cls] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": stats["total"],
        }

    false_alarm = sum(1 for r in rows
                      if r["expected_class"] in ("normal", "sensor_fault")
                      and r["predicted_class"] == "emergency")
    false_alarm_rate = false_alarm / total if total > 0 else 0

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(accuracy, 3),
        "by_class": by_class,
        "dangerous_errors": dangerous_errors,
        "false_alarm_rate": round(false_alarm_rate, 3),
    }


async def insert_hardware_reading(device_id: str, reading: dict, decision: dict) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO hardware_readings
           (device_id, temperature, humidity, smoke, gas, motion, door_status, power_status,
            classification, confidence, evidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (device_id, reading.get("temperature"), reading.get("humidity"),
         reading.get("smoke"), reading.get("gas"), int(reading.get("motion", False)),
         reading.get("door_status", "closed"), reading.get("power_status", "on"),
         decision.get("classification"), decision.get("confidence"),
         json.dumps(decision.get("evidence", [])))
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


async def upsert_hardware_device(device_id: str, location: str = ""):
    db = await get_db()
    await db.execute(
        """INSERT INTO hardware_devices (device_id, location, last_seen, status)
           VALUES (?, ?, CURRENT_TIMESTAMP, 'active')
           ON CONFLICT(device_id) DO UPDATE SET last_seen=CURRENT_TIMESTAMP, status='active'""",
        (device_id, location)
    )
    await db.commit()
    await db.close()


async def get_hardware_readings(limit: int = 50) -> List[Dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM hardware_readings ORDER BY id DESC LIMIT ?", (limit,)
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


async def get_hardware_devices() -> List[Dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM hardware_devices ORDER BY last_seen DESC")
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


async def get_latest_hardware_reading(device_id: str = None) -> Optional[Dict]:
    db = await get_db()
    if device_id:
        cursor = await db.execute(
            "SELECT * FROM hardware_readings WHERE device_id=? ORDER BY id DESC LIMIT 1",
            (device_id,)
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM hardware_readings ORDER BY id DESC LIMIT 1"
        )
    row = await cursor.fetchone()
    await db.close()
    return dict(row) if row else None
