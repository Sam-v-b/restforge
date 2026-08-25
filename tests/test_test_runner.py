"""
tests/test_test_runner.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for the test runner service and /api/test-runs endpoints.
Uses pytest-httpx to mock outbound HTTP calls so no real network hits.
"""

from __future__ import annotations

import json
import pytest
import httpx
from pytest_httpx import HTTPXMock

from services.test_runner import run_test, _get_nested, _evaluate_assertion


# ===========================================================================
# _get_nested utility
# ===========================================================================

class TestGetNested:
    def test_simple_key(self):
        val, found = _get_nested({"id": 42}, "id")
        assert found is True
        assert val == 42

    def test_nested_key(self):
        val, found = _get_nested({"user": {"email": "a@b.com"}}, "user.email")
        assert found is True
        assert val == "a@b.com"

    def test_missing_key(self):
        val, found = _get_nested({"x": 1}, "y")
        assert found is False
        assert val is None

    def test_deep_missing(self):
        val, found = _get_nested({"a": {"b": 1}}, "a.c.d")
        assert found is False

    def test_list_index(self):
        val, found = _get_nested({"items": [10, 20, 30]}, "items.1")
        assert found is True
        assert val == 20

    def test_not_a_dict(self):
        val, found = _get_nested("just-a-string", "key")
        assert found is False


# ===========================================================================
# _evaluate_assertion
# ===========================================================================

class TestEvaluateAssertion:

    def test_status_code_pass(self):
        result = _evaluate_assertion(
            spec={"type": "status_code", "expected": 200},
            status_code=200,
            response_body={},
            duration_ms=50.0,
            expected_response_schema=None,
        )
        assert result["passed"] is True

    def test_status_code_fail(self):
        result = _evaluate_assertion(
            spec={"type": "status_code", "expected": 201},
            status_code=200,
            response_body={},
            duration_ms=50.0,
            expected_response_schema=None,
        )
        assert result["passed"] is False
        assert "201" in result["detail"]
        assert "200" in result["detail"]

    def test_contains_field_pass(self):
        result = _evaluate_assertion(
            spec={"type": "contains_field", "field": "id"},
            status_code=200,
            response_body={"id": 1},
            duration_ms=10.0,
            expected_response_schema=None,
        )
        assert result["passed"] is True

    def test_contains_field_fail(self):
        result = _evaluate_assertion(
            spec={"type": "contains_field", "field": "token"},
            status_code=200,
            response_body={"id": 1},
            duration_ms=10.0,
            expected_response_schema=None,
        )
        assert result["passed"] is False

    def test_field_equals_pass(self):
        result = _evaluate_assertion(
            spec={"type": "field_equals", "field": "status", "expected": "active"},
            status_code=200,
            response_body={"status": "active"},
            duration_ms=10.0,
            expected_response_schema=None,
        )
        assert result["passed"] is True

    def test_field_equals_fail(self):
        result = _evaluate_assertion(
            spec={"type": "field_equals", "field": "status", "expected": "active"},
            status_code=200,
            response_body={"status": "inactive"},
            duration_ms=10.0,
            expected_response_schema=None,
        )
        assert result["passed"] is False

    def test_response_time_pass(self):
        result = _evaluate_assertion(
            spec={"type": "response_time_ms", "max": 500},
            status_code=200,
            response_body={},
            duration_ms=100.0,
            expected_response_schema=None,
        )
        assert result["passed"] is True

    def test_response_time_fail(self):
        result = _evaluate_assertion(
            spec={"type": "response_time_ms", "max": 50},
            status_code=200,
            response_body={},
            duration_ms=300.0,
            expected_response_schema=None,
        )
        assert result["passed"] is False

    def test_schema_valid_pass(self):
        schema = {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        }
        result = _evaluate_assertion(
            spec={"type": "schema_valid"},
            status_code=200,
            response_body={"id": 1},
            duration_ms=10.0,
            expected_response_schema=schema,
        )
        assert result["passed"] is True

    def test_schema_valid_fail(self):
        schema = {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        }
        result = _evaluate_assertion(
            spec={"type": "schema_valid"},
            status_code=200,
            response_body={"id": "not-an-int"},
            duration_ms=10.0,
            expected_response_schema=schema,
        )
        assert result["passed"] is False

    def test_schema_valid_no_schema_defined(self):
        result = _evaluate_assertion(
            spec={"type": "schema_valid"},
            status_code=200,
            response_body={"id": 1},
            duration_ms=10.0,
            expected_response_schema=None,
        )
        assert result["passed"] is False

    def test_unknown_assertion_type(self):
        result = _evaluate_assertion(
            spec={"type": "unsupported"},
            status_code=200,
            response_body={},
            duration_ms=10.0,
            expected_response_schema=None,
        )
        assert result["passed"] is False
        assert "Unknown" in result["detail"]


