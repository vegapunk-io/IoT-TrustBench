from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from .sensor_simulator import SensorReading, REGISTERED_DEVICES, NORMAL_RANGES


class ValidationResult:
    """Collects errors, warnings, and passed-checks during validation."""

    def __init__(self) -> None:
        self.is_valid: bool = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.checks_passed: List[str] = []

    def add_error(self, message: str) -> None:
        self.is_valid = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_pass(self, message: str) -> None:
        self.checks_passed.append(message)


# ------------------------------------------------------------------
# Required-field check
# ------------------------------------------------------------------
def validate_required_fields(
    reading: SensorReading, result: ValidationResult
) -> None:
    """Verify that every mandatory field is present and non-None."""
    required = [
        "temperature", "humidity", "smoke", "gas",
        "device_id", "timestamp",
    ]
    for field in required:
        value = getattr(reading, field)
        if value is None:
            result.add_error(f"Required field '{field}' is missing")
        else:
            result.add_pass(f"Field '{field}' is present")


# ------------------------------------------------------------------
# Device-ID check
# ------------------------------------------------------------------
def validate_device_id(
    reading: SensorReading, result: ValidationResult
) -> None:
    """Check the device_id against the registered list.

    NOTE: This uses the static REGISTERED_DEVICES list.  The safety
    engine performs an additional database-backed trusted-device check.
    """
    if reading.device_id in REGISTERED_DEVICES:
        result.add_pass(f"Device '{reading.device_id}' is registered")
    else:
        result.add_error(f"Device '{reading.device_id}' is NOT registered")


# ------------------------------------------------------------------
# Temperature limits
# ------------------------------------------------------------------
def validate_temperature(
    reading: SensorReading, result: ValidationResult
) -> None:
    """Check temperature against physically realistic limits."""
    if reading.temperature < -40:
        result.add_error(
            f"Temperature {reading.temperature}\u00b0C is below sensor minimum (-40\u00b0C)"
        )
    elif reading.temperature > 150:
        result.add_error(
            f"Temperature {reading.temperature}\u00b0C exceeds sensor maximum (150\u00b0C)"
        )
    else:
        result.add_pass("Temperature within sensor hardware range")


# ------------------------------------------------------------------
# Humidity limits
# ------------------------------------------------------------------
def validate_humidity(
    reading: SensorReading, result: ValidationResult
) -> None:
    """Check humidity is between 0 and 100 percent."""
    if reading.humidity < 0:
        result.add_error(
            f"Humidity {reading.humidity}% is below 0%"
        )
    elif reading.humidity > 100:
        result.add_error(
            f"Humidity {reading.humidity}% is physically impossible (>100%)"
        )
    else:
        result.add_pass("Humidity within physical range")


# ------------------------------------------------------------------
# Smoke / gas limits
# ------------------------------------------------------------------
def validate_smoke_gas(
    reading: SensorReading, result: ValidationResult
) -> None:
    """Check smoke and gas are within [0, 100]."""
    if reading.smoke < 0:
        result.add_error(f"Smoke level {reading.smoke} is negative")
    elif reading.smoke > 100:
        result.add_error(f"Smoke level {reading.smoke} exceeds maximum (100)")
    else:
        result.add_pass("Smoke within physical range")

    if reading.gas < 0:
        result.add_error(f"Gas level {reading.gas} is negative")
    elif reading.gas > 100:
        result.add_error(f"Gas level {reading.gas} exceeds maximum (100)")
    else:
        result.add_pass("Gas within physical range")


# ------------------------------------------------------------------
# Door / power status
# ------------------------------------------------------------------
def validate_statuses(
    reading: SensorReading, result: ValidationResult
) -> None:
    """Validate enumerated string fields."""
    valid_door = {"open", "closed"}
    if reading.door_status not in valid_door:
        result.add_error(
            f"Invalid door_status '{reading.door_status}'"
            f" (expected one of {valid_door})"
        )
    else:
        result.add_pass("Door status is valid")

    valid_power = {"on", "off"}
    if reading.power_status not in valid_power:
        result.add_error(
            f"Invalid power_status '{reading.power_status}'"
            f" (expected one of {valid_power})"
        )
    else:
        result.add_pass("Power status is valid")


