import random
import uuid
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel


class SensorReading(BaseModel):
    temperature: float
    humidity: float
    smoke: float
    gas: float
    motion: bool
    door_status: str
    power_status: str
    device_id: str
    timestamp: datetime


REGISTERED_DEVICES = [
    "DEV-001-TEMP",
    "DEV-002-HUM",
    "DEV-003-SMOKE",
    "DEV-004-GAS",
    "DEV-005-MOTION",
]

NORMAL_RANGES = {
    "temperature": (18.0, 35.0),
    "humidity": (20.0, 80.0),
    "smoke": (0.0, 10.0),
    "gas": (0.0, 20.0),
}


def generate_normal_reading(device_id: Optional[str] = None) -> SensorReading:
    return SensorReading(
        temperature=round(random.uniform(22.0, 30.0), 1),
        humidity=round(random.uniform(35.0, 65.0), 1),
        smoke=round(random.uniform(0.0, 5.0), 1),
        gas=round(random.uniform(0.0, 10.0), 1),
        motion=random.choice([True, False]),
        door_status=random.choice(["closed", "closed", "closed", "open"]),
        power_status="on",
        device_id=device_id or random.choice(REGISTERED_DEVICES),
        timestamp=datetime.now(),
    )


def generate_emergency_reading(device_id: Optional[str] = None) -> SensorReading:
    return SensorReading(
        temperature=round(random.uniform(55.0, 85.0), 1),
        humidity=round(random.uniform(10.0, 30.0), 1),
        smoke=round(random.uniform(70.0, 100.0), 1),
        gas=round(random.uniform(60.0, 100.0), 1),
        motion=True,
        door_status="open",
        power_status="on",
        device_id=device_id or random.choice(REGISTERED_DEVICES),
        timestamp=datetime.now(),
    )


def generate_sensor_fault(device_id: Optional[str] = None) -> SensorReading:
    fault_type = random.choice(["high_temp", "high_humidity", "stuck_zero", "erratic", "single_outlier", "inconsistent"])
    if fault_type == "high_temp":
        temp = random.uniform(90.0, 120.0)
    elif fault_type == "high_humidity":
        temp = round(random.uniform(22.0, 28.0), 1)
    elif fault_type == "stuck_zero":
        temp = 0.0
    elif fault_type == "erratic":
        temp = round(random.uniform(-50.0, -10.0), 1)
    elif fault_type == "single_outlier":
        temp = round(random.uniform(70.0, 100.0), 1)
    else:
        temp = round(random.uniform(45.0, 60.0), 1)

    if fault_type == "high_humidity":
        return SensorReading(
            temperature=temp,
            humidity=round(random.uniform(85.0, 99.0), 1),
            smoke=round(random.uniform(0.0, 5.0), 1),
            gas=round(random.uniform(0.0, 10.0), 1),
            motion=False,
            door_status="closed",
            power_status="on",
            device_id=device_id or random.choice(REGISTERED_DEVICES),
            timestamp=datetime.now(),
        )

    if fault_type == "single_outlier":
        return SensorReading(
            temperature=temp,
            humidity=round(random.uniform(35.0, 55.0), 1),
            smoke=round(random.uniform(0.0, 3.0), 1),
            gas=round(random.uniform(0.0, 8.0), 1),
            motion=False,
            door_status="closed",
            power_status="on",
            device_id=device_id or random.choice(REGISTERED_DEVICES),
            timestamp=datetime.now(),
        )

    if fault_type == "inconsistent":
        return SensorReading(
            temperature=round(random.uniform(50.0, 70.0), 1),
            humidity=round(random.uniform(35.0, 55.0), 1),
            smoke=round(random.uniform(0.0, 2.0), 1),
            gas=round(random.uniform(0.0, 3.0), 1),
            motion=False,
            door_status="closed",
            power_status="on",
            device_id=device_id or random.choice(REGISTERED_DEVICES),
            timestamp=datetime.now(),
        )

    return SensorReading(
        temperature=temp,
        humidity=round(random.uniform(0.0, 100.0), 1),
        smoke=round(random.uniform(0.0, 5.0), 1),
        gas=round(random.uniform(0.0, 10.0), 1),
        motion=False,
        door_status="closed",
        power_status="on",
        device_id=device_id or random.choice(REGISTERED_DEVICES),
        timestamp=datetime.now(),
    )


def generate_spoofed_reading(device_id: Optional[str] = None) -> SensorReading:
    spoof_type = random.choice(["invalid_humidity", "unknown_device", "impossible_values"])
    if spoof_type == "invalid_humidity":
        humidity = random.uniform(101.0, 200.0)
        device_id = random.choice(REGISTERED_DEVICES)
    elif spoof_type == "unknown_device":
        humidity = round(random.uniform(30.0, 60.0), 1)
        device_id = f"FAKE-{uuid.uuid4().hex[:8].upper()}"
    else:
        humidity = random.uniform(101.0, 500.0)
        device_id = random.choice(REGISTERED_DEVICES)

    return SensorReading(
        temperature=round(random.uniform(20.0, 30.0), 1),
        humidity=humidity,
        smoke=round(random.uniform(0.0, 5.0), 1),
        gas=round(random.uniform(0.0, 10.0), 1),
        motion=random.choice([True, False]),
        door_status=random.choice(["closed", "open"]),
        power_status="on",
        device_id=device_id,
        timestamp=datetime.now(),
    )


def generate_offline_reading(device_id: Optional[str] = None) -> SensorReading:
    delay_minutes = random.choice([15, 30, 60, 120, 240])
    return SensorReading(
        temperature=round(random.uniform(22.0, 28.0), 1),
        humidity=round(random.uniform(40.0, 60.0), 1),
        smoke=round(random.uniform(0.0, 3.0), 1),
        gas=round(random.uniform(0.0, 5.0), 1),
        motion=False,
        door_status="closed",
        power_status="off",
        device_id=device_id or random.choice(REGISTERED_DEVICES),
        timestamp=datetime.now() - timedelta(minutes=delay_minutes),
    )


def generate_uncertain_reading(device_id: Optional[str] = None) -> SensorReading:
    return SensorReading(
        temperature=round(random.uniform(35.0, 48.0), 1),
        humidity=round(random.uniform(25.0, 75.0), 1),
        smoke=round(random.uniform(5.0, 25.0), 1),
        gas=round(random.uniform(10.0, 30.0), 1),
        motion=random.choice([True, False]),
        door_status=random.choice(["closed", "open"]),
        power_status="on",
        device_id=device_id or random.choice(REGISTERED_DEVICES),
        timestamp=datetime.now(),
    )


GENERATORS = {
    "normal": generate_normal_reading,
    "emergency": generate_emergency_reading,
    "sensor_fault": generate_sensor_fault,
    "spoofing": generate_spoofed_reading,
    "offline": generate_offline_reading,
    "uncertain": generate_uncertain_reading,
}


def generate_reading(scenario_type: str, device_id: Optional[str] = None) -> SensorReading:
    generator = GENERATORS.get(scenario_type, generate_normal_reading)
    return generator(device_id)
