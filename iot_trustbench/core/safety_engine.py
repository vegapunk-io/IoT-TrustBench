"""Deterministic safety engine for IoT sensor event classification.

Classifies sensor readings into one of six decision classes:
  normal, emergency, sensor_fault, spoofing, offline, uncertain.

The safety engine is the primary decision-maker. LLM explanations are
optional and never override the classification.
"""

from enum import Enum
from typing import List, Optional, Tuple
from pydantic import BaseModel
from .sensor_simulator import SensorReading, NORMAL_RANGES, REGISTERED_DEVICES
from .data_validator import ValidationResult


class DecisionClass(str, Enum):
    """Enumeration of all possible safety decision classes."""
    NORMAL = "normal"
    EMERGENCY = "emergency"
    SENSOR_FAULT = "sensor_fault"
    SPOOFING = "spoofing"
    OFFLINE = "offline"
    UNCERTAIN = "uncertain"


class SafetyDecision(BaseModel):
    """Result of the safety engine classification."""
    classification: DecisionClass
    confidence: float
    evidence: List[str]
    requires_human_verification: bool
    validation_result: Optional[dict] = None
    reasoning: str


# ---------------------------------------------------------------------------
# Detection helpers – each returns (detected: bool, evidence: List[str])
# ---------------------------------------------------------------------------

def detect_offline(reading: SensorReading) -> Tuple[bool, List[str]]:
    """Detect if the device is offline or sending stale data.

    Offline conditions:
      - power_status == 'off'
      - timestamp is older than 10 minutes
      - timestamp is in the future (clock skew / replay)
    """
    evidence: List[str] = []
    from datetime import datetime
    now = datetime.now()
    age = now - reading.timestamp

    # Future timestamp – indicates clock manipulation or replay
    if reading.timestamp > now:
        evidence.append(f"Timestamp is in the future: {reading.timestamp}")
        return True, evidence

    if reading.power_status == "off":
        evidence.append("Device power is off")
        return True, evidence

    if age.total_seconds() > 600:
        evidence.append(f"Data is {age.total_seconds():.0f}s old (stale, max 600s)")
        return True, evidence

    return False, evidence


def detect_spoofing(
    reading: SensorReading,
    validation: ValidationResult,
    trusted_device_ids: Optional[List[str]] = None,
) -> Tuple[bool, List[str]]:
    """Detect spoofed or unauthorized data.

    Spoofing indicators:
      - Device ID not in the trusted list (database or static fallback)
      - Physically impossible humidity (> 100)
      - Sensor values exceeding physical maximums
      - Impossible temperature extremes
    """
    evidence: List[str] = []
    score = 0

    # Determine the effective set of known device IDs
    known_ids = set(REGISTERED_DEVICES)
    if trusted_device_ids:
        known_ids.update(trusted_device_ids)

    if reading.device_id not in known_ids:
        evidence.append(f"Unknown device ID: {reading.device_id}")
        score += 5

    if reading.humidity > 100:
        evidence.append(f"Physically impossible humidity: {reading.humidity}%")
        score += 5

    if reading.smoke > 100 or reading.gas > 100:
        evidence.append("Sensor values exceed physical maximum (>100)")
        score += 5

    if reading.temperature > 120 or reading.temperature < -50:
        evidence.append(f"Impossible temperature: {reading.temperature}°C")
        score += 5

    return score >= 3, evidence


def detect_sensor_fault(
    reading: SensorReading,
    validation: ValidationResult,
) -> Tuple[bool, List[str]]:
    """Detect sensor malfunction based on individual sensor anomalies.

    A sensor fault is indicated when a single sensor produces readings that
    are physically implausible or inconsistent with the other sensors, while
    the other sensors remain in a normal or non-emergency range.

    Key principle: high temperature alone with normal smoke and gas is more
    likely a sensor fault than a real emergency.
    """
    evidence: List[str] = []
    score = 0

    # --- Temperature anomalies ---
    if reading.temperature > 90:
        evidence.append(f"Impossible temperature: {reading.temperature}°C (sensor failure)")
        score += 3
    elif reading.temperature < -40:
        evidence.append(f"Impossibly low temperature: {reading.temperature}°C (sensor failure)")
        score += 3
    elif reading.temperature == 0.0:
        evidence.append("Temperature stuck at zero – likely sensor failure")
        score += 3
    elif reading.temperature < 0:
        evidence.append(f"Temperature below freezing: {reading.temperature}°C – likely sensor fault")
        score += 2

    # High temperature with low smoke/gas: isolated sensor anomaly
    if reading.temperature > 45 and reading.smoke < 5 and reading.gas < 10:
        evidence.append(
            f"High temperature ({reading.temperature}°C) with low smoke/gas – isolated sensor fault"
        )
        score += 2

    # --- Humidity anomalies ---
    if reading.humidity > 85 and reading.temperature < 35 and reading.smoke <= 5:
        evidence.append(
            f"High humidity ({reading.humidity}%) with normal temp – possible sensor fault"
        )
        score += 2

    if reading.humidity > 85 and reading.smoke <= 5 and reading.gas <= 10:
        evidence.append(
            f"High humidity ({reading.humidity}%) with low smoke/gas – sensor fault likely"
        )
        score += 1

    # --- Cross-sensor inconsistency ---
    if reading.smoke > 50 and reading.gas < 5:
        evidence.append("High smoke but very low gas – inconsistent readings")
        score += 2

    return score >= 2, evidence


