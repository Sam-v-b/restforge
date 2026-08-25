"""
tests/conftest.py — Shared pytest fixtures.

Strategy:
- Each test function gets its own fresh SQLite in-memory engine (StaticPool).
- We patch `database.engine` so the app lifespan's create_all targets the
  test engine rather than a real file.
- The DB session dependency is overridden to the per-test session.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database as db_module
from database import Base, get_db
from main import app


# ---------------------------------------------------------------------------
# Per-test engine + session
# ---------------------------------------------------------------------------

@pytest.fixture
def test_engine():
    """Fresh in-memory SQLite engine per test function."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(test_engine, db_session):
    """
    TestClient with:
      - database.engine patched → test engine (so lifespan create_all is harmless)
      - get_db dependency overridden → per-test session
    """
    original_engine = db_module.engine
    db_module.engine = test_engine        # redirect lifespan

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
    db_module.engine = original_engine    # restore


# ---------------------------------------------------------------------------
# Reusable template payload
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_template_payload() -> dict:
    return {
        "name": "Create User",
        "description": "Creates a new user account",
        "endpoint_url": "https://jsonplaceholder.typicode.com/users",
        "http_method": "POST",
        "headers": {"Content-Type": "application/json"},
        "request_schema": {
            "type": "object",
            "properties": {
                "name":     {"type": "string", "minLength": 1},
                "username": {"type": "string", "minLength": 3},
                "email":    {"type": "string", "format": "email"},
                "age":      {"type": "integer", "minimum": 18, "maximum": 120},
            },
            "required": ["name", "username", "email"],
        },
        "expected_response_schema": {
            "type": "object",
            "properties": {
                "id":   {"type": "integer"},
                "name": {"type": "string"},
            },
            "required": ["id"],
        },
        "assertions": [
            {"type": "status_code",    "expected": 201},
            {"type": "contains_field", "field": "id"},
            {"type": "response_time_ms", "max": 5000},
        ],
        "tags": ["users", "auth"],
    }


@pytest.fixture
def created_template(client, sample_template_payload) -> dict:
    resp = client.post("/api/templates/", json=sample_template_payload)
    assert resp.status_code == 201
    return resp.json()
