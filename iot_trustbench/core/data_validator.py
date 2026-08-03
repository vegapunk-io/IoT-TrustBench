"""Data validation module for IoT sensor readings.

Performs comprehensive validation including:
  - Required field presence
  - Physical value bounds
  - Timestamp freshness and plausibility
  - Device registration status
  - Duplicate / replay detection
  - Cross-sensor consistency checks
  - Trusted-device database lookup
"""

from datetime import datetime, timedelta
from typing import List, Optional

from .sensor_simulator import SensorReading, REGISTERED_DEVICES, NORMAL_RANGES

# Absolute physical limits for each sensor
PHYSICAL_LIMITS = {
    "temperature": (-40.0, 150.0),
    "humidity": (0.0, 100.0),
    "smoke": (0.0, 100.0),
    "gas": (0.0, 100.0),
}

# Maximum acceptable data age in seconds
MAX_STALENESS_SECONDS = 600  # 10 minutes


class ValidationResult:
    """Aggregated result of all validation checks."""

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


def validate_required_fields(reading: SensorReading, result: ValidationResult) -> None:
    """Check that all mandatory fields are present and non-null."""
    required_fields = ["temperature", "humidity", "smoke", "gas", "device_id", "timestamp"]
    for field in required_fields:
        value = getattr(reading, field, None)
        if value is None:
            result.add_error(f"Required field '{field}' is missing or null")
        else:
            result.add_pass(f"Field '{field}' is present")


def validate_device_id(
    reading: SensorReading,
    result: ValidationResult,
    trusted_device_ids: Optional[List[str]] = None,
) -> None:
    """Validate the device ID against known/trusted device lists.

    Unknown devices are flagged as errors (will be classified as spoofing).
    """
    known_ids = set(REGISTERED_DEVICES)
    if trusted_device_ids:
        known_ids.update(trusted_device_ids)

    if reading.device_id in known_ids:
        result.add_pass(f"Device '{reading.device_id}' is registered")
    else:
        result.add_error(f"Device '{reading.device_id}' is NOT registered")


def validate_device_enabled(
    reading: SensorReading,
    result: ValidationResult,
    disabled_device_ids: Optional[List[str]] = None,
) -> None:
    """Check if a device has been disabled in the trusted_devices table."""
    if disabled_device_ids and reading.device_id in disabled_device_ids:
        result.add_error(f"Device '{reading.device_id}' is disabled")
    else:
        result.add_pass(f"Device '{reading.device_id}' is not disabled")


def validate_timestamp(reading: SensorReading, result: ValidationResult) -> None:
    """Validate that the timestamp is fresh, not stale, and not in the future."""
    now = datetime.now()
    age = now - reading.timestamp

    if reading.timestamp > now:
        result.add_error(
            f"Timestamp is in the future by {abs(age.total_seconds()):.0f}s – possible clock skew or replay"
        )
    elif age.total_seconds() > MAX_STALENESS_SECONDS:
        result.add_error(
            f"Timestamp is stale: {age.total_seconds():.0f}s old (max {MAX_STALENESS_SECONDS}s)"
        )
    elif age.total_seconds() > 300:
        result.add_warning(f"Timestamp is aging: {age.total_seconds():.0f}s old")
    else:
        result.add_pass("Timestamp is fresh")


def validate_ranges(reading: SensorReading, result: ValidationResult) -> None:
    """Check each sensor value against its normal operating range."""
    for field, (low, high) in NORMAL_RANGES.items():
        value = getattr(reading, field)
        if value < low or value > high:
            result.add_warning(f"{field}={value} is outside normal range [{low}, {high}]")
        else:
            result.add_pass(f"{field}={value} within normal range")


