import time
import json
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List

from iot_trustbench.core.sensor_simulator import generate_reading, SensorReading
from iot_trustbench.core.data_validator import validate_reading
from iot_trustbench.core.safety_engine import classify_event, SafetyDecision, DecisionClass
from iot_trustbench.core.llm_explainer import explain_decision
from iot_trustbench.database.db import (
    init_db, insert_scenario, insert_telemetry, insert_decision,
    insert_llm_explanation, insert_test_result, get_all_scenarios,
    get_recent_decisions, get_test_results, get_evaluation_metrics,
    insert_hardware_reading, upsert_hardware_device, get_hardware_readings,
    get_hardware_devices, get_latest_hardware_reading
)

app = FastAPI(title="IoT-TrustBench", version="1.0.0")

from pathlib import Path
PKG_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = str(PKG_DIR / "static")
TEMPLATES_DIR = str(PKG_DIR / "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


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


@app.on_event("startup")
async def startup():
    await init_db()


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


@app.post("/api/simulate")
async def api_simulate(req: ScenarioRequest):
    start = time.time()
    reading = generate_reading(req.scenario_type, req.device_id)
    validation = validate_reading(reading)
    decision = classify_event(reading, validation)

    scenario_id = await insert_scenario(
        name=req.scenario_name or f"Live {req.scenario_type}",
        scenario_type=req.scenario_type,
        expected_class=req.scenario_type,
        description=f"Live simulation of {req.scenario_type}"
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
async def api_batch_test(req: BatchTestRequest):
    scenario_types = req.scenario_types or [
        "normal", "emergency", "sensor_fault", "spoofing", "uncertain"
    ]
    count = req.count_per_type
    results = []
    total_start = time.time()

    for scenario_type in scenario_types:
        for i in range(count):
            start = time.time()
            reading = generate_reading(scenario_type)
            validation = validate_reading(reading)
            decision = classify_event(reading, validation)
            elapsed_ms = (time.time() - start) * 1000

            is_correct = decision.classification.value == scenario_type
            scenario_id = await insert_scenario(
                name=f"Test {scenario_type} #{i+1}",
                scenario_type=scenario_type,
                expected_class=scenario_type,
                description=f"Batch test scenario"
            )
            await insert_test_result(scenario_id, scenario_type, decision.classification.value, is_correct, elapsed_ms)
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
async def api_reset_history():
    import aiosqlite
    db = await aiosqlite.connect("iot_trustbench.db")
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


@app.post("/api/hardware")
async def api_hardware_reading(reading: HardwareReading):
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
    validation = validate_reading(sensor_reading)
    decision = classify_event(sensor_reading, validation)

    await upsert_hardware_device(reading.device_id)
    reading_id = await insert_hardware_reading(
        reading.device_id,
        reading.model_dump(),
        decision.model_dump()
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
