import aiosqlite
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

DB_PATH = "iot_trustbench.db"


async def get_db() -> aiosqlite.Connection:
    """Return an aiosqlite connection with Row factory enabled."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db() -> None:
    """Create all database tables if they do not exist."""
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

        CREATE TABLE IF NOT EXISTS trusted_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            device_name TEXT NOT NULL DEFAULT '',
            device_type TEXT NOT NULL DEFAULT 'esp32',
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            enabled INTEGER NOT NULL DEFAULT 1,
            token_hash TEXT
        );
    """)
    await db.commit()
    await db.close()


# ======================================================================
# Scenario helpers
# ======================================================================

async def insert_scenario(
    name: str,
    scenario_type: str,
    expected_class: str,
    description: str = "",
    sensor_config: str = "",
) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO scenarios"
        " (name, scenario_type, expected_class, description, sensor_config)"
        " VALUES (?, ?, ?, ?, ?)",
        (name, scenario_type, expected_class, description, sensor_config),
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


async def insert_telemetry(scenario_id: int, reading: dict) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO telemetry
           (scenario_id, temperature, humidity, smoke, gas,
            motion, door_status, power_status, device_id, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            scenario_id,
            reading["temperature"],
            reading["humidity"],
            reading["smoke"],
            reading["gas"],
            int(reading["motion"]),
            reading["door_status"],
            reading["power_status"],
            reading["device_id"],
            reading["timestamp"],
        ),
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


async def insert_decision(
    scenario_id: int, telemetry_id: int, decision: dict
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO decisions
           (scenario_id, telemetry_id, classification, confidence,
            evidence, requires_human_verification, reasoning)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            scenario_id,
            telemetry_id,
            decision["classification"],
            decision["confidence"],
            json.dumps(decision["evidence"]),
            int(decision["requires_human_verification"]),
            decision["reasoning"],
        ),
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


async def insert_llm_explanation(decision_id: int, explanation: dict) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO llm_explanations
           (decision_id, explanation, prompt_used, backend, generation_time_ms)
           VALUES (?, ?, ?, ?, ?)""",
        (
            decision_id,
            explanation["explanation"],
            explanation.get("prompt_used", ""),
            explanation.get("backend", "local"),
            explanation.get("generation_time_ms", 0),
        ),
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


async def insert_test_result(
    scenario_id: int,
    expected: str,
    predicted: str,
    is_correct: bool,
    execution_time_ms: float = 0,
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO test_results
           (scenario_id, expected_class, predicted_class,
            is_correct, execution_time_ms)
           VALUES (?, ?, ?, ?, ?)""",
        (scenario_id, expected, predicted, int(is_correct), execution_time_ms),
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


# ======================================================================
# Read helpers
# ======================================================================

async def get_all_scenarios() -> List[Dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM scenarios ORDER BY id")
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


async def get_scenario_by_id(scenario_id: int) -> Optional[Dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM scenarios WHERE id = ?", (scenario_id,)
    )
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
        (limit,),
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


# ======================================================================
# Evaluation metrics
# ======================================================================

async def get_evaluation_metrics() -> Dict[str, Any]:
    """Compute comprehensive evaluation metrics from test_results.

    Returns total, correct, accuracy, per-class precision/recall/F1,
    support, confusion_matrix, false_alarm_rate, dangerous_errors,
    missed_emergencies, correct_uncertain_rate, and
    spoof_detected_count.
    """
    db = await get_db()
    cursor = await db.execute("SELECT * FROM test_results")
    rows = await cursor.fetchall()
    await db.close()

    if not rows:
        return {
            "total": 0,
            "accuracy": 0,
            "by_class": {},
            "confusion_matrix": {},
            "dangerous_errors": 0,
            "false_alarm_rate": 0,
            "missed_emergencies": 0,
            "correct_uncertain_rate": 0,
            "spoof_detected_count": 0,
        }

    total = len(rows)
    correct = sum(1 for r in rows if r["is_correct"])
    accuracy = correct / total if total > 0 else 0

    # Gather all classes that appear in expected or predicted
    all_classes: set = set()
    classes: Dict[str, Dict[str, int]] = {}
    confusion: Dict[str, Dict[str, int]] = {}
    dangerous_errors = 0
    missed_emergencies = 0
    correct_uncertain = 0
    total_uncertain_expected = 0
    spoof_detected = 0

    for row in rows:
        expected = row["expected_class"]
        predicted = row["predicted_class"]
        all_classes.add(expected)
        all_classes.add(predicted)

        # Per-class TP/FP/FN
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

        # Confusion matrix
        if expected not in confusion:
            confusion[expected] = {}
        confusion[expected][predicted] = confusion[expected].get(predicted, 0) + 1

        # Dangerous error: expected emergency but classified normal
        if expected == "emergency" and predicted == "normal":
            dangerous_errors += 1

        # Missed emergency: expected emergency but predicted something else
        if expected == "emergency" and predicted != "emergency":
            missed_emergencies += 1

        # False alarm: normal/sensor_fault predicted as emergency
        if (
            expected in ("normal", "sensor_fault")
            and predicted == "emergency"
        ):
            pass  # counted below

        # Uncertain verification rate
        if expected == "uncertain":
            total_uncertain_expected += 1
            if predicted == "uncertain":
                correct_uncertain += 1

        # Spoofing detection
        if expected == "spoofing" and predicted == "spoofing":
            spoof_detected += 1

    # False alarm rate
    false_alarm = sum(
        1
        for r in rows
        if r["expected_class"] in ("normal", "sensor_fault")
        and r["predicted_class"] == "emergency"
    )
    false_alarm_rate = false_alarm / total if total > 0 else 0

    # Per-class metrics
    by_class: Dict[str, Dict[str, Any]] = {}
    for cls in all_classes:
        stats = classes.get(cls, {"tp": 0, "fp": 0, "fn": 0, "total": 0})
        precision = (
            stats["tp"] / (stats["tp"] + stats["fp"])
            if (stats["tp"] + stats["fp"]) > 0
            else 0
        )
        recall = (
            stats["tp"] / (stats["tp"] + stats["fn"])
            if (stats["tp"] + stats["fn"]) > 0
            else 0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0
        )
        by_class[cls] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": stats["total"],
        }

    correct_uncertain_rate = (
        correct_uncertain / total_uncertain_expected
        if total_uncertain_expected > 0
        else 0
    )

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(accuracy, 3),
        "by_class": by_class,
        "confusion_matrix": confusion,
        "dangerous_errors": dangerous_errors,
        "false_alarm_rate": round(false_alarm_rate, 3),
        "missed_emergencies": missed_emergencies,
        "correct_uncertain_rate": round(correct_uncertain_rate, 3),
        "spoof_detected_count": spoof_detected,
    }