def validate_physical_limits(reading: SensorReading, result: ValidationResult) -> None:
    """Check values against absolute physical sensor limits."""
    for field, (low, high) in PHYSICAL_LIMITS.items():
        value = getattr(reading, field)
        if value < low:
            result.add_error(f"{field}={value} is below physical minimum ({low})")
        elif value > high:
            result.add_error(f"{field}={value} exceeds physical maximum ({high})")

    # Additional specific checks
    if reading.humidity < 0:
        result.add_error(f"Humidity {reading.humidity}% is physically impossible (negative)")
    if reading.humidity > 100:
        result.add_error(f"Humidity {reading.humidity}% is physically impossible (>100%)")
    if reading.smoke > 100:
        result.add_error(f"Smoke level {reading.smoke} exceeds maximum (100)")
    if reading.gas > 100:
        result.add_error(f"Gas level {reading.gas} exceeds maximum (100)")
    if reading.temperature < -40 or reading.temperature > 150:
        result.add_error(f"Temperature {reading.temperature}°C is outside sensor range [-40, 150]")

    # Door status validation
    valid_door = {"open", "closed"}
    if reading.door_status not in valid_door:
        result.add_error(f"Invalid door_status '{reading.door_status}' – must be 'open' or 'closed'")
    else:
        result.add_pass(f"Door status '{reading.door_status}' is valid")

    # Power status validation
    valid_power = {"on", "off"}
    if reading.power_status not in valid_power:
        result.add_error(f"Invalid power_status '{reading.power_status}' – must be 'on' or 'off'")
    else:
        result.add_pass(f"Power status '{reading.power_status}' is valid")


def validate_duplicates(
    reading: SensorReading,
    result: ValidationResult,
    history: Optional[List[SensorReading]] = None,
) -> None:
    """Detect duplicate or replayed telemetry by comparing to recent history."""
    if not history:
        result.add_pass("No history available for duplicate check")
        return

    last = history[-1]
    if (
        reading.temperature == last.temperature
        and reading.humidity == last.humidity
        and reading.smoke == last.smoke
        and reading.gas == last.gas
        and reading.device_id == last.device_id
        and reading.timestamp == last.timestamp
    ):
        result.add_error("Exact duplicate reading detected (same values and timestamp) – possible replay")
    elif (
        reading.temperature == last.temperature
        and reading.humidity == last.humidity
        and reading.smoke == last.smoke
        and reading.gas == last.gas
    ):
        result.add_warning("Duplicate sensor values detected (identical readings)")
    else:
        result.add_pass("No duplicate reading detected")


def validate_consistency(reading: SensorReading, result: ValidationResult) -> None:
    """Cross-sensor consistency checks for suspicious patterns."""
    if reading.smoke > 50 and reading.gas < 5:
        result.add_warning("High smoke with very low gas – inconsistent readings")
    if reading.temperature > 60 and reading.humidity > 70:
        result.add_warning("High temperature with high humidity is unusual")
    if reading.temperature > 45 and reading.smoke < 3 and reading.gas < 5:
        result.add_warning(
            f"High temperature ({reading.temperature}°C) with negligible smoke/gas – likely sensor fault"
        )

    # No consistency warnings is fine
    if not any("consistency" in w.lower() or "inconsistent" in w.lower() for w in result.warnings):
        result.add_pass("Sensor readings are internally consistent")


def validate_reading(
    reading: SensorReading,
    history: Optional[List[SensorReading]] = None,
    trusted_device_ids: Optional[List[str]] = None,
    disabled_device_ids: Optional[List[str]] = None,
) -> ValidationResult:
    """Run all validation checks on a sensor reading.

    Args:
        reading: The sensor reading to validate.
        history: Recent readings for duplicate detection.
        trusted_device_ids: IDs from the trusted_devices database table.
        disabled_device_ids: IDs of disabled devices.

    Returns:
        ValidationResult with errors, warnings, and passed checks.
    """
    result = ValidationResult()

    validate_required_fields(reading, result)
    validate_device_id(reading, result, trusted_device_ids)
    validate_device_enabled(reading, result, disabled_device_ids)
    validate_timestamp(reading, result)
    validate_physical_limits(reading, result)
    validate_ranges(reading, result)
    validate_duplicates(reading, result, history)
    validate_consistency(reading, result)

    return result
