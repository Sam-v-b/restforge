"""
routers/payloads.py — Payload generation and validation endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import ApiTemplate
from schemas import (
    GeneratePayloadRequest,
    GeneratePayloadResponse,
    ValidatePayloadRequest,
    ValidatePayloadResponse,
    ValidationError,
)
from services.payload_generator import generate_payload
from services.validator import validate_payload

router = APIRouter()


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

@router.post(
    "/generate",
    response_model=GeneratePayloadResponse,
    summary="Generate a sample payload from a template's request schema",
)
def generate(
    body: GeneratePayloadRequest,
    db: Session = Depends(get_db),
) -> GeneratePayloadResponse:
    schema = _resolve_schema(body.template_id, body.schema_override, db, "request_schema")

    payload, warnings = generate_payload(schema, mode=body.mode, seed=body.seed)

    return GeneratePayloadResponse(
        payload=payload,
        schema_used=schema,
        mode=body.mode,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

@router.post(
    "/validate",
    response_model=ValidatePayloadResponse,
    summary="Validate a payload against a template's request schema",
)
def validate(
    body: ValidatePayloadRequest,
    db: Session = Depends(get_db),
) -> ValidatePayloadResponse:
    schema = _resolve_schema(body.template_id, body.schema_override, db, "request_schema")

    raw_errors = validate_payload(body.payload, schema)
    errors = [ValidationError(**e) for e in raw_errors]

    return ValidatePayloadResponse(valid=len(errors) == 0, errors=errors)


# ---------------------------------------------------------------------------
# Convenience: generate + validate in one call
# ---------------------------------------------------------------------------

@router.post(
    "/generate-and-validate",
    response_model=GeneratePayloadResponse,
    summary="Generate a payload and immediately validate it (sanity check)",
)
def generate_and_validate(
    body: GeneratePayloadRequest,
    db: Session = Depends(get_db),
) -> GeneratePayloadResponse:
    schema = _resolve_schema(body.template_id, body.schema_override, db, "request_schema")
    payload, warnings = generate_payload(schema, mode=body.mode, seed=body.seed)

    validation_errors = validate_payload(payload, schema)
    for err in validation_errors:
        warnings.append(f"Generated payload validation issue at {err['path']}: {err['message']}")

    return GeneratePayloadResponse(
        payload=payload,
        schema_used=schema,
        mode=body.mode,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _resolve_schema(
    template_id: int | None,
    schema_override: dict | None,
    db: Session,
    schema_attr: str,
) -> dict:
    """Return the JSON Schema to use, from template or inline override."""
    if schema_override:
        return schema_override

    if template_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either template_id or schema_override.",
        )

    template: ApiTemplate | None = (
        db.query(ApiTemplate).filter(ApiTemplate.id == template_id).first()
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template id={template_id} not found.",
        )

    schema = getattr(template, schema_attr, None)
    if not schema:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Template '{template.name}' has no {schema_attr} defined.",
        )

    return schema
