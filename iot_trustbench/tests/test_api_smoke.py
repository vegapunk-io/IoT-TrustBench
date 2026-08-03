"""Quick smoke test for all API endpoints."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from iot_trustbench.api.app import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_docs_endpoint():
    r = client.get("/docs")
    assert r.status_code == 200


def test_evaluation_endpoint():
    r = client.get("/api/evaluation")
    assert r.status_code == 200


def test_trusted_devices_list_empty():
    r = client.get("/api/trusted-devices")
    assert r.status_code == 200
    assert len(r.json().get("devices", [])) >= 0


def test_simulate_normal():
    r = client.post("/api/simulate", json={"scenario_type": "normal"})
    assert r.status_code == 200
    assert r.json()["decision"]["classification"] == "normal"


def test_batch_test_all_six_classes():
    r = client.post("/api/batch-test", json={"count_per_type": 3})
    assert r.status_code == 200
    data = r.json()
    assert data["total_tests"] == 18  # 6 classes * 3
    assert data["accuracy"] > 0


def test_trusted_device_crud():
    # Register
    r = client.post("/api/trusted-devices", json={"device_id": "TEST-001", "device_name": "Test"})
    assert r.status_code == 200

    # List
    r = client.get("/api/trusted-devices")
    assert len(r.json()["devices"]) >= 1

    # Disable
    r = client.put("/api/trusted-devices/TEST-001/enable", json={"enabled": False})
    assert r.status_code == 200
    r = client.get("/api/trusted-devices/TEST-001")
    assert r.json()["device"]["enabled"] == 0

    # Re-enable
    r = client.put("/api/trusted-devices/TEST-001/enable", json={"enabled": True})
    assert r.status_code == 200

    # Delete
    r = client.delete("/api/trusted-devices/TEST-001")
    assert r.status_code == 200


def test_unknown_hardware_not_auto_trusted():
    r = client.post("/api/hardware", json={
        "device_id": "UNKNOWN-HW-999", "temperature": 25.0,
        "humidity": 50.0, "smoke": 2.0, "gas": 5.0
    })
    assert r.status_code == 200
    assert r.json()["classification"] == "spoofing"

    # Should NOT appear in trusted_devices
    r2 = client.get("/api/trusted-devices")
    device_ids = [d["device_id"] for d in r2.json()["devices"]]
    assert "UNKNOWN-HW-999" not in device_ids


def test_home_page():
    r = client.get("/")
    assert r.status_code == 200


def test_live_page():
    r = client.get("/live")
    assert r.status_code == 200


def test_evaluation_page():
    r = client.get("/evaluation")
    assert r.status_code == 200
