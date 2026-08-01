from enum import Enum
from typing import List, Optional
from pydantic import BaseModel
from .sensor_simulator import SensorReading, NORMAL_RANGES, REGISTERED_DEVICES
from .data_validator import ValidationResult


class DecisionClass(str, Enum):
    NORMAL = "normal"
    EMERGENCY = "emergency"
    SENSOR_FAULT = "sensor_fault"
    SPOOFING = "spoofing"
    OFFLINE = "offline"
    UNCERTAIN = "uncertain"


class SafetyDecision(BaseModel):
    classification: DecisionClass
    confidence: float
    evidence: List[str]
    requires_human_verification: bool
    validation_result: Optional[dict] = None
    reasoning: str


def detect_emergency(reading: SensorReading) -> Tuple[bool, List[str]]:
    evidence = []
    score = 0

    if reading.temperature > 50:
        evidence.append(f"High temperature: {reading.temperature}°C")
        score += 2
    if reading.smoke > 50:
        evidence.append(f"High smoke level: {reading.smoke}")
        score += 2
    if reading.gas > 50:
        evidence.append(f"High gas level: {reading.gas}")
        score += 2
    if reading.temperature > 40 and reading.smoke > 20:
        evidence.append("Elevated temperature with smoke presence")
        score += 1
    if reading.smoke > 40 and reading.gas > 30:
        evidence.append("High smoke with high gas")
        score += 1

    return score >= 3, evidence


def detect_sensor_fault(reading: SensorReading, validation: ValidationResult) -> Tuple[bool, List[str]]:
    evidence = []
    score = 0

    if reading.temperature > 90:
        evidence.append(f"Impossible temperature: {reading.temperature}°C")
        score += 3
    if reading.temperature < -40:
        evidence.append(f"Impossibly low temperature: {reading.temperature}°C")
        score += 3
    if reading.temperature < 0:
        evidence.append(f"Temperature below freezing: {reading.temperature}°C - likely sensor fault")
        score += 2
    if reading.temperature == 0.0:
        evidence.append("Temperature stuck at zero - likely sensor failure")
        score += 3
    if reading.smoke > 50 and reading.gas < 5:
        evidence.append("High smoke but no gas - inconsistent")
        score += 2
    if reading.temperature > 45 and reading.smoke < 5 and reading.gas < 10:
        evidence.append(f"High temperature ({reading.temperature}°C) with low smoke/gas - likely sensor fault")
        score += 2
    if reading.humidity > 85 and reading.temperature < 35 and reading.smoke <= 5:
        evidence.append(f"High humidity ({reading.humidity}%) with normal temp - possible sensor fault")
        score += 2

    if reading.humidity > 85 and reading.smoke <= 5 and reading.gas <= 10:
        evidence.append(f"High humidity ({reading.humidity}%) with low smoke/gas - sensor fault likely")
        score += 1

    return score >= 2, evidence


def detect_spoofing(reading: SensorReading, validation: ValidationResult) -> Tuple[bool, List[str]]:
    evidence = []
    score = 0

    if reading.device_id not in REGISTERED_DEVICES:
        evidence.append(f"Unknown device ID: {reading.device_id}")
        score += 5
    if reading.humidity > 100:
        evidence.append(f"Physically impossible humidity: {reading.humidity}%")
        score += 5
    if reading.smoke > 100 or reading.gas > 100:
        evidence.append("Sensor values exceed physical maximum")
        score += 5
    if reading.temperature > 120 or reading.temperature < -50:
        evidence.append(f"Impossible temperature: {reading.temperature}°C")
        score += 5

    return score >= 3, evidence


def detect_offline(reading: SensorReading) -> Tuple[bool, List[str]]:
    evidence = []
    from datetime import datetime
    age = datetime.now() - reading.timestamp

    if reading.power_status == "off":
        evidence.append("Device power is off")
        return True, evidence
    if age.total_seconds() > 600:
        evidence.append(f"Data is {age.total_seconds():.0f}s old (stale)")
        return True, evidence

    return False, evidence


def classify_event(
    reading: SensorReading,
    validation: ValidationResult,
    history: List[SensorReading] = None
) -> SafetyDecision:
    evidence = []

    is_offline, offline_evidence = detect_offline(reading)
    if is_offline:
        return SafetyDecision(
            classification=DecisionClass.OFFLINE,
            confidence=0.9,
            evidence=offline_evidence,
            requires_human_verification=True,
            reasoning="Device appears to be offline or sending stale data.",
        )

    is_spoofed, spoof_evidence = detect_spoofing(reading, validation)
    if is_spoofed:
        return SafetyDecision(
            classification=DecisionClass.SPOOFING,
            confidence=0.85,
            evidence=spoof_evidence,
            requires_human_verification=True,
            reasoning="Data appears to be spoofed or from an unauthorized device.",
        )

    is_fault, fault_evidence = detect_sensor_fault(reading, validation)
    is_emergency, emergency_evidence = detect_emergency(reading)

    if is_fault and not is_emergency:
        return SafetyDecision(
            classification=DecisionClass.SENSOR_FAULT,
            confidence=0.8,
            evidence=fault_evidence,
            requires_human_verification=True,
            reasoning="Sensor readings indicate a fault - other sensors do not support emergency.",
        )

    if is_emergency and not is_fault:
        return SafetyDecision(
            classification=DecisionClass.EMERGENCY,
            confidence=0.9,
            evidence=emergency_evidence,
            requires_human_verification=False,
            reasoning="Multiple sensors confirm dangerous conditions.",
        )

    if is_fault and is_emergency:
        return SafetyDecision(
            classification=DecisionClass.UNCERTAIN,
            confidence=0.5,
            evidence=fault_evidence + emergency_evidence,
            requires_human_verification=True,
            reasoning="Conflicting evidence: possible fault masking real emergency.",
        )

    if validation.warnings:
        return SafetyDecision(
            classification=DecisionClass.UNCERTAIN,
            confidence=0.6,
            evidence=[f"Warning: {w}" for w in validation.warnings],
            requires_human_verification=True,
            reasoning="Minor anomalies detected - human verification recommended.",
        )

    borderline_evidence = []
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
        borderline_evidence.append("Both smoke and gas elevated - uncertain cause")
        borderline_score += 1

    if borderline_score >= 2:
        return SafetyDecision(
            classification=DecisionClass.UNCERTAIN,
            confidence=0.55,
            evidence=borderline_evidence,
            requires_human_verification=True,
            reasoning="Readings are borderline - not clearly normal or emergency. Human verification recommended.",
        )

    return SafetyDecision(
        classification=DecisionClass.NORMAL,
        confidence=0.95,
        evidence=["All readings within normal range", "Device is registered", "Data is fresh"],
        requires_human_verification=False,
        reasoning="All sensors report normal values from a registered device.",
    )
