"""
tests/test_payloads.py
~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for payload generation, validation, and the service layer directly.
"""

import pytest

from services.payload_generator import generate_payload
from services.validator import validate_payload, _format_path


# ===========================================================================
# payload_generator — direct service tests
# ===========================================================================

class TestGeneratePayloadService:

    def test_sample_mode_returns_dict(self):
        schema = {
            "type": "object",
            "properties": {
                "name":  {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["name", "count"],
        }
        payload, warnings = generate_payload(schema, mode="sample")
        assert isinstance(payload, dict)
        assert "name" in payload
        assert "count" in payload
        assert isinstance(payload["name"], str)
        assert isinstance(payload["count"], int)

    def test_required_fields_always_generated(self):
        schema = {
            "type": "object",
            "properties": {
                "email": {"type": "string", "format": "email"},
                "optional_field": {"type": "string"},
            },
            "required": ["email"],
        }
        for _ in range(20):
            payload, _ = generate_payload(schema, mode="edge_case")
            assert "email" in payload

    def test_email_format(self):
        schema = {
            "type": "object",
            "properties": {"email": {"type": "string", "format": "email"}},
            "required": ["email"],
        }
        payload, _ = generate_payload(schema)
        assert "@" in payload["email"]

    def test_uuid_format(self):
        schema = {
            "type": "object",
            "properties": {"id": {"type": "string", "format": "uuid"}},
            "required": ["id"],
        }
        payload, _ = generate_payload(schema)
        import uuid
        # Should not raise
        uuid.UUID(payload["id"])

    def test_integer_respects_minimum(self):
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer", "minimum": 18, "maximum": 120}},
            "required": ["age"],
        }
        for _ in range(30):
            payload, _ = generate_payload(schema, mode="random", seed=None)
            assert 18 <= payload["age"] <= 120

    def test_edge_case_returns_min_integer(self):
        schema = {
            "type": "object",
            "properties": {"score": {"type": "integer", "minimum": 0, "maximum": 100}},
            "required": ["score"],
        }
        # edge_case picks either min or max
        values = set()
        for seed in range(20):
            payload, _ = generate_payload(schema, mode="edge_case", seed=seed)
            values.add(payload["score"])
        assert 0 in values or 100 in values

    def test_enum_value_selected(self):
        schema = {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": ["active", "inactive", "pending"]}},
            "required": ["status"],
        }
        payload, _ = generate_payload(schema)
        assert payload["status"] in ["active", "inactive", "pending"]

    def test_nested_object(self):
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name":  {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                    },
                    "required": ["name", "email"],
                }
            },
            "required": ["user"],
        }
        payload, _ = generate_payload(schema)
        assert isinstance(payload["user"], dict)
        assert "name" in payload["user"]
        assert "email" in payload["user"]

    def test_array_generation(self):
        schema = {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 5,
                }
            },
            "required": ["tags"],
        }
        payload, _ = generate_payload(schema, mode="sample")
        assert isinstance(payload["tags"], list)
        assert len(payload["tags"]) >= 1

    def test_boolean_generation(self):
        schema = {
            "type": "object",
            "properties": {"active": {"type": "boolean"}},
            "required": ["active"],
        }
        payload, _ = generate_payload(schema)
        assert isinstance(payload["active"], bool)

    def test_seed_produces_deterministic_output(self):
        schema = {
            "type": "object",
            "properties": {
                "name":  {"type": "string"},
                "score": {"type": "integer", "minimum": 0, "maximum": 1000},
            },
            "required": ["name", "score"],
        }
        p1, _ = generate_payload(schema, mode="random", seed=42)
        p2, _ = generate_payload(schema, mode="random", seed=42)
        assert p1 == p2

    def test_anyof_picks_one_subschema(self):
        schema = {
            "type": "object",
            "properties": {
                "value": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "integer"},
                    ]
                }
            },
            "required": ["value"],
        }
        payload, _ = generate_payload(schema)
        assert isinstance(payload["value"], (str, int))

    def test_warnings_on_unknown_type(self):
        schema = {"type": "unknownType"}
        payload, warnings = generate_payload(schema)
        assert len(warnings) > 0


# ===========================================================================
# validator — direct service tests
# ===========================================================================

