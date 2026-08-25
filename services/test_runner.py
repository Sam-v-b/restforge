"""
services/test_runner.py
~~~~~~~~~~~~~~~~~~~~~~~~
Executes an HTTP request for a given ApiTemplate + payload and evaluates
all defined assertions.  Returns a TestRunResult which the router persists.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from services.validator import validate_response_against_schema


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TestRunResult:
    payload_used:      Optional[dict[str, Any]]
    headers_used:      Optional[dict[str, Any]]
    query_params_used: Optional[dict[str, Any]]
    status_code:       Optional[int]        = None
    response_body:     Optional[Any]        = None
    response_headers:  Optional[dict]       = None
    duration_ms:       Optional[float]      = None
    overall_passed:    Optional[bool]       = None
    assertion_results: list[dict[str, Any]] = field(default_factory=list)
    error_message:     Optional[str]        = None


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_test(
    *,
    endpoint_url: str,
    http_method: str,
    headers: dict[str, str],
    query_params: dict[str, Any],
    payload: Optional[dict[str, Any]],
    assertions: list[dict[str, Any]],
    expected_response_schema: Optional[dict[str, Any]],
    timeout_seconds: float = 30.0,
) -> TestRunResult:
    """
    Execute the HTTP request and evaluate assertions.
    Uses httpx.AsyncClient for async transport.
    """
    result = TestRunResult(
        payload_used=payload,
        headers_used=headers,
        query_params_used=query_params,
    )

    # ------------------------------------------------------------------
    # Execute request
    # ------------------------------------------------------------------
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            start = time.perf_counter()

            request_kwargs: dict[str, Any] = {
                "method":  http_method.upper(),
                "url":     endpoint_url,
                "headers": headers,
                "params":  query_params or {},
            }

            if payload is not None and http_method.upper() not in ("GET", "HEAD", "DELETE"):
                request_kwargs["json"] = payload

            response = await client.request(**request_kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

        result.status_code     = response.status_code
        result.duration_ms     = round(elapsed_ms, 2)
        result.response_headers = dict(response.headers)

        # Try to parse body as JSON; fall back to text
        try:
            result.response_body = response.json()
        except Exception:
            result.response_body = response.text

    except httpx.TimeoutException as exc:
        result.error_message = f"Request timed out after {timeout_seconds}s: {exc}"
        result.overall_passed = False
        return result

    except httpx.RequestError as exc:
        result.error_message = f"Network error: {exc}"
        result.overall_passed = False
        return result

    # ------------------------------------------------------------------
    # Evaluate assertions
    # ------------------------------------------------------------------
    assertion_results: list[dict[str, Any]] = []

    for spec in assertions:
        ar = _evaluate_assertion(
            spec=spec,
            status_code=result.status_code,
            response_body=result.response_body,
            duration_ms=result.duration_ms,
            expected_response_schema=expected_response_schema,
        )
        assertion_results.append(ar)

    # If schema_valid assertion wasn't listed but schema exists, add implicit check
    has_schema_assertion = any(a.get("type") == "schema_valid" for a in assertions)
    if expected_response_schema and not has_schema_assertion:
        implicit = _evaluate_assertion(
            spec={"type": "schema_valid"},
            status_code=result.status_code,
            response_body=result.response_body,
            duration_ms=result.duration_ms,
            expected_response_schema=expected_response_schema,
        )
        assertion_results.append(implicit)

    result.assertion_results = assertion_results
    result.overall_passed = all(ar["passed"] for ar in assertion_results)

    return result


# ---------------------------------------------------------------------------
# Assertion evaluators
# ---------------------------------------------------------------------------

def _evaluate_assertion(
    *,
    spec: dict[str, Any],
    status_code: Optional[int],
    response_body: Any,
    duration_ms: Optional[float],
    expected_response_schema: Optional[dict[str, Any]],
) -> dict[str, Any]:
    assertion_type = spec.get("type")

    try:
        if assertion_type == "status_code":
            return _assert_status_code(spec, status_code)

        if assertion_type == "contains_field":
            return _assert_contains_field(spec, response_body)

        if assertion_type == "field_equals":
            return _assert_field_equals(spec, response_body)

        if assertion_type == "response_time_ms":
            return _assert_response_time(spec, duration_ms)

        if assertion_type == "schema_valid":
            return _assert_schema_valid(spec, response_body, expected_response_schema)

        return {
            "assertion": spec,
            "passed": False,
            "detail": f"Unknown assertion type: {assertion_type!r}",
        }

    except Exception as exc:
        return {
            "assertion": spec,
            "passed": False,
            "detail": f"Assertion evaluation error: {exc}",
        }


def _assert_status_code(spec: dict, status_code: Optional[int]) -> dict:
    expected = spec["expected"]
    passed = status_code == expected
    return {
        "assertion": spec,
        "passed": passed,
        "detail": f"Expected {expected}, got {status_code}" if not passed else f"Status {status_code} ✓",
    }


def _assert_contains_field(spec: dict, body: Any) -> dict:
    field_path: str = spec["field"]
    value, found = _get_nested(body, field_path)
    return {
        "assertion": spec,
        "passed": found,
        "detail": f"Field '{field_path}' {'found ✓' if found else 'NOT found ✗'}",
    }


def _assert_field_equals(spec: dict, body: Any) -> dict:
    field_path: str = spec["field"]
    expected = spec["expected"]
    value, found = _get_nested(body, field_path)

    if not found:
        return {
            "assertion": spec,
            "passed": False,
            "detail": f"Field '{field_path}' not found",
        }

    passed = value == expected
    return {
        "assertion": spec,
        "passed": passed,
        "detail": (
            f"Field '{field_path}': expected {expected!r}, got {value!r}"
            if not passed else f"Field '{field_path}' == {value!r} ✓"
        ),
    }


def _assert_response_time(spec: dict, duration_ms: Optional[float]) -> dict:
    max_ms: float = spec["max"]
    if duration_ms is None:
        return {"assertion": spec, "passed": False, "detail": "No duration recorded"}
    passed = duration_ms <= max_ms
    return {
        "assertion": spec,
        "passed": passed,
        "detail": (
            f"Response took {duration_ms:.1f}ms (max {max_ms}ms) ✓"
            if passed else
            f"Response took {duration_ms:.1f}ms — exceeded {max_ms}ms ✗"
        ),
    }


def _assert_schema_valid(
    spec: dict,
    body: Any,
    schema: Optional[dict[str, Any]],
) -> dict:
    if schema is None:
        return {"assertion": spec, "passed": False, "detail": "No expected_response_schema defined"}

    errors = validate_response_against_schema(body, schema)
    passed = len(errors) == 0
    return {
        "assertion": spec,
        "passed": passed,
        "detail": (
            "Response matches expected schema ✓"
            if passed else
            f"{len(errors)} schema error(s): {errors[0]['message']}"
        ),
    }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _get_nested(obj: Any, path: str) -> tuple[Any, bool]:
    """
    Traverse *obj* using dot-notation *path* (e.g. 'user.address.city').
    Returns (value, found).
    """
    parts = path.split(".")
    current = obj

    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return None, False
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return None, False
        else:
            return None, False

    return current, True
