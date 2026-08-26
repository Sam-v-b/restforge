# RESTForge

A developer utility for **generating**, **validating**, and **auto-testing** REST API payloads — built with FastAPI, SQLAlchemy, and Pydantic v2.

Define an API contract once as a template, then auto-generate payloads, validate arbitrary requests against the schema, fire real HTTP tests against live endpoints, and browse a persistent history of every run.

---

## Features

- **Template management** — store your API contract (endpoint, HTTP method, headers, path/query params, request & response JSON Schemas, assertions) as a reusable template
- **Payload generation** — generate structured payloads in three modes: `sample` (sensible defaults), `edge_case` (boundary values), or `random` (randomised within schema constraints); supports a seed for reproducibility
- **Payload validation** — validate any payload against a template's JSON Schema (Draft-07) and get back dot-notation error paths
- **Live test runner** — fire real HTTP requests against your endpoints using `httpx`, evaluate assertions, and persist the full result
- **Assertion engine** — five built-in assertion types: `status_code`, `contains_field`, `field_equals`, `response_time_ms`, `schema_valid`
- **Test history & stats** — browse all past runs, filter by template or pass/fail, and pull aggregated stats (pass rate, avg/min/max duration, status code counts)

---

## Tech Stack

| Layer | Library |
|---|---|
| API framework | FastAPI 0.115 |
| Data validation | Pydantic v2 |
| ORM | SQLAlchemy 2.0 |
| HTTP client | httpx (async) |
| Schema validation | jsonschema (Draft-07) |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Testing | pytest + pytest-asyncio + pytest-httpx |

---

## Architecture

```mermaid
flowchart TB
    Client([HTTP Client / Browser])

    Client --> FastAPI

    subgraph FastAPI["FastAPI Application"]
        R1[/api/templates]
        R2[/api/payloads]
        R3[/api/test-runs]
    end

    subgraph Services
        PG[Payload Generator]
        TR[Test Runner]
        VAL[Validator]
    end

    subgraph DB["Database (SQLite / PostgreSQL)"]
        T[(api_templates)]
        TR2[(test_runs)]
    end

    R1 --> T
    R2 --> PG
    R2 --> VAL
    R3 --> TR
    R3 --> T
    R3 --> TR2
    TR --> PG
    TR --> VAL
    PG --> VAL
    T --- TR2
```

---

## Project Structure

```
restforge/
├── main.py                  # FastAPI app, middleware, router registration
├── database.py              # Engine, SessionLocal, Base, get_db dependency
├── models.py                # ORM models: ApiTemplate, TestRun
├── schemas.py               # Pydantic schemas for all request/response shapes
├── routers/
│   ├── templates.py         # CRUD endpoints for API templates
│   ├── payloads.py          # Generate, validate, generate-and-validate
│   └── test_runs.py         # Run tests, list history, stats, delete
├── services/
│   ├── payload_generator.py # JSON Schema → payload (sample/edge_case/random)
│   ├── test_runner.py       # HTTP execution + assertion evaluation
│   └── validator.py         # jsonschema wrapper, dot-notation error paths
└── tests/
    ├── conftest.py
    ├── test_templates.py
    ├── test_payloads.py
    └── test_test_runner.py
```

---

## Data Model

```mermaid
erDiagram
    api_templates {
        int id PK
        string name
        string description
        string endpoint_url
        string http_method
        json headers
        json path_params
        json query_params
        json request_schema
        json expected_response_schema
        json assertions
        json tags
        bool is_active
        datetime created_at
        datetime updated_at
    }

    test_runs {
        int id PK
        int template_id FK
        json payload_used
        json headers_used
        json query_params_used
        int status_code
        json response_body
        json response_headers
        float duration_ms
        bool overall_passed
        json assertion_results
        text error_message
        datetime created_at
    }

    api_templates ||--o{ test_runs : "has many"
```

---

## Getting Started

### 1. Clone and install dependencies

