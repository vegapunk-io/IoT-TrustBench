import os
import json
from typing import Optional
from .safety_engine import SafetyDecision, DecisionClass


LLM_BACKEND = os.getenv("LLM_BACKEND", "local")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.0-flash")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")


def build_prompt(reading: dict, decision: SafetyDecision) -> str:
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

TASK: Write a 2-3 sentence plain-language explanation of this classification.
Do NOT change the classification. Do NOT invent facts. Be concise and clear."""


async def call_llm(prompt: str) -> str:
    if LLM_BACKEND == "none":
        return _generate_local_explanation(prompt)

    try:
        import httpx
        if LLM_BACKEND == "gemini":
            return await _call_gemini(prompt)
        elif LLM_BACKEND == "openai":
            return await _call_openai_compatible(prompt)
        else:
            return _generate_local_explanation(prompt)
    except Exception as e:
        return _generate_local_explanation(prompt)


async def _call_gemini(prompt: str) -> str:
    import httpx
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{LLM_MODEL}:generateContent?key={LLM_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _call_openai_compatible(prompt: str) -> str:
    import httpx
    url = f"{LLM_BASE_URL}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _generate_local_explanation(prompt: str) -> str:
    if DecisionClass.EMERGENCY.value in prompt.lower():
        return "Multiple sensors indicate dangerous conditions. Immediate attention recommended."
    elif DecisionClass.SENSOR_FAULT.value in prompt.lower():
        return "Sensor readings are inconsistent with other evidence, indicating a likely sensor malfunction."
    elif DecisionClass.SPOOFING.value in prompt.lower():
        return "Data appears to originate from an unauthorized or spoofed device."
    elif DecisionClass.OFFLINE.value in prompt.lower():
        return "The device is not sending current data and may be offline."
    elif DecisionClass.UNCERTAIN.value in prompt.lower():
        return "Evidence is mixed. Human verification is recommended before taking action."
    else:
        return "All sensors report normal readings from a verified device. No action needed."


async def explain_decision(reading: dict, decision: SafetyDecision) -> dict:
    prompt = build_prompt(reading, decision)
    explanation = await call_llm(prompt)
    return {
        "explanation": explanation,
        "prompt_used": prompt,
        "backend": LLM_BACKEND,
    }