# ------------------------------------------------------------------
# Timestamp freshness
# ------------------------------------------------------------------
def validate_timestamp(
    reading: SensorReading, result: ValidationResult
) -> None:
    """Reject stale or future timestamps."""
    now = datetime.now()
    age = now - reading.timestamp

    if age.total_seconds() < 0:
        result.add_error(
            f"Timestamp is in the future by {abs(age.total_seconds()):.0f}s"
        )
    elif age > timedelta(minutes=10):
        result.add_error(
            f"Timestamp is stale: {age.total_seconds():.0f}s old"
            f" (max {timedelta(minutes=10).total_seconds():.0f}s)"
        )
    elif age > timedelta(minutes=5):
        result.add_warning(
            f"Timestamp is aging: {age.total_seconds():.0f}s old"
        )
    else:
        result.add_pass("Timestamp is fresh")


# ------------------------------------------------------------------
# Normal-range check
# ------------------------------------------------------------------
def validate_ranges(
    reading: SensorReading, result: ValidationResult
) -> None:
    """Flag values that fall outside expected normal operating ranges.

    NOTE: Values outside normal ranges are *errors* only when the
    reading is expected to be normal.  The safety engine decides the
    final classification.
    """
    for field, (low, high) in NORMAL_RANGES.items():
        value = getattr(reading, field)
        if value < low or value > high:
            result.add_warning(
                f"{field}={value} is outside normal range [{low}, {high}]"
            )
        else:
            result.add_pass(f"{field}={value} within normal range")


# ------------------------------------------------------------------
# Impossible / physically-invalid values
# ------------------------------------------------------------------
def validate_impossible_values(
    reading: SensorReading, result: ValidationResult
) -> None:
    """Hard-fail checks for physically impossible readings."""
    if reading.humidity > 100:
        result.add_error(
            f"Humidity {reading.humidity}% is physically impossible (>100%)"
        )
    if reading.smoke > 100:
        result.add_error(f"Smoke level {reading.smoke} exceeds maximum (100)")
    if reading.gas > 100:
        result.add_error(f"Gas level {reading.gas} exceeds maximum (100)")
    if reading.temperature < -40 or reading.temperature > 150:
        result.add_error(
            f"Temperature {reading.temperature}\u00b0C is outside sensor range"
        )
    if not any(result.errors):
        result.add_pass("All values within physical limits")


# ------------------------------------------------------------------
# Duplicate / replay detection
# ------------------------------------------------------------------
def validate_duplicates(
    reading: SensorReading,
    result: ValidationResult,
    history: List[SensorReading],
) -> None:
    """Warn when the reading is identical to the most recent one."""
    if len(history) > 0:
        last = history[-1]
        if (
            reading.temperature == last.temperature
            and reading.humidity == last.humidity
            and reading.smoke == last.smoke
            and reading.gas == last.gas
        ):
            result.add_warning(
                "Duplicate reading detected (identical values) - possible replay"
            )
        else:
            result.add_pass("No duplicate reading detected")


# ------------------------------------------------------------------
# Internal consistency
# ------------------------------------------------------------------
def validate_consistency(
    reading: SensorReading, result: ValidationResult
) -> None:
    """Flag patterns that are unlikely in real scenarios."""
    if reading.smoke > 50 and reading.gas < 5:
        result.add_warning("High smoke with low gas may indicate sensor issue")
    if reading.temperature > 60 and reading.humidity > 70:
        result.add_warning(
            "High temperature with high humidity is unusual"
        )
    if reading.temperature > 45 and reading.smoke < 3 and reading.gas < 5:
        result.add_warning(
            "High temperature with very low smoke/gas - likely sensor fault"
        )
    if not any("consistency" in w.lower() for w in result.warnings):
        result.add_pass("Sensor readings are internally consistent")


# ------------------------------------------------------------------
# Orchestrator
# ------------------------------------------------------------------
def validate_reading(
    reading: SensorReading,
    history: Optional[List[SensorReading]] = None,
) -> ValidationResult:
    """Run all validation checks and return a ValidationResult.

    Checks are executed in order: required fields first, then
    timestamps, device identity, physical limits, range warnings,
    duplicates, and internal consistency.
    """
    result = ValidationResult()
    if history is None:
        history = []

    validate_required_fields(reading, result)
    validate_timestamp(reading, result)
    validate_device_id(reading, result)
    validate_temperature(reading, result)
    validate_humidity(reading, result)
    validate_smoke_gas(reading, result)
    validate_statuses(reading, result)
    validate_ranges(reading, result)
    validate_impossible_values(reading, result)
    validate_duplicates(reading, result, history)
    validate_consistency(reading, result)

    return result