```bash
git clone <your-repo-url>
cd restforge
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# SQLite (default — no extra setup needed)
DATABASE_URL=sqlite:///./restforge.db

# PostgreSQL (production)
# DATABASE_URL=postgresql://user:password@localhost:5432/restforge
```

### 3. Run the server

```bash
uvicorn main:app --reload --port 8000
```

### 4. Open the docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

---

## API Overview

### Templates — `/api/templates`

| Method | Path | Description |
|---|---|---|
| `POST` | `/` | Create a new API template |
| `GET` | `/` | List templates (filter by `active_only`, `tag`, paginate with `skip`/`limit`) |
| `GET` | `/{id}` | Get a single template |
| `PATCH` | `/{id}` | Partially update a template |
| `DELETE` | `/{id}` | Delete a template and its test run history |

**Example — create a template:**

```json
POST /api/templates/
{
  "name": "Create User",
  "endpoint_url": "https://api.example.com/users",
  "http_method": "POST",
  "headers": { "Content-Type": "application/json" },
  "request_schema": {
    "type": "object",
    "properties": {
      "username": { "type": "string" },
      "email":    { "type": "string", "format": "email" },
      "age":      { "type": "integer", "minimum": 18 }
    },
    "required": ["username", "email"]
  },
  "assertions": [
    { "type": "status_code",      "expected": 201 },
    { "type": "contains_field",   "field": "id" },
    { "type": "response_time_ms", "max": 2000 },
    { "type": "schema_valid" }
  ]
}
```

---

### Payloads — `/api/payloads`

| Method | Path | Description |
|---|---|---|
| `POST` | `/generate` | Generate a payload from a template or inline schema |
| `POST` | `/validate` | Validate a payload against a template or inline schema |
| `POST` | `/generate-and-validate` | Generate then immediately validate (sanity check) |

**Generation modes:**

| Mode | Behaviour |
|---|---|
| `sample` | Readable defaults — good for manual inspection |
| `edge_case` | Boundary values (min/max integers, empty/minimum-length strings, optional fields randomly omitted) |
| `random` | Fully randomised within schema constraints; pass `seed` for reproducibility |

**Supported JSON Schema features:** `type`, `properties`, `required`, `items`, `enum`, `const`, `format` (email, uuid, date, date-time, uri, ipv4, hostname, password), `minimum`/`maximum`, `minLength`/`maxLength`, `minItems`/`maxItems`, `anyOf`, `oneOf`, `allOf`, `$ref` (local `#/$defs/` and `#/definitions/`)

#### Payload Generation Flow

```mermaid
flowchart TD
    Schema[JSON Schema] --> Dispatch{Schema type?}

    Dispatch -->|object| Obj[Iterate properties\ngenerate each field]
    Dispatch -->|array| Arr[Generate N items\nfrom items schema]
    Dispatch -->|string| Str{Format hint?}
    Dispatch -->|integer| Int[Apply min/max bounds]
    Dispatch -->|number| Num[Apply min/max bounds]
    Dispatch -->|boolean| Bool[Return value]
    Dispatch -->|enum| Enum[Pick from values]
    Dispatch -->|anyOf / oneOf| Compose[Pick one sub-schema]
    Dispatch -->|allOf| Merge[Merge all sub-schemas]
    Dispatch -->|$ref| Ref[Resolve from $defs]

    Str -->|email| Email[user@example.com]
    Str -->|uuid| UUID[random UUID]
    Str -->|date| Date[today ISO]
    Str -->|date-time| DT[now UTC ISO]
    Str -->|uri| URI[https://example.com/resource]
    Str -->|none| Plain[sample_NNNN / random chars / min-length]

    subgraph Modes
        M1[sample → sensible defaults]
        M2[edge_case → boundary values]
        M3[random + seed → reproducible random]
    end

    Int & Num & Arr & Obj --> Modes
```

#### Payload Generation — Request Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as POST /api/payloads/generate
    participant DB
    participant PG as PayloadGenerator

    Client->>API: { template_id, mode, seed }
    API->>DB: fetch template.request_schema
    DB-->>API: JSON Schema
    API->>PG: generate(schema, mode, seed)
    PG-->>API: (payload, warnings)
    API-->>Client: { payload, schema_used, mode, warnings }