# ======================================================================
# Hardware helpers
# ======================================================================

async def insert_hardware_reading(
    device_id: str, reading: dict, decision: dict
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO hardware_readings
           (device_id, temperature, humidity, smoke, gas, motion,
            door_status, power_status, classification, confidence, evidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            device_id,
            reading.get("temperature"),
            reading.get("humidity"),
            reading.get("smoke"),
            reading.get("gas"),
            int(reading.get("motion", False)),
            reading.get("door_status", "closed"),
            reading.get("power_status", "on"),
            decision.get("classification"),
            decision.get("confidence"),
            json.dumps(decision.get("evidence", [])),
        ),
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


async def upsert_hardware_device(
    device_id: str, location: str = ""
) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO hardware_devices (device_id, location, last_seen, status)
           VALUES (?, ?, CURRENT_TIMESTAMP, 'active')
           ON CONFLICT(device_id) DO UPDATE SET
             last_seen=CURRENT_TIMESTAMP, status='active'""",
        (device_id, location),
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
    cursor = await db.execute(
        "SELECT * FROM hardware_devices ORDER BY last_seen DESC"
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


async def get_latest_hardware_reading(
    device_id: Optional[str] = None,
) -> Optional[Dict]:
    db = await get_db()
    if device_id:
        cursor = await db.execute(
            "SELECT * FROM hardware_readings WHERE device_id=?"
            " ORDER BY id DESC LIMIT 1",
            (device_id,),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM hardware_readings ORDER BY id DESC LIMIT 1"
        )
    row = await cursor.fetchone()
    await db.close()
    return dict(row) if row else None


# ======================================================================
# Trusted-device helpers
# ======================================================================

async def insert_trusted_device(
    device_id: str,
    device_name: str = "",
    device_type: str = "esp32",
    token_hash: Optional[str] = None,
) -> int:
    """Register a new trusted device."""
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO trusted_devices
           (device_id, device_name, device_type, token_hash)
           VALUES (?, ?, ?, ?)""",
        (device_id, device_name, device_type, token_hash),
    )
    await db.commit()
    row_id = cursor.lastrowid
    await db.close()
    return row_id


async def get_trusted_devices() -> List[Dict]:
    """Return all registered trusted devices."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM trusted_devices ORDER BY registered_at DESC"
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


async def get_trusted_device(device_id: str) -> Optional[Dict]:
    """Return a single trusted device by device_id."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM trusted_devices WHERE device_id = ?", (device_id,)
    )
    row = await cursor.fetchone()
    await db.close()
    return dict(row) if row else None


async def set_trusted_device_enabled(
    device_id: str, enabled: bool
) -> bool:
    """Enable or disable a trusted device. Returns True if updated."""
    db = await get_db()
    cursor = await db.execute(
        "UPDATE trusted_devices SET enabled = ? WHERE device_id = ?",
        (int(enabled), device_id),
    )
    await db.commit()
    updated = cursor.rowcount > 0
    await db.close()
    return updated


async def delete_trusted_device(device_id: str) -> bool:
    """Remove a trusted device. Returns True if deleted."""
    db = await get_db()
    cursor = await db.execute(
        "DELETE FROM trusted_devices WHERE device_id = ?", (device_id,)
    )
    await db.commit()
    deleted = cursor.rowcount > 0
    await db.close()
    return deleted
