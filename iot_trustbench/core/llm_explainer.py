"""LLM explanation module for IoT-TrustBench.

Provides optional LLM-generated explanations for safety decisions.
The LLM is NEVER used to override the deterministic safety engine.

Supported backends:
  - local: rule-based local explanation (no API key required)
  - gemini: Google Gemini API
  - openai: OpenAI-compatible API

The system works fully with LLM_BACKEND=local or none.
"""

import os
import time
from typing import Optional

from .safety_engine import SafetyDecision, DecisionClass

# Configuration from environment variables
LLM_BACKEND = os.getenv("LLM_BACKEND", "local")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.0-flash")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "10"))


def build_prompt(reading: dict, decision: SafetyDecision) -> str:
    """Build a safe prompt for the LLM explanation.

    The prompt explicitly instructs the LLM to:
      - NOT change the classification
      - NOT invent facts
      - NOT give physical-device control instructions
      - State that human verification is required when the decision says so
    """
    return f"""You are an IoT safety assistant. A sensor reading was analyzed and classified.

SENSOR DATA:
- Temperature: {reading.get('temperature')}°C
- Humidity: {reading.get('humidity')}%
- Smoke: {reading.get('smoke')}
- Gas: {reading.get('gas')}
- Motion: {reading.get('motion')}
- Door: {reading.get('door_status')}
- Power: {reading.get('power_status')}
- Device: {reading.get('device_id')}

SYSTEM CLASSIFICATION: {decision.classification.value.upper()}
CONFIDENCE: {decision.confidence:.0%}
EVIDENCE: {'; '.join(decision.evidence)}
REQUIRES HUMAN VERIFICATION: {'Yes' if decision.requires_human_verification else 'No'}

TASK: Write a 2-3 sentence plain-language explanation of this classification.

RULES:
1. Do NOT change the classification. The system has already decided.
2. Do NOT invent facts. Only describe what the data shows.
3. Do NOT give instructions for controlling physical devices.
4. If the decision says human verification is required, you MUST state that.
5. Be concise and clear. Avoid jargon."""


async def call_llm(prompt: str) -> tuple:
    """Call the configured LLM backend with timeout and safe fallback.

    Returns (explanation_text, backend_used).
    """
    if LLM_BACKEND == "none" or LLM_BACKEND == "local":
        return _generate_local_explanation(prompt), "local"

    try:
        if LLM_BACKEND == "gemini":
            result = await _call_gemini(prompt)
            return result, "gemini"
        elif LLM_BACKEND == "openai":
            result = await _call_openai_compatible(prompt)
            return result, "openai"
        else:
            return _generate_local_explanation(prompt), "local"
    except Exception:
        return _generate_local_explanation(prompt), "local"


async def _call_gemini(prompt: str) -> str:
    """Call the Google Gemini API."""
    import httpx

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{LLM_MODEL}:generateContent?key={LLM_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=LLM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _call_openai_compatible(prompt: str) -> str:
    """Call an OpenAI-compatible API."""
    import httpx

    url = f"{LLM_BASE_URL}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers, timeout=LLM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _generate_local_explanation(prompt: str) -> str:
    """Generate a rule-based explanation without any external API.

    This is the default fallback that requires no API key.
    """
    if "EMERGENCY" in prompt.upper():
        return (
            "Multiple sensors indicate dangerous conditions requiring immediate attention. "
            "The system has classified this as an emergency based on corroborating evidence."
        )
    elif "SENSOR_FAULT" in prompt.upper():
        return (
            "Sensor readings are inconsistent with other evidence, indicating a likely "
            "sensor malfunction. Other sensors do not support an emergency condition."
        )
    elif "SPOOFING" in prompt.upper():
        return (
            "Data appears to originate from an unauthorized or spoofed device. "
            "The device ID is not in the trusted device registry."
        )
    elif "OFFLINE" in prompt.upper():
        return (
            "The device is not sending current data and may be offline. "
            "The timestamp indicates stale or missing communication."
        )
    elif "UNCERTAIN" in prompt.upper():
        return (
            "Evidence is mixed or conflicting. Human verification is recommended "
            "before taking any action based on this reading."
        )
    else:
        return (
            "All sensors report normal readings from a verified device. "
            "No anomalies detected. No action required."
        )


async def explain_decision(reading: dict, decision: SafetyDecision) -> dict:
    """Generate an explanation for a safety decision.

    Returns a dict with explanation, prompt_used, backend, and generation_time_ms.
    """
    prompt = build_prompt(reading, decision)
    start = time.time()
    explanation, backend = await call_llm(prompt)
    elapsed_ms = (time.time() - start) * 1000

    return {
        "explanation": explanation,
        "prompt_used": prompt,
        "backend": backend,
        "generation_time_ms": round(elapsed_ms, 2),
    }
