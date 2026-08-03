"""API endpoint smoke tests.

Uses the shared ``client`` fixture from conftest.py which provides a
TestClient with a temporary database and proper startup event.
"""


def test_docs_endpoint(client):
    r = client.get("/docs")
    assert r.status_code == 200


def test_home_page(client):
    r = client.get("/")
    assert r.status_code == 200


def test_live_page(client):
    r = client.get("/live")
    assert r.status_code == 200


def test_evaluation_page(client):
    r = client.get("/evaluation")
    assert r.status_code == 200


def test_evaluation_endpoint(client):
    r = client.get("/api/evaluation")
    assert r.status_code == 200


def test_trusted_devices_list_empty(client):
    r = client.get("/api/trusted-devices")
    assert r.status_code == 200
    assert len(r.json().get("devices", [])) == 0


def test_simulate_normal(client):
    r = client.post("/api/simulate", json={"scenario_type": "normal"})
    assert r.status_code == 200
    assert r.json()["decision"]["classification"] == "normal"


def test_batch_test_all_six_classes(client):
    r = client.post("/api/batch-test", json={"count_per_type": 3})
    assert r.status_code == 200
    data = r.json()
    assert data["total_tests"] == 18  # 6 classes * 3
    assert data["accuracy"] > 0


def test_trusted_device_crud(client):
    # Register
    r = client.post(
        "/api/trusted-devices",
        json={"device_id": "TEST-001", "device_name": "Test"},
    )
    assert r.status_code == 200

    # List
    r = client.get("/api/trusted-devices")
    assert len(r.json()["devices"]) >= 1

    # Get single
    r = client.get("/api/trusted-devices/TEST-001")
    assert r.status_code == 200
    assert r.json()["device"]["device_id"] == "TEST-001"

    # Disable
    r = client.put(
        "/api/trusted-devices/TEST-001/enable",
        json={"enabled": False},
    )
    assert r.status_code == 200
    r = client.get("/api/trusted-devices/TEST-001")
    assert r.json()["device"]["enabled"] == 0

    # Re-enable
    r = client.put(
        "/api/trusted-devices/TEST-001/enable",
        json={"enabled": True},
    )
    assert r.status_code == 200

    # Delete
    r = client.delete("/api/trusted-devices/TEST-001")
    assert r.status_code == 200

    # Confirm gone
    r = client.get("/api/trusted-devices/TEST-001")
    assert r.status_code == 404


def test_unknown_hardware_not_auto_trusted(client):
    r = client.post(
        "/api/hardware",
        json={
            "device_id": "UNKNOWN-HW-999",
            "temperature": 25.0,
            "humidity": 50.0,
            "smoke": 2.0,
            "gas": 5.0,
        },
    )
    assert r.status_code == 200
    assert r.json()["classification"] == "spoofing"
    assert r.json()["device_trusted"] is False

    # Should NOT appear in trusted_devices
    r2 = client.get("/api/trusted-devices")
    device_ids = [d["device_id"] for d in r2.json()["devices"]]
    assert "UNKNOWN-HW-999" not in device_ids


def test_trusted_device_not_spoofed(client):
    """A device registered and enabled in trusted_devices must not be
    classified as spoofing for the unknown-device reason."""
    # Register the device
    client.post(
        "/api/trusted-devices",
        json={"device_id": "HW-TRUSTED-001", "device_name": "Trusted HW"},
    )

    # Send normal readings from this device (not in static REGISTERED_DEVICES)
    r = client.post(
        "/api/hardware",
        json={
            "device_id": "HW-TRUSTED-001",
            "temperature": 25.0,
            "humidity": 50.0,
            "smoke": 2.0,
            "gas": 5.0,
        },
    )
    assert r.status_code == 200
    assert r.json()["classification"] == "normal"
    assert r.json()["device_trusted"] is True

    # Cleanup
    client.delete("/api/trusted-devices/HW-TRUSTED-001")


def test_disabled_trusted_device_spoofed(client):
    """A device registered but DISABLED in trusted_devices must be
    classified as spoofing."""
    # Register then disable
    client.post(
        "/api/trusted-devices",
        json={"device_id": "HW-DISABLED-001", "device_name": "Disabled HW"},
    )
    client.put(
        "/api/trusted-devices/HW-DISABLED-001/enable",
        json={"enabled": False},
    )

    # Send readings — should be spoofing
    r = client.post(
        "/api/hardware",
        json={
            "device_id": "HW-DISABLED-001",
            "temperature": 25.0,
            "humidity": 50.0,
            "smoke": 2.0,
            "gas": 5.0,
        },
    )
    assert r.status_code == 200
    assert r.json()["classification"] == "spoofing"
    assert r.json()["device_trusted"] is False

    # Cleanup
    client.delete("/api/trusted-devices/HW-DISABLED-001")


def test_static_list_device_trusted(client):
    """Devices in the static REGISTERED_DEVICES list are always trusted."""
    r = client.post(
        "/api/hardware",
        json={
            "device_id": "DEV-001-TEMP",
            "temperature": 25.0,
            "humidity": 50.0,
            "smoke": 2.0,
            "gas": 5.0,
        },
    )
    assert r.status_code == 200
    assert r.json()["classification"] == "normal"
    assert r.json()["device_trusted"] is True
