"""
main.py — RESTForge FastAPI application entry point.

Run locally:
    uvicorn main:app --reload --port 8000

Interactive docs:
    http://localhost:8000/docs   (Swagger UI)
    http://localhost:8000/redoc  (ReDoc)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import database
from database import Base
from routers import templates, payloads, test_runs


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    # Always create tables against whatever database.engine currently points to.
    # In tests, conftest patches database.engine to an in-memory instance.
    Base.metadata.create_all(bind=database.engine)
    yield


app = FastAPI(
    title="RESTForge",
    description=(
        "Developer utility for **generating**, **validating**, and "
        "**auto-testing** REST API payloads.\n\n"
        "Define an API contract template once, then:\n"
        "- Auto-generate structured request payloads in *sample*, *edge_case*, or *random* mode\n"
        "- Validate arbitrary payloads against the schema\n"
        "- Run assertions against live endpoints and persist history\n"
    ),
    version="1.0.0",
    contact={"name": "RESTForge", "email": "restforge@example.com"},
    license_info={"name": "MIT"},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(templates.router,  prefix="/api/templates",  tags=["Templates"])
app.include_router(payloads.router,   prefix="/api/payloads",   tags=["Payloads"])
app.include_router(test_runs.router,  prefix="/api/test-runs",  tags=["Test Runs"])


@app.get("/", tags=["Health"])
def root() -> dict:
    return {"service": "RESTForge", "version": "1.0.0", "status": "healthy", "docs": "/docs"}


@app.get("/health", tags=["Health"])
def health() -> dict:
    return {"status": "ok"}
