"""
routers/templates.py — CRUD for ApiTemplate resources.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from models import ApiTemplate
from schemas import (
    ApiTemplateCreate,
    ApiTemplateResponse,
    ApiTemplateUpdate,
    MessageResponse,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.post(
    "/",
    response_model=ApiTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API template",
)
def create_template(
    body: ApiTemplateCreate,
    db: Session = Depends(get_db),
) -> ApiTemplate:
    # Unique name check
    existing = db.query(ApiTemplate).filter(ApiTemplate.name == body.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template with name '{body.name}' already exists (id={existing.id}).",
        )

    template = ApiTemplate(**body.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


# ---------------------------------------------------------------------------
# Read — list
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=list[ApiTemplateResponse],
    summary="List all API templates",
)
def list_templates(
    active_only: bool = Query(False, description="Return only active templates"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[ApiTemplate]:
    q = db.query(ApiTemplate)
    if active_only:
        q = q.filter(ApiTemplate.is_active == True)  # noqa: E712
    templates = q.offset(skip).limit(limit).all()

    if tag:
        templates = [t for t in templates if tag in (t.tags or [])]

    return templates


# ---------------------------------------------------------------------------
# Read — single
# ---------------------------------------------------------------------------

@router.get(
    "/{template_id}",
    response_model=ApiTemplateResponse,
    summary="Get API template by ID",
)
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
) -> ApiTemplate:
    return _get_or_404(db, template_id)


# ---------------------------------------------------------------------------
# Update (partial)
# ---------------------------------------------------------------------------

@router.patch(
    "/{template_id}",
    response_model=ApiTemplateResponse,
    summary="Partially update an API template",
)
def update_template(
    template_id: int,
    body: ApiTemplateUpdate,
    db: Session = Depends(get_db),
) -> ApiTemplate:
    template = _get_or_404(db, template_id)

    update_data = body.model_dump(exclude_unset=True)

    # Name uniqueness check if name is being changed
    if "name" in update_data and update_data["name"] != template.name:
        clash = db.query(ApiTemplate).filter(ApiTemplate.name == update_data["name"]).first()
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Another template already uses the name '{update_data['name']}'.",
            )

    for key, value in update_data.items():
        setattr(template, key, value)

    db.commit()
    db.refresh(template)
    return template


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete(
    "/{template_id}",
    response_model=MessageResponse,
    summary="Delete an API template and its test run history",
)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
) -> dict:
    template = _get_or_404(db, template_id)
    db.delete(template)
    db.commit()
    return {"message": f"Template '{template.name}' (id={template_id}) deleted."}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_or_404(db: Session, template_id: int) -> ApiTemplate:
    obj = db.query(ApiTemplate).filter(ApiTemplate.id == template_id).first()
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template id={template_id} not found.",
        )
    return obj
