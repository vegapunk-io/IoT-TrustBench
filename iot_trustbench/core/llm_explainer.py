import os
import time
from typing import Optional
from .safety_engine import SafetyDecision, DecisionClass


LLM_BACKEND = os.getenv("LLM_BACKEND", "local")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.0-flash")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")


def build_prompt(reading: dict, decision: SafetyDecision) -> str:
    """Build a safe prompt for the LLM explainer.

    The prompt explicitly instructs the model to:
    - NOT change the classification
    - NOT invent facts
    - NOT give physical-device control instructions
    - State that human verification is required when the decision says so
    """
    human_note = ""
    if decision.requires_human_verification:
        human_note = (
            "\nNOTE: This decision REQUIRES human verification. "
            "Your explanation must state this."
        )

    return f"""You are an IoT safety assistant. A sensor reading was analyzed and classified by a deterministic safety engine.

SENSOR DATA:
- Temperature: {reading.get('temperature')}\u00b0C
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

TASK: Write a 2-3 sentence plain-language explanation of this classification.

STRICT RULES:
1. Do NOT change the classification.
2. Do NOT invent facts not present in the data above.
3. Do NOT give physical-device control instructions.
4. If the decision requires human verification, state that clearly.
{human_note}
Be concise and clear."""


async def call_llm(prompt: str) -> str:
    """Call the configured LLM backend with timeout and safe fallback.

    Returns the explanation text.  On any failure the local template
    explanation is returned instead.
    """
    if LLM_BACKEND == "none":
        return _generate_local_explanation(prompt)

    try:
        if LLM_BACKEND == "gemini":
            return await _call_gemini(prompt)
        elif LLM_BACKEND == "openai":
            return await _call_openai_compatible(prompt)
        else:
            return _generate_local_explanation(prompt)
    except Exception:
        return _generate_local_explanation(prompt)


async def _call_gemini(prompt: str) -> str:
    """Call Google Generative AI REST API with a 15-second timeout."""
    import httpx

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{LLM_MODEL}:generateContent?key={LLM_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _call_openai_compatible(prompt: str) -> str:
    """Call an OpenAI-compatible API with a 15-second timeout."""
    import httpx

    url = f"{LLM_BASE_URL}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url, json=payload, headers=headers, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _generate_local_explanation(prompt: str) -> str:
    """Generate a local template explanation (no API key required)."""
    if DecisionClass.EMERGENCY.value in prompt.lower():
        return (
            "Multiple sensors indicate dangerous conditions. "
            "Immediate attention recommended."
        )
    elif DecisionClass.SENSOR_FAULT.value in prompt.lower():
        return (
            "Sensor readings are inconsistent with other evidence, "
            "indicating a likely sensor malfunction."
        )
    elif DecisionClass.SPOOFING.value in prompt.lower():
        return (
            "Data appears to originate from an unauthorized or spoofed device."
        )
    elif DecisionClass.OFFLINE.value in prompt.lower():
        return (
            "The device is not sending current data and may be offline."
        )
    elif DecisionClass.UNCERTAIN.value in prompt.lower():
        return (
            "Evidence is mixed. Human verification is recommended "
            "before taking action."
        )
    else:
        return (
            "All sensors report normal readings from a verified device. "
            "No action needed."
        )


async def explain_decision(
    reading: dict, decision: SafetyDecision
) -> dict:
    """Generate an LLM explanation for a safety decision.

    Returns a dict with explanation text, prompt used, backend name,
    and generation time in milliseconds.
    """
    prompt = build_prompt(reading, decision)
    start = time.time()
    explanation = await call_llm(prompt)
    elapsed_ms = (time.time() - start) * 1000
    return {
        "explanation": explanation,
        "prompt_used": prompt,
        "backend": LLM_BACKEND,
        "generation_time_ms": round(elapsed_ms, 2),
    }
