"""
routers/test_runs.py — Execute tests and browse test-run history.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from models import ApiTemplate, TestRun
from schemas import RunTestRequest, TestRunResponse, TestRunSummary, MessageResponse
from services.payload_generator import generate_payload
from services.test_runner import run_test, TestRunResult

router = APIRouter()


# ---------------------------------------------------------------------------
# Execute a test run
# ---------------------------------------------------------------------------

@router.post(
    "/run",
    response_model=TestRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute an API test against a template and persist results",
)
async def execute_test(
    body: RunTestRequest,
    db: Session = Depends(get_db),
) -> TestRun:
    template = _get_template_or_404(db, body.template_id)

    # ------------------------------------------------------------------
    # Build request components
    # ------------------------------------------------------------------
    merged_headers = dict(template.headers or {})
    if body.headers_override:
        merged_headers.update(body.headers_override)

    merged_query = dict(template.query_params or {})
    if body.query_params_override:
        merged_query.update(body.query_params_override)

    # Resolve endpoint — substitute path params
    endpoint = template.endpoint_url
    path_params = dict(template.path_params or {})
    if body.path_params_override:
        path_params.update(body.path_params_override)
    for param, value in path_params.items():
        endpoint = endpoint.replace(f"{{{param}}}", str(value))

    # Resolve payload
    payload: Optional[dict] = body.payload_override
    if payload is None and template.request_schema:
        payload, _ = generate_payload(
            template.request_schema,
            mode=body.generate_mode,
        )

    # ------------------------------------------------------------------
    # Run the HTTP request + assertions
    # ------------------------------------------------------------------
    result: TestRunResult = await run_test(
        endpoint_url=endpoint,
        http_method=template.http_method,
        headers=merged_headers,
        query_params=merged_query,
        payload=payload,
        assertions=list(template.assertions or []),
        expected_response_schema=template.expected_response_schema,
        timeout_seconds=body.timeout_seconds,
    )

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------
    run = TestRun(
        template_id=template.id,
        payload_used=result.payload_used,
        headers_used=result.headers_used,
        query_params_used=result.query_params_used,
        status_code=result.status_code,
        response_body=result.response_body,
        response_headers=result.response_headers,
        duration_ms=result.duration_ms,
        overall_passed=result.overall_passed,
        assertion_results=result.assertion_results,
        error_message=result.error_message,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


# ---------------------------------------------------------------------------
# List test runs
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=list[TestRunSummary],
    summary="List test run history (newest first)",
)
def list_test_runs(
    template_id: Optional[int] = Query(None, description="Filter by template"),
    passed: Optional[bool] = Query(None, description="Filter by pass/fail"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[TestRun]:
    q = db.query(TestRun).order_by(desc(TestRun.created_at))

    if template_id is not None:
        q = q.filter(TestRun.template_id == template_id)
    if passed is not None:
        q = q.filter(TestRun.overall_passed == passed)

    return q.offset(skip).limit(limit).all()


# ---------------------------------------------------------------------------
# Single test run detail
# ---------------------------------------------------------------------------

@router.get(
    "/{run_id}",
    response_model=TestRunResponse,
    summary="Get full detail for a single test run",
)
def get_test_run(run_id: int, db: Session = Depends(get_db)) -> TestRun:
    return _get_run_or_404(db, run_id)


# ---------------------------------------------------------------------------
# Delete a test run record
# ---------------------------------------------------------------------------

@router.delete(
    "/{run_id}",
    response_model=MessageResponse,
    summary="Delete a test run record",
)
def delete_test_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = _get_run_or_404(db, run_id)
    db.delete(run)
    db.commit()
    return {"message": f"Test run id={run_id} deleted."}


# ---------------------------------------------------------------------------
# Summary stats for a template
# ---------------------------------------------------------------------------

@router.get(
    "/stats/{template_id}",
    summary="Aggregated stats for a template's test runs",
)
def get_stats(template_id: int, db: Session = Depends(get_db)) -> dict:
    _get_template_or_404(db, template_id)

    runs = (
        db.query(TestRun)
        .filter(TestRun.template_id == template_id)
        .all()
    )

    if not runs:
        return {"template_id": template_id, "total_runs": 0}

    total = len(runs)
    passed = sum(1 for r in runs if r.overall_passed)
    durations = [r.duration_ms for r in runs if r.duration_ms is not None]
    status_codes = {}
    for r in runs:
        if r.status_code:
            status_codes[r.status_code] = status_codes.get(r.status_code, 0) + 1

    return {
        "template_id":        template_id,
        "total_runs":         total,
        "passed":             passed,
        "failed":             total - passed,
        "pass_rate_pct":      round(passed / total * 100, 1),
        "avg_duration_ms":    round(sum(durations) / len(durations), 2) if durations else None,
        "min_duration_ms":    round(min(durations), 2) if durations else None,
        "max_duration_ms":    round(max(durations), 2) if durations else None,
        "status_code_counts": status_codes,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_template_or_404(db: Session, template_id: int) -> ApiTemplate:
    obj = db.query(ApiTemplate).filter(ApiTemplate.id == template_id).first()
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template id={template_id} not found.",
        )
    return obj


def _get_run_or_404(db: Session, run_id: int) -> TestRun:
    obj = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test run id={run_id} not found.",
        )
    return obj
