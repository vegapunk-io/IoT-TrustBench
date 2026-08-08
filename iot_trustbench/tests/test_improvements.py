"""Tests for improvements: consistency-validator fix, API validation,
admin-key constant-time comparison, reset-history DB path, and the CLI.
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from iot_trustbench.core.sensor_simulator import SensorReading
from iot_trustbench.core.data_validator import validate_reading
from iot_trustbench.core.safety_engine import classify_event, DecisionClass


def _make_reading(**overrides) -> SensorReading:
    """Create a SensorReading with defaults, overridden as needed."""
    defaults = dict(
        temperature=25.0,
        humidity=50.0,
        smoke=2.0,
        gas=3.0,
        motion=False,
        door_status="closed",
        power_status="on",
        device_id="DEV-001-TEMP",
        timestamp=datetime.now(),
    )
    defaults.update(overrides)
    return SensorReading(**defaults)


# ----------------------------------------------------------------------
# validate_consistency fix: the "internally consistent" pass message must
# NOT be recorded when a consistency warning was raised.
# ----------------------------------------------------------------------
class TestConsistencyValidation:
    def test_consistent_reading_gets_pass_message(self):
        result = validate_reading(_make_reading())
        assert "Sensor readings are internally consistent" in result.checks_passed

    def test_high_smoke_low_gas_warns_and_skips_pass(self):
        result = validate_reading(_make_reading(smoke=60.0, gas=2.0))
        assert any("may indicate sensor issue" in w for w in result.warnings)
        assert "Sensor readings are internally consistent" not in result.checks_passed

    def test_hot_humid_warns_and_skips_pass(self):
        result = validate_reading(_make_reading(temperature=70.0, humidity=80.0))
        assert any("unusual" in w for w in result.warnings)
        assert "Sensor readings are internally consistent" not in result.checks_passed

    def test_hot_with_clean_air_warns_and_skips_pass(self):
        result = validate_reading(_make_reading(temperature=50.0, smoke=1.0, gas=1.0))
        assert any("likely sensor fault" in w for w in result.warnings)
        assert "Sensor readings are internally consistent" not in result.checks_passed


# ----------------------------------------------------------------------
# API hardening: invalid scenario_type must be rejected with 422,
# reset-history must use the configured (temporary) DB, and admin-key
# endpoints must enforce X-Admin-Key when ADMIN_API_KEY is set.
# ----------------------------------------------------------------------
class TestApiHardening:
    def test_invalid_scenario_type_rejected(self, client):
        r = client.post("/api/simulate", json={"scenario_type": "bogus"})
        assert r.status_code == 422
        assert "Invalid scenario_type" in r.json()["detail"]

    def test_valid_scenario_types_accepted(self, client):
        for st in ["normal", "emergency", "sensor_fault", "spoofing", "offline", "uncertain"]:
            r = client.post("/api/simulate", json={"scenario_type": st})
            assert r.status_code == 200, f"{st} -> {r.status_code}"

    def test_reset_history_uses_tmp_db(self, client, tmp_db):
        # Seed some data through the API
        client.post("/api/simulate", json={"scenario_type": "normal"})
        r = client.get("/api/scenarios")
        assert len(r.json()["scenarios"]) >= 1

        # Reset must clear only the temporary DB (no crash on real path)
        r = client.post("/api/reset-history")
        assert r.status_code == 200
        r = client.get("/api/scenarios")
        assert r.json()["scenarios"] == []

    def test_admin_key_enforced_when_configured(self, monkeypatch, tmp_db):
        from fastapi.testclient import TestClient
        from iot_trustbench import api
        from iot_trustbench.api import app as app_module

        monkeypatch.setenv("ADMIN_API_KEY", "sekret-key-123")
        # Re-import module state so the env var is picked up
        import importlib

        api_mod = importlib.import_module("iot_trustbench.api.app")
        original = api_mod.ADMIN_API_KEY
        api_mod.ADMIN_API_KEY = "sekret-key-123"

        try:
            with TestClient(app_module.app) as c:
                # Without header -> 403
                r = c.post("/api/trusted-devices", json={"device_id": "NEW-DEV-01"})
                assert r.status_code == 403
                # With wrong key -> 403
                r = c.post(
                    "/api/trusted-devices",
                    json={"device_id": "NEW-DEV-01"},
                    headers={"X-Admin-Key": "wrong"},
                )
                assert r.status_code == 403
                # With correct key -> 200
                r = c.post(
                    "/api/trusted-devices",
                    json={"device_id": "NEW-DEV-01"},
                    headers={"X-Admin-Key": "sekret-key-123"},
                )
                assert r.status_code == 200
        finally:
            api_mod.ADMIN_API_KEY = original


# ----------------------------------------------------------------------
# CLI: batch subcommand runs and reports accuracy; unknown types exit 2.
# ----------------------------------------------------------------------
class TestCli:
    def test_batch_single_type(self, capsys):
        from iot_trustbench.cli import main

        code = main(["batch", "normal", "--count", "10"])
        out = capsys.readouterr().out
        assert code == 0
        assert "scenario_type: normal" in out
        assert "runs: 10" in out
        assert "accuracy:" in out

    def test_batch_all_types(self, capsys):
        from iot_trustbench.cli import main

        code = main(["batch", "--count", "5"])
        out = capsys.readouterr().out
        assert code == 0
        for st in ["normal", "emergency", "sensor_fault", "spoofing", "offline", "uncertain"]:
            assert f"scenario_type: {st}" in out

    def test_batch_unknown_type_exits_2(self, capsys):
        import pytest
        from iot_trustbench.cli import main

        with pytest.raises(SystemExit) as excinfo:
            main(["batch", "bogus", "--count", "5"])
        err = capsys.readouterr().err
        assert excinfo.value.code == 2
        assert "unknown scenario type" in err

    def test_cli_no_args_prints_help(self, capsys):
        from iot_trustbench.cli import main

        code = main([])
        out = capsys.readouterr().out
        assert code == 1
        assert "usage" in out.lower()

    def test_python_dash_m_entrypoint(self):
        import subprocess
        import sys

        r = subprocess.run(
            [sys.executable, "-m", "iot_trustbench", "batch", "normal", "--count", "3"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        assert r.returncode == 0
        assert "scenario_type: normal" in r.stdout
