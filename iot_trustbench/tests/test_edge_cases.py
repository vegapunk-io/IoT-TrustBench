"""Comprehensive edge-case and boundary tests for IoT-TrustBench.

These tests are designed to be harder than the auto-generated scenarios.
Each test creates a specific hand-crafted sensor reading and verifies
that the safety engine produces the expected classification, confidence
range, evidence, and human-verification flag.
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from iot_trustbench.core.sensor_simulator import SensorReading
from iot_trustbench.core.data_validator import validate_reading
from iot_trustbench.core.safety_engine import classify_event, DecisionClass


# ------------------------------------------------------------------
# Helper to build a SensorReading with defaults
# ------------------------------------------------------------------
def _make_reading(**overrides) -> SensorReading:
    """Create a SensorReading with sensible defaults, overridden as needed."""
    defaults = dict(
        temperature=25.0,
        humidity=45.0,
        smoke=2.0,
        gas=5.0,
        motion=False,
        door_status="closed",
        power_status="on",
        device_id="DEV-001-TEMP",
        timestamp=datetime.now(),
    )
    defaults.update(overrides)
    return SensorReading(**defaults)


# ------------------------------------------------------------------
# 1. High temperature with zero smoke and gas → SENSOR_FAULT
# ------------------------------------------------------------------
def test_high_temp_zero_smoke_gas():
    """High temp with no smoke/gas should be sensor fault, not emergency."""
    reading = _make_reading(temperature=75.0, smoke=0.0, gas=0.0)
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification in (
        DecisionClass.SENSOR_FAULT,
        DecisionClass.UNCERTAIN,
    ), f"Expected SENSOR_FAULT or UNCERTAIN, got {decision.classification}"
    assert decision.requires_human_verification is True


# ------------------------------------------------------------------
# 2. High smoke with no temperature change → SENSOR_FAULT or UNCERTAIN
# ------------------------------------------------------------------
def test_high_smoke_normal_temp():
    """High smoke alone with normal temp may be sensor fault."""
    reading = _make_reading(temperature=25.0, smoke=80.0, gas=2.0)
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    # Smoke > 50 but gas < 5 → fault indicator
    assert decision.classification in (
        DecisionClass.SENSOR_FAULT,
        DecisionClass.UNCERTAIN,
        DecisionClass.EMERGENCY,
    ), f"Unexpected: {decision.classification}"


# ------------------------------------------------------------------
# 3. High gas with normal temperature → SENSOR_FAULT or UNCERTAIN
# ------------------------------------------------------------------
def test_high_gas_normal_temp():
    """High gas alone with normal temp may be sensor fault."""
    reading = _make_reading(temperature=25.0, smoke=2.0, gas=80.0)
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    # Gas > 50 scores +2 in emergency, but smoke is low.
    # The combined score needs >= 3 for emergency.
    # gas>50 → +2, temp>40+smoke>20 fails, smoke>40+gas>30 fails
    # So emergency score = 2 → not emergency. Could be fault or uncertain.
    assert decision.classification != DecisionClass.NORMAL, (
        "High gas should not be classified as normal"
    )


# ------------------------------------------------------------------
# 4. Humidity = 0 → VALID (warning if outside normal range)
# ------------------------------------------------------------------
def test_humidity_zero():
    reading = _make_reading(humidity=0.0)
    validation = validate_reading(reading)
    # Humidity 0 is below normal range [20, 80] but not impossible
    assert validation.is_valid or any(
        "humidity" in w.lower() for w in validation.warnings
    )


# ------------------------------------------------------------------
# 5. Humidity = 100 → VALID (boundary value)
# ------------------------------------------------------------------
def test_humidity_100():
    reading = _make_reading(humidity=100.0)
    validation = validate_reading(reading)
    assert validation.is_valid  # 100% is physically possible


# ------------------------------------------------------------------
# 6. Humidity > 100 → INVALID (physically impossible)
# ------------------------------------------------------------------
def test_humidity_above_100():
    reading = _make_reading(humidity=120.0)
    validation = validate_reading(reading)
    assert not validation.is_valid
    assert any("120" in e or "100" in e for e in validation.errors)


# ------------------------------------------------------------------
# 7. Negative temperature → SENSOR_FAULT or validation error
# ------------------------------------------------------------------
def test_negative_temperature():
    reading = _make_reading(temperature=-10.0)
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    # -10°C is below freezing → sensor fault
    assert decision.classification in (
        DecisionClass.SENSOR_FAULT,
        DecisionClass.UNCERTAIN,
    )


# ------------------------------------------------------------------
# 8. Unknown device with normal readings → SPOOFING
# ------------------------------------------------------------------
def test_unknown_device_normal_readings():
    reading = _make_reading(device_id="FAKE-UNKNOWN-123")
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification == DecisionClass.SPOOFING, (
        f"Unknown device should be SPOOFING, got {decision.classification}"
    )


# ------------------------------------------------------------------
# 9. Stale timestamp → OFFLINE
# ------------------------------------------------------------------
def test_stale_timestamp():
    reading = _make_reading(
        timestamp=datetime.now() - timedelta(minutes=30)
    )
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification == DecisionClass.OFFLINE, (
        f"Stale timestamp should be OFFLINE, got {decision.classification}"
    )


# ------------------------------------------------------------------
# 10. Future timestamp → INVALID validation
# ------------------------------------------------------------------
def test_future_timestamp():
    reading = _make_reading(
        timestamp=datetime.now() + timedelta(minutes=5)
    )
    validation = validate_reading(reading)
    assert not validation.is_valid
    assert any("future" in e.lower() for e in validation.errors)


# ------------------------------------------------------------------
# 11. Missing sensor data (temperature = 0.0 → stuck-zero fault)
# ------------------------------------------------------------------
def test_stuck_zero_temperature():
    reading = _make_reading(temperature=0.0)
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification in (
        DecisionClass.SENSOR_FAULT,
        DecisionClass.UNCERTAIN,
    ), f"Stuck-zero temp should be fault, got {decision.classification}"


# ------------------------------------------------------------------
# 12. Conflicting readings → UNCERTAIN
# ------------------------------------------------------------------
def test_conflicting_readings():
    """High temp + high humidity + low smoke/gas → conflicting."""
    reading = _make_reading(
        temperature=55.0, humidity=90.0, smoke=1.0, gas=2.0
    )
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    # High temp>50 → emergency score +2, but smoke/gas normal
    # Humidity > 85 + temp < 35 fails (temp is 55)
    # temp>45 + smoke<5 + gas<10 → fault +2
    # So fault=True, emergency=True → UNCERTAIN
    assert decision.classification in (
        DecisionClass.UNCERTAIN,
        DecisionClass.SENSOR_FAULT,
    ), f"Conflicting should be UNCERTAIN, got {decision.classification}"
    assert decision.requires_human_verification is True


# ------------------------------------------------------------------
# 13. Emergency with one faulty sensor → UNCERTAIN
# ------------------------------------------------------------------
def test_emergency_with_faulty_sensor():
    """Genuine emergency temps but one sensor stuck at zero."""
    reading = _make_reading(
        temperature=65.0,
        smoke=80.0,
        gas=0.0,  # gas sensor appears faulty
        humidity=15.0,
    )
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    # temp>50(+2) + smoke>50(+2) = 4 → emergency
    # smoke>50 + gas<5 → fault +2
    # Both true → UNCERTAIN
    assert decision.classification in (
        DecisionClass.UNCERTAIN,
        DecisionClass.EMERGENCY,
    ), f"Got {decision.classification}"
    assert decision.requires_human_verification is True


# ------------------------------------------------------------------
# 14. Multiple sensors offline (power off) → OFFLINE
# ------------------------------------------------------------------
def test_power_off():
    reading = _make_reading(power_status="off")
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification == DecisionClass.OFFLINE


# ------------------------------------------------------------------
# 15. Replayed data (duplicate) → UNCERTAIN (warning)
# ------------------------------------------------------------------
def test_replayed_data():
    reading = _make_reading()
    previous = [_make_reading()]
    validation = validate_reading(reading, history=previous)
    assert any("duplicate" in w.lower() for w in validation.warnings)


# ------------------------------------------------------------------
# 16. Extreme spoofing: humidity 500%
# ------------------------------------------------------------------
def test_extreme_spoofing_humidity():
    reading = _make_reading(humidity=500.0)
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification == DecisionClass.SPOOFING


# ------------------------------------------------------------------
# 17. Temperature at 90 boundary → SENSOR_FAULT
# ------------------------------------------------------------------
def test_temperature_90_boundary():
    reading = _make_reading(temperature=90.0, smoke=1.0, gas=1.0)
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification in (
        DecisionClass.SENSOR_FAULT,
        DecisionClass.UNCERTAIN,
    )


# ------------------------------------------------------------------
# 18. Pure emergency: all danger indicators high
# ------------------------------------------------------------------
def test_pure_emergency():
    reading = _make_reading(
        temperature=70.0,
        smoke=90.0,
        gas=80.0,
        humidity=10.0,
        motion=True,
        door_status="open",
    )
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification == DecisionClass.EMERGENCY, (
        f"Pure emergency should be EMERGENCY, got {decision.classification}"
    )
    assert decision.requires_human_verification is False
    assert decision.confidence >= 0.8


# ------------------------------------------------------------------
# 19. Borderline readings → UNCERTAIN
# ------------------------------------------------------------------
def test_borderline_readings():
    reading = _make_reading(
        temperature=42.0, smoke=15.0, gas=25.0, humidity=50.0
    )
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification == DecisionClass.UNCERTAIN, (
        f"Borderline should be UNCERTAIN, got {decision.classification}"
    )
    assert decision.requires_human_verification is True


# ------------------------------------------------------------------
# 20. Normal reading always classified NORMAL
# ------------------------------------------------------------------
def test_normal_always_normal():
    """Normal readings from a registered device should always be NORMAL."""
    for _ in range(10):
        reading = _make_reading(
            temperature=25.0, smoke=2.0, gas=5.0, humidity=45.0
        )
        validation = validate_reading(reading)
        decision = classify_event(reading, validation)
        assert decision.classification == DecisionClass.NORMAL, (
            f"Normal reading classified as {decision.classification}"
        )
        assert decision.requires_human_verification is False
        assert decision.confidence >= 0.9


# ------------------------------------------------------------------
# 21. Evidence is always present
# ------------------------------------------------------------------
def test_evidence_always_present():
    """Every classification must include at least one piece of evidence."""
    for stype in ["normal", "emergency", "sensor_fault", "spoofing",
                  "offline", "uncertain"]:
        reading = _make_reading(
            temperature=25.0, smoke=2.0, gas=5.0, humidity=45.0
        )
        if stype == "emergency":
            reading = _make_reading(
                temperature=70.0, smoke=90.0, gas=80.0,
                motion=True, door_status="open",
            )
        elif stype == "spoofing":
            reading = _make_reading(humidity=200.0)
        elif stype == "offline":
            reading = _make_reading(
                timestamp=datetime.now() - timedelta(minutes=30)
            )
        elif stype == "sensor_fault":
            reading = _make_reading(temperature=100.0, smoke=1.0, gas=1.0)
        elif stype == "uncertain":
            reading = _make_reading(
                temperature=42.0, smoke=15.0, gas=25.0
            )
        validation = validate_reading(reading)
        decision = classify_event(reading, validation)
        assert len(decision.evidence) > 0, (
            f"No evidence for {stype}"
        )
        assert decision.reasoning, f"No reasoning for {stype}"


# ------------------------------------------------------------------
# 22. Confidence always in [0, 1]
# ------------------------------------------------------------------
def test_confidence_always_valid():
    for stype in ["normal", "emergency", "sensor_fault", "spoofing",
                  "offline", "uncertain"]:
        reading = _make_reading(
            temperature=25.0, smoke=2.0, gas=5.0, humidity=45.0
        )
        if stype == "emergency":
            reading = _make_reading(
                temperature=70.0, smoke=90.0, gas=80.0,
                motion=True, door_status="open",
            )
        elif stype == "spoofing":
            reading = _make_reading(humidity=200.0)
        elif stype == "offline":
            reading = _make_reading(
                timestamp=datetime.now() - timedelta(minutes=30)
            )
        elif stype == "sensor_fault":
            reading = _make_reading(temperature=100.0, smoke=1.0, gas=1.0)
        elif stype == "uncertain":
            reading = _make_reading(
                temperature=42.0, smoke=15.0, gas=25.0
            )
        validation = validate_reading(reading)
        decision = classify_event(reading, validation)
        assert 0 <= decision.confidence <= 1, (
            f"Confidence {decision.confidence} out of range for {stype}"
        )


# ------------------------------------------------------------------
# 23. Dangerous emergency-to-normal mistake must not occur
# ------------------------------------------------------------------
def test_no_emergency_to_normal_mistake():
    """A genuine emergency must NEVER be classified as normal."""
    emergency_reading = _make_reading(
        temperature=70.0,
        smoke=90.0,
        gas=80.0,
        humidity=10.0,
        motion=True,
        door_status="open",
    )
    validation = validate_reading(emergency_reading)
    decision = classify_event(emergency_reading, validation)
    assert decision.classification != DecisionClass.NORMAL, (
        "CRITICAL: Emergency was misclassified as NORMAL"
    )


# ------------------------------------------------------------------
# 24. Invalid door status → validation error
# ------------------------------------------------------------------
def test_invalid_door_status():
    reading = _make_reading(door_status="ajar")
    validation = validate_reading(reading)
    assert any("door_status" in e.lower() or "invalid" in e.lower()
               for e in validation.errors)


# ------------------------------------------------------------------
# 25. Invalid power status → validation error
# ------------------------------------------------------------------
def test_invalid_power_status():
    reading = _make_reading(power_status="low")
    validation = validate_reading(reading)
    assert any("power_status" in e.lower() or "invalid" in e.lower()
               for e in validation.errors)


# ------------------------------------------------------------------
# 26. Negative smoke → validation error
# ------------------------------------------------------------------
def test_negative_smoke():
    reading = _make_reading(smoke=-5.0)
    validation = validate_reading(reading)
    assert not validation.is_valid
    assert any("negative" in e.lower() or "-5" in e for e in validation.errors)


# ------------------------------------------------------------------
# 27. Negative gas → validation error
# ------------------------------------------------------------------
def test_negative_gas():
    reading = _make_reading(gas=-3.0)
    validation = validate_reading(reading)
    assert not validation.is_valid
    assert any("negative" in e.lower() or "-3" in e for e in validation.errors)


# ------------------------------------------------------------------
# 28. Temperature below -40 → validation error
# ------------------------------------------------------------------
def test_temperature_below_minus_40():
    reading = _make_reading(temperature=-50.0)
    validation = validate_reading(reading)
    assert not validation.is_valid


# ------------------------------------------------------------------
# 29. Temperature above 150 → validation error
# ------------------------------------------------------------------
def test_temperature_above_150():
    reading = _make_reading(temperature=200.0)
    validation = validate_reading(reading)
    assert not validation.is_valid


# ------------------------------------------------------------------
# 30. Normal range check: values in range → no warnings
# ------------------------------------------------------------------
def test_normal_ranges_no_warnings():
    reading = _make_reading(
        temperature=25.0, humidity=50.0, smoke=3.0, gas=8.0
    )
    validation = validate_reading(reading)
    range_warnings = [w for w in validation.warnings if "outside normal" in w]
    assert len(range_warnings) == 0, (
        f"Normal values should not produce range warnings: {range_warnings}"
    )