# ===========================================================================
# run_test service — mocked HTTP
# ===========================================================================

@pytest.mark.asyncio
async def test_run_test_success(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url="https://api.example.com/users",
        status_code=201,
        json={"id": 99, "name": "Alice"},
    )

    result = await run_test(
        endpoint_url="https://api.example.com/users",
        http_method="POST",
        headers={"Content-Type": "application/json"},
        query_params={},
        payload={"name": "Alice", "email": "alice@example.com"},
        assertions=[
            {"type": "status_code", "expected": 201},
            {"type": "contains_field", "field": "id"},
        ],
        expected_response_schema={
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    )

    assert result.status_code == 201
    assert result.response_body == {"id": 99, "name": "Alice"}
    assert result.overall_passed is True
    assert result.error_message is None
    assert len(result.assertion_results) >= 2


@pytest.mark.asyncio
async def test_run_test_assertion_failure(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url="https://api.example.com/users",
        status_code=400,
        json={"error": "Bad Request"},
    )

    result = await run_test(
        endpoint_url="https://api.example.com/users",
        http_method="POST",
        headers={},
        query_params={},
        payload={"bad": "data"},
        assertions=[{"type": "status_code", "expected": 201}],
        expected_response_schema=None,
    )

    assert result.status_code == 400
    assert result.overall_passed is False
    assert any(not ar["passed"] for ar in result.assertion_results)


@pytest.mark.asyncio
async def test_run_test_network_error():
    """No httpx_mock — we expect a real connection refused error."""
    result = await run_test(
        endpoint_url="http://localhost:19999/does-not-exist",
        http_method="GET",
        headers={},
        query_params={},
        payload=None,
        assertions=[{"type": "status_code", "expected": 200}],
        expected_response_schema=None,
        timeout_seconds=2.0,
    )

    assert result.overall_passed is False
    assert result.error_message is not None
    assert result.status_code is None


@pytest.mark.asyncio
async def test_run_test_get_request_no_body(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url="https://api.example.com/users",
        status_code=200,
        json=[{"id": 1}, {"id": 2}],
    )

    result = await run_test(
        endpoint_url="https://api.example.com/users",
        http_method="GET",
        headers={},
        query_params={},
        payload=None,
        assertions=[{"type": "status_code", "expected": 200}],
        expected_response_schema=None,
    )

    assert result.status_code == 200
    assert result.overall_passed is True


@pytest.mark.asyncio
async def test_run_test_records_duration(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.example.com/ping",
        status_code=200,
        json={"pong": True},
    )

    result = await run_test(
        endpoint_url="https://api.example.com/ping",
        http_method="GET",
        headers={},
        query_params={},
        payload=None,
        assertions=[],
        expected_response_schema=None,
    )

    assert result.duration_ms is not None
    assert result.duration_ms >= 0


# ===========================================================================
# /api/test-runs API endpoint tests
# ===========================================================================

class TestRunsEndpoints:

    def test_list_runs_empty(self, client):
        resp = client.get("/api/test-runs/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_nonexistent_run(self, client):
        resp = client.get("/api/test-runs/99999")
        assert resp.status_code == 404

    def test_delete_nonexistent_run(self, client):
        resp = client.delete("/api/test-runs/99999")
        assert resp.status_code == 404

    def test_stats_no_runs(self, client, created_template):
        tid = created_template["id"]
        resp = client.get(f"/api/test-runs/stats/{tid}")
        assert resp.status_code == 200
        assert resp.json()["total_runs"] == 0

    def test_stats_nonexistent_template(self, client):
        resp = client.get("/api/test-runs/stats/99999")
        assert resp.status_code == 404
