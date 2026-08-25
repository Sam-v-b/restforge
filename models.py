"""
models.py — SQLAlchemy ORM models.

Tables:
    api_templates   — API contract definitions (endpoint, method, schemas, assertions)
    test_runs       — History of every executed test against a template
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float,
    Boolean, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ApiTemplate(Base):
    """
    Stores an API contract template.

    request_schema / expected_response_schema are stored as JSON objects
    following the JSON Schema draft-07 spec so the payload generator and
    validator can consume them directly.

    assertions is a list of assertion dicts, e.g.:
        [
          {"type": "status_code",    "expected": 201},
          {"type": "contains_field", "field": "id"},
          {"type": "field_equals",   "field": "status", "expected": "active"},
          {"type": "response_time_ms","max": 2000},
          {"type": "schema_valid"}
        ]
    """

    __tablename__ = "api_templates"

    id                       = Column(Integer, primary_key=True, index=True)
    name                     = Column(String(120), nullable=False, unique=True, index=True)
    description              = Column(Text, nullable=True)
    endpoint_url             = Column(String(500), nullable=False)
    http_method              = Column(String(10), nullable=False, default="POST")
    headers                  = Column(JSON, nullable=True, default=dict)          # {key: value}
    path_params              = Column(JSON, nullable=True, default=dict)          # {param: description}
    query_params             = Column(JSON, nullable=True, default=dict)          # {param: value}
    request_schema           = Column(JSON, nullable=True)                        # JSON Schema
    expected_response_schema = Column(JSON, nullable=True)                        # JSON Schema
    assertions               = Column(JSON, nullable=True, default=list)          # list[dict]
    tags                     = Column(JSON, nullable=True, default=list)          # list[str]
    is_active                = Column(Boolean, default=True, nullable=False)
    created_at               = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at               = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    test_runs = relationship("TestRun", back_populates="template", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ApiTemplate id={self.id} name={self.name!r} method={self.http_method}>"


class TestRun(Base):
    """
    Records the result of a single test execution.

    assertion_results is a list of dicts:
        [{"assertion": {...}, "passed": True/False, "detail": "..."}]
    """

    __tablename__ = "test_runs"

    id                  = Column(Integer, primary_key=True, index=True)
    template_id         = Column(Integer, ForeignKey("api_templates.id"), nullable=False, index=True)
    payload_used        = Column(JSON, nullable=True)              # request body sent
    headers_used        = Column(JSON, nullable=True)              # merged headers sent
    query_params_used   = Column(JSON, nullable=True)
    status_code         = Column(Integer, nullable=True)
    response_body       = Column(JSON, nullable=True)
    response_headers    = Column(JSON, nullable=True)
    duration_ms         = Column(Float, nullable=True)
    overall_passed      = Column(Boolean, nullable=True)           # all assertions passed?
    assertion_results   = Column(JSON, nullable=True, default=list)
    error_message       = Column(Text, nullable=True)              # network/timeout errors
    created_at          = Column(DateTime(timezone=True), default=_now, nullable=False)

    template = relationship("ApiTemplate", back_populates="test_runs")

    def __repr__(self) -> str:
        return (
            f"<TestRun id={self.id} template_id={self.template_id} "
            f"status={self.status_code} passed={self.overall_passed}>"
        )
