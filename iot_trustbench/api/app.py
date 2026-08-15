"""FastAPI application for IoT-TrustBench.

Provides the web dashboard, REST API, and integration points for
the IoT safety classification system.
"""

import os
import secrets
import time
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from iot_trustbench.core.sensor_simulator import SensorReading, generate_reading
from iot_trustbench.core.data_validator import validate_reading
from iot_trustbench.core.safety_engine import classify_event, DecisionClass, SafetyDecision
from iot_trustbench.core.llm_explainer import explain_decision
from iot_trustbench.database.db import (
    init_db,
    insert_scenario,
    insert_telemetry,
    insert_decision,
    insert_llm_explanation,
    insert_test_result,
    get_all_scenarios,
    get_recent_decisions,
    get_test_results,
    get_evaluation_metrics,
    insert_hardware_reading,
    upsert_hardware_device,
    get_hardware_readings,
    get_hardware_devices,
    get_latest_hardware_reading,
    register_trusted_device,
    get_trusted_devices,
    get_trusted_device_ids,
    get_disabled_device_ids,
    enable_trusted_device,
    disable_trusted_device,
    remove_trusted_device,
)

app = FastAPI(title="IoT-TrustBench", version="1.2.0")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: JSONResponse(
    status_code=429,
    content={"detail": "Rate limit exceeded. Please try again later."}
))

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = str(PKG_DIR / "static")
TEMPLATES_DIR = str(PKG_DIR / "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ScenarioRequest(BaseModel):
    scenario_type: str
    device_id: Optional[str] = None
    scenario_name: Optional[str] = None


class BatchTestRequest(BaseModel):
    scenario_types: Optional[List[str]] = None
    count_per_type: int = 20


class HardwareReading(BaseModel):
    device_id: str
    temperature: float = 0.0
    humidity: float = 0.0
    smoke: float = 0.0
    gas: float = 0.0
    motion: bool = False
    door_status: str = "closed"
    power_status: str = "on"


class TrustedDeviceRequest(BaseModel):
    device_id: str
    device_name: str = ""
    device_type: str = "esp32"
    token_hash: Optional[str] = None


ALL_SCENARIO_TYPES = [
    "normal", "emergency", "sensor_fault", "spoofing", "offline", "uncertain"
]

ADMIN_KEY = os.getenv("ADMIN_KEY", "")


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def verify_admin_key(request: Request):
    """Verify admin API key for protected endpoints."""
    if not ADMIN_KEY:
        return
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = auth_header[7:]
    if not secrets.compare_digest(token, ADMIN_KEY):
        raise HTTPException(status_code=403, detail="Invalid admin key")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:
    await init_db()


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "home.html")


@app.get("/live", response_class=HTMLResponse)
async def live_simulation(request: Request):
    return templates.TemplateResponse(request, "live.html")


@app.get("/scenarios", response_class=HTMLResponse)
async def scenario_runner(request: Request):
    return templates.TemplateResponse(request, "scenarios.html")


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    return templates.TemplateResponse(request, "history.html")


@app.get("/evaluation", response_class=HTMLResponse)
async def evaluation_page(request: Request):
    return templates.TemplateResponse(request, "evaluation.html")


@app.get("/hardware", response_class=HTMLResponse)
async def hardware_page(request: Request):
    return templates.TemplateResponse(request, "hardware.html")


@app.get("/devices", response_class=HTMLResponse)
async def devices_page(request: Request):
    return templates.TemplateResponse(request, "devices.html")


# ---------------------------------------------------------------------------
# Simulation API
# ---------------------------------------------------------------------------

