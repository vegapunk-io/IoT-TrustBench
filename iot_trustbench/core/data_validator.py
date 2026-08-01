from datetime import datetime, timedelta
from typing import List, Tuple
from .sensor_simulator import SensorReading, REGISTERED_DEVICES, NORMAL_RANGES


class ValidationResult:
    def __init__(self):
        self.is_valid = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.checks_passed: List[str] = []

    def add_error(self, message: str):
        self.is_valid = False
        self.errors.append(message)

    def add_warning(self, message: str):
        self.warnings.append(message)

    def add_pass(self, message: str):
        self.checks_passed.append(message)


def validate_ranges(reading: SensorReading, result: ValidationResult):
    for field, (low, high) in NORMAL_RANGES.items():
        value = getattr(reading, field)
        if value < low or value > high:
            result.add_error(f"{field}={value} is outside normal range [{low}, {high}]")
        else:
            result.add_pass(f"{field}={value} within normal range")


def validate_required_fields(reading: SensorReading, result: ValidationResult):
    required = ["temperature", "humidity", "smoke", "gas", "device_id", "timestamp"]
    for field in required:
        value = getattr(reading, field)
        if value is None:
            result.add_error(f"Required field '{field}' is missing")
        else:
            result.add_pass(f"Field '{field}' is present")


def validate_timestamp(reading: SensorReading, result: ValidationResult):
    now = datetime.now()
    age = now - reading.timestamp
    max_age = timedelta(minutes=10)
    if age > max_age:
        result.add_error(f"Timestamp is stale: {age.total_seconds():.0f}s old (max {max_age.total_seconds():.0f}s)")
    elif age > timedelta(minutes=5):
        result.add_warning(f"Timestamp is aging: {age.total_seconds():.0f}s old")
    else:
        result.add_pass("Timestamp is fresh")


def validate_device_id(reading: SensorReading, result: ValidationResult):
    if reading.device_id in REGISTERED_DEVICES:
        result.add_pass(f"Device '{reading.device_id}' is registered")
    else:
        result.add_error(f"Device '{reading.device_id}' is NOT registered")


def validate_duplicates(reading: SensorReading, result: ValidationResult, history: List[SensorReading]):
    if len(history) > 0:
        last = history[-1]
        if (reading.temperature == last.temperature and
            reading.humidity == last.humidity and
            reading.smoke == last.smoke and
            reading.gas == last.gas):
            result.add_warning("Duplicate reading detected (identical values)")
        else:
            result.add_pass("No duplicate reading detected")


def validate_impossible_values(reading: SensorReading, result: ValidationResult):
    if reading.humidity > 100:
        result.add_error(f"Humidity {reading.humidity}% is physically impossible (>100%)")
    if reading.smoke > 100:
        result.add_error(f"Smoke level {reading.smoke} exceeds maximum (100)")
    if reading.gas > 100:
        result.add_error(f"Gas level {reading.gas} exceeds maximum (100)")
    if reading.temperature < -40 or reading.temperature > 150:
        result.add_error(f"Temperature {reading.temperature}°C is outside sensor range")
    if not any(result.errors):
        result.add_pass("All values within physical limits")


def validate_consistency(reading: SensorReading, result: ValidationResult):
    if reading.smoke > 50 and reading.gas < 5:
        result.add_warning("High smoke with low gas may indicate sensor issue")
    if reading.temperature > 60 and reading.humidity > 70:
        result.add_warning("High temperature with high humidity is unusual")
    if not any("consistency" in w.lower() for w in result.warnings):
        result.add_pass("Sensor readings are internally consistent")


def validate_reading(
    reading: SensorReading,
    history: List[SensorReading] = None
) -> ValidationResult:
    result = ValidationResult()
    if history is None:
        history = []

    validate_required_fields(reading, result)
    validate_timestamp(reading, result)
    validate_device_id(reading, result)
    validate_ranges(reading, result)
    validate_impossible_values(reading, result)
    validate_duplicates(reading, result, history)
    validate_consistency(reading, result)

    return result