def detect_emergency(reading: SensorReading) -> Tuple[bool, List[str]]:
    """Detect a genuine emergency requiring multi-sensor corroboration.

    A real emergency should have supporting evidence from more than one
    sensor. A very high temperature alone does NOT automatically qualify
    as a real emergency if smoke and gas are normal – that pattern is
    more consistent with a sensor fault.

    Emergency requires a composite score from multiple danger indicators.
    """
    evidence: List[str] = []
    score = 0

    # Primary danger indicators (each contributes to the score)
    if reading.temperature > 50:
        evidence.append(f"High temperature: {reading.temperature}°C")
        score += 2
    if reading.smoke > 50:
        evidence.append(f"High smoke level: {reading.smoke}")
        score += 2
    if reading.gas > 50:
        evidence.append(f"High gas level: {reading.gas}")
        score += 2

    # Secondary corroboration (cross-sensor evidence)
    if reading.temperature > 40 and reading.smoke > 20:
        evidence.append("Elevated temperature with smoke presence")
        score += 1
    if reading.smoke > 40 and reading.gas > 30:
        evidence.append("High smoke with high gas")
        score += 1
    if reading.temperature > 40 and reading.gas > 20:
        evidence.append("Elevated temperature with gas presence")
        score += 1

    # Require a score of >= 3 for emergency, ensuring multi-sensor evidence
    # A single high temperature (score=2) is NOT enough – that's a fault
    return score >= 3, evidence


def classify_event(
    reading: SensorReading,
    validation: ValidationResult,
    history: Optional[List[SensorReading]] = None,
    trusted_device_ids: Optional[List[str]] = None,
) -> SafetyDecision:
    """Classify a sensor reading into one of six decision classes.

    Decision order (highest priority first):
      1. OFFLINE – device not communicating or stale data
      2. SPOOFING – unauthorized device or impossible values
      3. SENSOR_FAULT – single sensor anomaly, others normal
      4. EMERGENCY – multi-sensor danger corroboration
      5. UNCERTAIN – conflicting evidence or borderline readings
      6. NORMAL – all readings within normal range

    When sensor_fault and emergency conflict, the result is UNCERTAIN
    because a fault could be masking a real emergency.
    """
    evidence: List[str] = []

    # --- 1. OFFLINE check (highest priority) ---
    is_offline, offline_evidence = detect_offline(reading)
    if is_offline:
        return SafetyDecision(
            classification=DecisionClass.OFFLINE,
            confidence=0.9,
            evidence=offline_evidence,
            requires_human_verification=True,
            reasoning="Device appears to be offline or sending stale data.",
        )

    # --- 2. SPOOFING check ---
    is_spoofed, spoof_evidence = detect_spoofing(reading, validation, trusted_device_ids)
    if is_spoofed:
        return SafetyDecision(
            classification=DecisionClass.SPOOFING,
            confidence=0.85,
            evidence=spoof_evidence,
            requires_human_verification=True,
            reasoning="Data appears to be spoofed or from an unauthorized device.",
        )

    # --- 3 & 4. SENSOR_FAULT and EMERGENCY (may conflict) ---
    is_fault, fault_evidence = detect_sensor_fault(reading, validation)
    is_emergency, emergency_evidence = detect_emergency(reading)

    # Fault only, no emergency: sensor malfunction
    if is_fault and not is_emergency:
        return SafetyDecision(
            classification=DecisionClass.SENSOR_FAULT,
            confidence=0.8,
            evidence=fault_evidence,
            requires_human_verification=True,
            reasoning="Sensor readings indicate a fault – other sensors do not support emergency.",
        )

    # Emergency only, no fault: confirmed danger
    if is_emergency and not is_fault:
        return SafetyDecision(
            classification=DecisionClass.EMERGENCY,
            confidence=0.9,
            evidence=emergency_evidence,
            requires_human_verification=False,
            reasoning="Multiple sensors confirm dangerous conditions.",
        )

    # Both fault and emergency: conflicting evidence → uncertain
    if is_fault and is_emergency:
        return SafetyDecision(
            classification=DecisionClass.UNCERTAIN,
            confidence=0.5,
            evidence=fault_evidence + emergency_evidence,
            requires_human_verification=True,
            reasoning="Conflicting evidence: possible fault masking real emergency. Human verification required.",
        )

    # --- 5. UNCERTAIN from validation warnings ---
    if validation.warnings:
        return SafetyDecision(
            classification=DecisionClass.UNCERTAIN,
            confidence=0.6,
            evidence=[f"Warning: {w}" for w in validation.warnings],
            requires_human_verification=True,
            reasoning="Minor anomalies detected – human verification recommended.",
        )

    # --- Borderline / uncertain zone ---
    borderline_evidence: List[str] = []
    borderline_score = 0
    if 35 <= reading.temperature <= 50:
        borderline_evidence.append(f"Elevated temperature: {reading.temperature}°C")
        borderline_score += 1
    if 5 <= reading.smoke <= 30:
        borderline_evidence.append(f"Moderate smoke level: {reading.smoke}")
        borderline_score += 1
    if 10 <= reading.gas <= 40:
        borderline_evidence.append(f"Moderate gas level: {reading.gas}")
        borderline_score += 1
    if reading.smoke > 10 and reading.gas > 10:
        borderline_evidence.append("Both smoke and gas elevated – uncertain cause")
        borderline_score += 1

    if borderline_score >= 2:
        return SafetyDecision(
            classification=DecisionClass.UNCERTAIN,
            confidence=0.55,
            evidence=borderline_evidence,
            requires_human_verification=True,
            reasoning="Readings are borderline – not clearly normal or emergency. Human verification recommended.",
        )

    # --- 6. NORMAL ---
    return SafetyDecision(
        classification=DecisionClass.NORMAL,
        confidence=0.95,
        evidence=["All readings within normal range", "Device is registered", "Data is fresh"],
        requires_human_verification=False,
        reasoning="All sensors report normal values from a registered device.",
    )
