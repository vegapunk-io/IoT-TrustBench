import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from iot_trustbench.core.sensor_simulator import generate_reading
from iot_trustbench.core.data_validator import validate_reading
from iot_trustbench.core.safety_engine import classify_event, DecisionClass


def test_normal_reading():
    reading = generate_reading("normal")
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification == DecisionClass.NORMAL, f"Expected NORMAL, got {decision.classification}"


def test_emergency_reading():
    reading = generate_reading("emergency")
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification == DecisionClass.EMERGENCY, f"Expected EMERGENCY, got {decision.classification}"


def test_sensor_fault_reading():
    for _ in range(5):
        reading = generate_reading("sensor_fault")
        validation = validate_reading(reading)
        decision = classify_event(reading, validation)
        if reading.temperature > 90 or reading.temperature < -40 or reading.humidity > 100:
            assert decision.classification in (DecisionClass.SENSOR_FAULT, DecisionClass.UNCERTAIN, DecisionClass.SPOOFING), f"Expected fault classification for extreme value, got {decision.classification}"


def test_spoofing_reading():
    reading = generate_reading("spoofing")
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification == DecisionClass.SPOOFING, f"Expected SPOOFING, got {decision.classification}"


def test_offline_reading():
    reading = generate_reading("offline")
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)
    assert decision.classification == DecisionClass.OFFLINE, f"Expected OFFLINE, got {decision.classification}"


def test_validation_catches_high_humidity():
    reading = generate_reading("spoofing")
    reading.humidity = 150
    validation = validate_reading(reading)
    assert not validation.is_valid
    assert any("100" in e for e in validation.errors)


def test_validation_catches_unknown_device():
    reading = generate_reading("spoofing")
    if reading.humidity > 100 or reading.device_id.startswith("FAKE"):
        validation = validate_reading(reading)
        assert not validation.is_valid


def test_validation_catches_stale_timestamp():
    reading = generate_reading("offline")
    validation = validate_reading(reading)
    assert any("stale" in e.lower() for e in validation.errors)


def test_decision_confidence_range():
    for stype in ["normal", "emergency", "sensor_fault", "spoofing", "offline", "uncertain"]:
        reading = generate_reading(stype)
        validation = validate_reading(reading)
        decision = classify_event(reading, validation)
        assert 0 <= decision.confidence <= 1, f"Confidence out of range for {stype}: {decision.confidence}"


def test_all_classifications_valid():
    for stype in ["normal", "emergency", "sensor_fault", "spoofing", "offline", "uncertain"]:
        reading = generate_reading(stype)
        validation = validate_reading(reading)
        decision = classify_event(reading, validation)
        assert isinstance(decision.classification, DecisionClass), f"Invalid classification type for {stype}"
        assert decision.evidence, f"No evidence for {stype}"
        assert decision.reasoning, f"No reasoning for {stype}"
