"""End-to-end verification that trusted devices affect classification."""
from iot_trustbench.api.app import app
from fastapi.testclient import TestClient


def test_e2e_trusted_devices_affect_classification():
    with TestClient(app) as c:
        # /docs works
        r = c.get("/docs")
        assert r.status_code == 200

        # /api/evaluation works
        r = c.get("/api/evaluation")
        assert r.status_code == 200

        # Register a trusted device
        c.post(
            "/api/trusted-devices",
            json={"device_id": "E2E-TEST", "device_name": "E2E"},
        )

        # Trusted device → normal (not spoofing)
        r = c.post(
            "/api/hardware",
            json={
                "device_id": "E2E-TEST",
                "temperature": 25.0,
                "humidity": 50.0,
                "smoke": 2.0,
                "gas": 5.0,
            },
        )
        assert r.json()["classification"] == "normal"
        assert r.json()["device_trusted"] is True

        # Disable it → spoofing
        c.put(
            "/api/trusted-devices/E2E-TEST/enable",
            json={"enabled": False},
        )
        r = c.post(
            "/api/hardware",
            json={
                "device_id": "E2E-TEST",
                "temperature": 25.0,
                "humidity": 50.0,
                "smoke": 2.0,
                "gas": 5.0,
            },
        )
        assert r.json()["classification"] == "spoofing"
        assert r.json()["device_trusted"] is False

        # Unknown device → spoofing
        r = c.post(
            "/api/hardware",
            json={
                "device_id": "COMPLETELY-UNKNOWN",
                "temperature": 25.0,
                "humidity": 50.0,
                "smoke": 2.0,
                "gas": 5.0,
            },
        )
        assert r.json()["classification"] == "spoofing"
        assert r.json()["device_trusted"] is False

        # Cleanup
        c.delete("/api/trusted-devices/E2E-TEST")