@app.post("/api/simulate")
@limiter.limit("30/minute")
async def api_simulate(request: Request, req: ScenarioRequest):
    """Run a simulated test for a single scenario type."""
    start = time.time()
    reading = generate_reading(req.scenario_type, req.device_id)

    # Fetch trusted device context
    trusted_ids = await get_trusted_device_ids()
    disabled_ids = await get_disabled_device_ids()

    validation = validate_reading(reading, trusted_device_ids=trusted_ids, disabled_device_ids=disabled_ids)
    decision = classify_event(reading, validation, trusted_device_ids=trusted_ids)

    scenario_id = await insert_scenario(
        name=req.scenario_name or f"Live {req.scenario_type}",
        scenario_type=req.scenario_type,
        expected_class=req.scenario_type,
        description=f"Live simulation of {req.scenario_type}",
    )
    telemetry_id = await insert_telemetry(scenario_id, reading.model_dump(mode="json"))
    decision_id = await insert_decision(scenario_id, telemetry_id, decision.model_dump())

    llm_result = await explain_decision(reading.model_dump(mode="json"), decision)
    await insert_llm_explanation(decision_id, llm_result)

    elapsed_ms = (time.time() - start) * 1000
    return {
        "reading": reading.model_dump(mode="json"),
        "validation": {
            "is_valid": validation.is_valid,
            "errors": validation.errors,
            "warnings": validation.warnings,
            "checks_passed": validation.checks_passed,
        },
        "decision": decision.model_dump(),
        "llm_explanation": llm_result["explanation"],
        "llm_backend": llm_result["backend"],
        "execution_time_ms": round(elapsed_ms, 2),
    }


@app.get("/api/scenarios")
async def api_list_scenarios():
    scenarios = await get_all_scenarios()
    return {"scenarios": scenarios}


@app.get("/api/decisions")
async def api_recent_decisions(limit: int = 50):
    decisions = await get_recent_decisions(limit)
    return {"decisions": decisions}


@app.get("/api/evaluation")
async def api_evaluation():
    metrics = await get_evaluation_metrics()
    return metrics


@app.post("/api/batch-test")
@limiter.limit("10/minute")
async def api_batch_test(request: Request, req: BatchTestRequest):
    """Run batch evaluation across all six scenario types."""
    scenario_types = req.scenario_types or ALL_SCENARIO_TYPES
    count = req.count_per_type
    results = []
    total_start = time.time()

    # Fetch trusted device context once
    trusted_ids = await get_trusted_device_ids()
    disabled_ids = await get_disabled_device_ids()

    for scenario_type in scenario_types:
        for i in range(count):
            start = time.time()
            reading = generate_reading(scenario_type)
            validation = validate_reading(
                reading, trusted_device_ids=trusted_ids, disabled_device_ids=disabled_ids
            )
            decision = classify_event(reading, validation, trusted_device_ids=trusted_ids)
            elapsed_ms = (time.time() - start) * 1000

            is_correct = decision.classification.value == scenario_type
            scenario_id = await insert_scenario(
                name=f"Test {scenario_type} #{i + 1}",
                scenario_type=scenario_type,
                expected_class=scenario_type,
                description="Batch test scenario",
            )
            await insert_test_result(
                scenario_id, scenario_type, decision.classification.value, is_correct, elapsed_ms
            )
            results.append({
                "scenario_type": scenario_type,
                "expected": scenario_type,
                "predicted": decision.classification.value,
                "is_correct": is_correct,
                "execution_time_ms": round(elapsed_ms, 2),
            })

    total_ms = (time.time() - total_start) * 1000
    correct = sum(1 for r in results if r["is_correct"])
    metrics = await get_evaluation_metrics()

    return {
        "total_tests": len(results),
        "correct": correct,
        "accuracy": round(correct / len(results), 3) if results else 0,
        "total_time_ms": round(total_ms, 2),
        "metrics": metrics,
        "results": results[:100],
    }


@app.get("/api/test-results")
async def api_test_results():
    results = await get_test_results()
    return {"results": results}


@app.post("/api/reset-history")
async def api_reset_history(request: Request, _=Depends(verify_admin_key)):
    from iot_trustbench.database.db import DB_PATH
    import aiosqlite
    db = await aiosqlite.connect(DB_PATH)
    await db.executescript("""
        DELETE FROM llm_explanations;
        DELETE FROM test_results;
        DELETE FROM decisions;
        DELETE FROM telemetry;
        DELETE FROM scenarios;
    """)
    await db.commit()
    await db.close()
    return {"status": "History cleared"}