```

---

### Test Runs — `/api/test-runs`

| Method | Path | Description |
|---|---|---|
| `POST` | `/run` | Execute a test against a live endpoint and persist the result |
| `GET` | `/` | List test run history (filter by `template_id`, `passed`) |
| `GET` | `/{run_id}` | Full detail for a single run |
| `GET` | `/stats/{template_id}` | Aggregated stats for a template |
| `DELETE` | `/{run_id}` | Delete a test run record |

**Example — run a test:**

```json
POST /api/test-runs/run
{
  "template_id": 1,
  "generate_mode": "sample",
  "timeout_seconds": 10
}
```

Pass `payload_override`, `headers_override`, `query_params_override`, or `path_params_override` to customise a single run without changing the template.

**Stats response:**

```json
{
  "template_id": 1,
  "total_runs": 42,
  "passed": 39,
  "failed": 3,
  "pass_rate_pct": 92.9,
  "avg_duration_ms": 148.5,
  "min_duration_ms": 91.2,
  "max_duration_ms": 312.7,
  "status_code_counts": { "200": 39, "500": 3 }
}
```

#### Test Execution Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as POST /api/test-runs/run
    participant DB
    participant PG as PayloadGenerator
    participant TR as TestRunner
    participant Live as Live Endpoint

    Client->>API: { template_id, payload_override?, ... }
    API->>DB: fetch template
    DB-->>API: template (schema, assertions, headers...)
    API->>PG: generate payload (if no override)
    PG-->>API: payload
    API->>TR: run_test(url, method, headers, payload, assertions)
    TR->>Live: HTTP request (httpx async)
    Live-->>TR: response (status, body, headers, duration)
    TR->>TR: evaluate each assertion
    TR-->>API: TestRunResult
    API->>DB: persist TestRun row
    API-->>Client: full TestRunResponse
```

---

### Assertion Engine

| Type | Required fields | Description |
|---|---|---|
| `status_code` | `expected` (int) | Response status must equal `expected` |
| `contains_field` | `field` (dot-notation) | Field must exist in response body |
| `field_equals` | `field`, `expected` | Field value must equal `expected` |
| `response_time_ms` | `max` (float) | Response time must be ≤ `max` ms |
| `schema_valid` | — | Response body must match `expected_response_schema` |

```mermaid
flowchart LR
    Response[HTTP Response] --> AE[Assertion Engine]

    AE --> A1{status_code}
    AE --> A2{contains_field}
    AE --> A3{field_equals}
    AE --> A4{response_time_ms}
    AE --> A5{schema_valid}

    A1 -->|status == expected| P1[✓ pass]
    A1 -->|mismatch| F1[✗ fail]

    A2 -->|dot-path exists| P2[✓ pass]
    A2 -->|not found| F2[✗ fail]

    A3 -->|value == expected| P3[✓ pass]
    A3 -->|mismatch or missing| F3[✗ fail]

    A4 -->|duration_ms ≤ max| P4[✓ pass]
    A4 -->|exceeded| F4[✗ fail]

    A5 -->|validates against schema| P5[✓ pass]
    A5 -->|schema errors| F5[✗ fail]

    P1 & P2 & P3 & P4 & P5 --> Overall{All passed?}
    F1 & F2 & F3 & F4 & F5 --> Overall

    Overall -->|yes| Pass([overall_passed = true])
    Overall -->|no| Fail([overall_passed = false])
```

> **Note:** If `expected_response_schema` is defined on the template and no explicit `schema_valid` assertion is listed, the engine adds it implicitly.

---

## Running Tests

```bash
pytest
```

Tests use an in-memory SQLite database and `pytest-httpx` to mock outbound HTTP calls — no live endpoints or credentials needed.

```bash
pytest -v                          # verbose output
pytest tests/test_payloads.py      # single file
```

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./restforge.db` | SQLAlchemy connection string |

---
