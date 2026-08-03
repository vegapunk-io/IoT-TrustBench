"""Shared pytest fixtures for IoT-TrustBench tests.

All API tests use a temporary SQLite database so the production
database is never touched.  The TestClient is created inside a
``with`` block so that the FastAPI startup event (init_db) fires.
"""

import os
import sys
import tempfile

import pytest

# Ensure the package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture()
def tmp_db(tmp_path):
    """Point the database module at a temporary file for the test."""
    from iot_trustbench.database import db

    original = db.DB_PATH
    test_db = str(tmp_path / "test_iot.db")
    db.set_db_path(test_db)
    yield test_db
    db.set_db_path(original)


@pytest.fixture()
def client(tmp_db):
    """Return a FastAPI TestClient whose startup event has fired.

    Using ``with`` ensures the ``on_event("startup")`` handler runs
    ``init_db()`` against the temporary database.
    """
    from iot_trustbench.api.app import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