# ---------------------------------------------------------------------------
# Hardware API
# ---------------------------------------------------------------------------

@app.post("/api/hardware")
@limiter.limit("60/minute")
async def api_hardware_reading(request: Request, reading: HardwareReading):
    """Receive data from an ESP32 hardware node.

    Unknown devices are NOT automatically trusted.
    They will be classified as spoofing.
    """
    start = time.time()
    sensor_reading = SensorReading(
        temperature=reading.temperature,
        humidity=reading.humidity,
        smoke=reading.smoke,
        gas=reading.gas,
        motion=reading.motion,
        door_status=reading.door_status,
        power_status=reading.power_status,
        device_id=reading.device_id,
        timestamp=datetime.now(),
    )

    # Fetch trusted device context
    trusted_ids = await get_trusted_device_ids()
    disabled_ids = await get_disabled_device_ids()

    validation = validate_reading(sensor_reading, trusted_device_ids=trusted_ids, disabled_device_ids=disabled_ids)
    decision = classify_event(sensor_reading, validation, trusted_device_ids=trusted_ids)

    await upsert_hardware_device(reading.device_id)
    reading_id = await insert_hardware_reading(
        reading.device_id, reading.model_dump(), decision.model_dump()
    )

    elapsed_ms = (time.time() - start) * 1000
    return {
        "reading_id": reading_id,
        "classification": decision.classification.value,
        "confidence": decision.confidence,
        "evidence": decision.evidence,
        "requires_human_verification": decision.requires_human_verification,
        "reasoning": decision.reasoning,
        "execution_time_ms": round(elapsed_ms, 2),
    }


@app.get("/api/hardware/readings")
async def api_hardware_readings(limit: int = 50, device_id: str = None):
    readings = await get_hardware_readings(limit)
    return {"readings": readings}


@app.get("/api/hardware/devices")
async def api_hardware_devices():
    devices = await get_hardware_devices()
    return {"devices": devices}


@app.get("/api/hardware/latest")
async def api_hardware_latest(device_id: str = None):
    reading = await get_latest_hardware_reading(device_id)
    return {"reading": reading}


# ---------------------------------------------------------------------------
# Trusted device management API (admin-protected)
# ---------------------------------------------------------------------------

@app.post("/api/trusted-devices")
async def api_register_trusted_device(request: Request, req: TrustedDeviceRequest, _=Depends(verify_admin_key)):
    """Register a new trusted device.

    Only pre-registered devices will be classified as non-spoofing.
    Unknown devices posting to /api/hardware remain classified as spoofing.
    """
    try:
        row_id = await register_trusted_device(
            device_id=req.device_id,
            device_name=req.device_name,
            device_type=req.device_type,
            token_hash=req.token_hash,
        )
        return {
            "status": "registered",
            "device_id": req.device_id,
            "id": row_id,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to register device: {str(e)}")


@app.get("/api/trusted-devices")
async def api_list_trusted_devices():
    """List all trusted devices."""
    devices = await get_trusted_devices()
    return {"devices": devices}


@app.post("/api/trusted-devices/{device_id}/enable")
async def api_enable_trusted_device(request: Request, device_id: str, _=Depends(verify_admin_key)):
    """Re-enable a trusted device."""
    changed = await enable_trusted_device(device_id)
    if not changed:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return {"status": "enabled", "device_id": device_id}


@app.post("/api/trusted-devices/{device_id}/disable")
async def api_disable_trusted_device(request: Request, device_id: str, _=Depends(verify_admin_key)):
    """Disable a trusted device.

    A disabled device will fail validation and be flagged in classification.
    """
    changed = await disable_trusted_device(device_id)
    if not changed:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return {"status": "disabled", "device_id": device_id}


@app.delete("/api/trusted-devices/{device_id}")
async def api_remove_trusted_device(request: Request, device_id: str, _=Depends(verify_admin_key)):
    """Remove a device from the trusted list."""
    changed = await remove_trusted_device(device_id)
    if not changed:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return {"status": "removed", "device_id": device_id}