class TestValidatePayloadService:

    def test_valid_payload_returns_empty_errors(self):
        schema = {
            "type": "object",
            "properties": {
                "name":  {"type": "string"},
                "email": {"type": "string", "format": "email"},
            },
            "required": ["name", "email"],
        }
        errors = validate_payload({"name": "Alice", "email": "alice@example.com"}, schema)
        assert errors == []

    def test_missing_required_field(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        errors = validate_payload({}, schema)
        assert len(errors) == 1
        assert "name" in errors[0]["message"] or "required" in errors[0]["message"].lower()

    def test_wrong_type_returns_error(self):
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer"}},
            "required": ["age"],
        }
        errors = validate_payload({"age": "not-an-int"}, schema)
        assert len(errors) == 1
        assert errors[0]["path"] == "age"

    def test_multiple_errors(self):
        schema = {
            "type": "object",
            "properties": {
                "name":  {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["name", "count"],
        }
        errors = validate_payload({"name": 123, "count": "bad"}, schema)
        # Both fields should fail
        assert len(errors) >= 2

    def test_nested_field_path(self):
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {"age": {"type": "integer"}},
                    "required": ["age"],
                }
            },
            "required": ["user"],
        }
        errors = validate_payload({"user": {"age": "old"}}, schema)
        assert len(errors) == 1
        assert "user" in errors[0]["path"]
        assert "age" in errors[0]["path"]

    def test_min_length_violation(self):
        schema = {
            "type": "object",
            "properties": {"username": {"type": "string", "minLength": 3}},
            "required": ["username"],
        }
        errors = validate_payload({"username": "ab"}, schema)
        assert len(errors) == 1

    def test_enum_violation(self):
        schema = {
            "type": "object",
            "properties": {"status": {"enum": ["active", "inactive"]}},
            "required": ["status"],
        }
        errors = validate_payload({"status": "deleted"}, schema)
        assert len(errors) == 1


# ===========================================================================
# API endpoint tests for /api/payloads/
# ===========================================================================

class TestGeneratePayloadEndpoint:

    def test_generate_with_template_id(self, client, created_template):
        resp = client.post("/api/payloads/generate", json={
            "template_id": created_template["id"],
            "mode": "sample",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "payload" in data
        assert isinstance(data["payload"], dict)
        assert data["mode"] == "sample"

    def test_generate_with_schema_override(self, client):
        resp = client.post("/api/payloads/generate", json={
            "schema_override": {
                "type": "object",
                "properties": {"foo": {"type": "string"}},
                "required": ["foo"],
            },
            "mode": "sample",
        })
        assert resp.status_code == 200
        assert "foo" in resp.json()["payload"]

    def test_generate_no_source_returns_422(self, client):
        resp = client.post("/api/payloads/generate", json={"mode": "sample"})
        assert resp.status_code == 422

    def test_generate_nonexistent_template_returns_404(self, client):
        resp = client.post("/api/payloads/generate", json={"template_id": 99999})
        assert resp.status_code == 404

    def test_generate_template_without_schema_returns_422(self, client):
        # Create a template with no request_schema
        t = client.post("/api/templates/", json={
            "name": "No Schema",
            "endpoint_url": "https://example.com",
            "http_method": "GET",
        }).json()
        resp = client.post("/api/payloads/generate", json={"template_id": t["id"]})
        assert resp.status_code == 422

    def test_generate_edge_case_mode(self, client, created_template):
        resp = client.post("/api/payloads/generate", json={
            "template_id": created_template["id"],
            "mode": "edge_case",
        })
        assert resp.status_code == 200

    def test_generate_random_mode_with_seed(self, client, created_template):
        tid = created_template["id"]
        r1 = client.post("/api/payloads/generate", json={"template_id": tid, "mode": "random", "seed": 7}).json()
        r2 = client.post("/api/payloads/generate", json={"template_id": tid, "mode": "random", "seed": 7}).json()
        assert r1["payload"] == r2["payload"]


class TestValidatePayloadEndpoint:

    def test_validate_valid_payload(self, client, created_template):
        resp = client.post("/api/payloads/validate", json={
            "template_id": created_template["id"],
            "payload": {
                "name":     "Alice",
                "username": "alice99",
                "email":    "alice@example.com",
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_validate_invalid_payload(self, client, created_template):
        resp = client.post("/api/payloads/validate", json={
            "template_id": created_template["id"],
            "payload": {"name": "Alice"},   # missing username & email
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) >= 1

    def test_validate_with_inline_schema(self, client):
        resp = client.post("/api/payloads/validate", json={
            "schema_override": {
                "type": "object",
                "properties": {"x": {"type": "integer"}},
                "required": ["x"],
            },
            "payload": {"x": "not-int"},
        })
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
