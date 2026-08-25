"""
schemas.py — Pydantic v2 request/response schemas for the FastAPI layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# Assertion schemas
# ---------------------------------------------------------------------------

class StatusCodeAssertion(BaseModel):
    type: Literal["status_code"]
    expected: int = Field(..., ge=100, le=599)


class ContainsFieldAssertion(BaseModel):
    type: Literal["contains_field"]
    field: str = Field(..., description="Dot-notation field path, e.g. 'user.id'")


class FieldEqualsAssertion(BaseModel):
    type: Literal["field_equals"]
    field: str
    expected: Any


class ResponseTimeAssertion(BaseModel):
    type: Literal["response_time_ms"]
    max: float = Field(..., gt=0, description="Maximum allowed response time in ms")


class SchemaValidAssertion(BaseModel):
    type: Literal["schema_valid"]


AssertionSpec = Union[
    StatusCodeAssertion,
    ContainsFieldAssertion,
    FieldEqualsAssertion,
    ResponseTimeAssertion,
    SchemaValidAssertion,
]


# ---------------------------------------------------------------------------
# Template schemas
# ---------------------------------------------------------------------------

class ApiTemplateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, examples=["Create User"])
    description: Optional[str] = None
    endpoint_url: str = Field(..., examples=["https://api.example.com/users"])
    http_method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict, examples=[{"Content-Type": "application/json"}])
    path_params: dict[str, str] = Field(default_factory=dict, examples=[{"user_id": "UUID path param"}])
    query_params: dict[str, Any] = Field(default_factory=dict)
    request_schema: Optional[dict[str, Any]] = Field(
        default=None,
        description="JSON Schema for the request body",
        examples=[{
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "email": {"type": "string", "format": "email"},
                "age": {"type": "integer", "minimum": 18}
            },
            "required": ["username", "email"]
        }]
    )
    expected_response_schema: Optional[dict[str, Any]] = Field(
        default=None,
        description="JSON Schema for the expected response body",
    )
    assertions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of assertion specs to run after the request",
        examples=[[
            {"type": "status_code", "expected": 201},
            {"type": "contains_field", "field": "id"},
            {"type": "response_time_ms", "max": 2000},
            {"type": "schema_valid"}
        ]]
    )
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("http_method", mode="before")
    @classmethod
    def uppercase_method(cls, v: str) -> str:
        return v.upper()


class ApiTemplateCreate(ApiTemplateBase):
    pass


class ApiTemplateUpdate(BaseModel):
    """All fields optional for partial updates."""
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    endpoint_url: Optional[str] = None
    http_method: Optional[Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]] = None
    headers: Optional[dict[str, str]] = None
    path_params: Optional[dict[str, str]] = None
    query_params: Optional[dict[str, Any]] = None
    request_schema: Optional[dict[str, Any]] = None
    expected_response_schema: Optional[dict[str, Any]] = None
    assertions: Optional[list[dict[str, Any]]] = None
    tags: Optional[list[str]] = None
    is_active: Optional[bool] = None


class ApiTemplateResponse(ApiTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Payload schemas
# ---------------------------------------------------------------------------

class GeneratePayloadRequest(BaseModel):
    template_id: Optional[int] = Field(None, description="Use an existing template's request_schema")
    schema_override: Optional[dict[str, Any]] = Field(
        None, description="Provide an inline JSON Schema instead"
    )
    mode: Literal["sample", "edge_case", "random"] = Field(
        "sample",
        description="sample=sensible defaults, edge_case=boundary values, random=randomised"
    )
    seed: Optional[int] = Field(None, description="Seed for reproducible random generation")


class GeneratePayloadResponse(BaseModel):
    payload: dict[str, Any]
    schema_used: dict[str, Any]
    mode: str
    warnings: list[str] = []


class ValidatePayloadRequest(BaseModel):
    template_id: Optional[int] = None
    schema_override: Optional[dict[str, Any]] = None
    payload: dict[str, Any]


class ValidationError(BaseModel):
    path: str
    message: str


class ValidatePayloadResponse(BaseModel):
    valid: bool
    errors: list[ValidationError] = []


# ---------------------------------------------------------------------------
# Test run schemas
# ---------------------------------------------------------------------------

class RunTestRequest(BaseModel):
    template_id: int
    payload_override: Optional[dict[str, Any]] = Field(
        None, description="Custom payload; if omitted, one is auto-generated"
    )
    headers_override: Optional[dict[str, str]] = None
    query_params_override: Optional[dict[str, Any]] = None
    path_params_override: Optional[dict[str, str]] = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    generate_mode: Literal["sample", "edge_case", "random"] = "sample"


class AssertionResult(BaseModel):
    assertion: dict[str, Any]
    passed: bool
    detail: str


class TestRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    payload_used: Optional[dict[str, Any]]
    headers_used: Optional[dict[str, Any]]
    query_params_used: Optional[dict[str, Any]]
    status_code: Optional[int]
    response_body: Optional[Any]
    response_headers: Optional[dict[str, Any]]
    duration_ms: Optional[float]
    overall_passed: Optional[bool]
    assertion_results: list[dict[str, Any]]
    error_message: Optional[str]
    created_at: datetime


class TestRunSummary(BaseModel):
    """Lightweight listing response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    status_code: Optional[int]
    duration_ms: Optional[float]
    overall_passed: Optional[bool]
    error_message: Optional[str]
    created_at: datetime


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]
