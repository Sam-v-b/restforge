"""
tests/test_templates.py — Unit tests for the /api/templates CRUD endpoints.
"""

import pytest


class TestCreateTemplate:
    def test_create_success(self, client, sample_template_payload):
        resp = client.post("/api/templates/", json=sample_template_payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == sample_template_payload["name"]
        assert data["http_method"] == "POST"
        assert "id" in data
        assert "created_at" in data

    def test_create_duplicate_name_returns_409(self, client, sample_template_payload):
        client.post("/api/templates/", json=sample_template_payload)
        resp = client.post("/api/templates/", json=sample_template_payload)
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_create_normalises_method_to_uppercase(self, client, sample_template_payload):
        sample_template_payload["http_method"] = "get"
        sample_template_payload["name"] = "Get Users"
        resp = client.post("/api/templates/", json=sample_template_payload)
        assert resp.status_code == 201
        assert resp.json()["http_method"] == "GET"

    def test_create_missing_required_fields_returns_422(self, client):
        resp = client.post("/api/templates/", json={"description": "no name"})
        assert resp.status_code == 422

    def test_create_without_schema_is_valid(self, client):
        payload = {
            "name": "Minimal Template",
            "endpoint_url": "https://example.com/api",
            "http_method": "GET",
        }
        resp = client.post("/api/templates/", json=payload)
        assert resp.status_code == 201
        assert resp.json()["request_schema"] is None


class TestListTemplates:
    def test_list_empty(self, client):
        resp = client.get("/api/templates/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_all(self, client, sample_template_payload):
        client.post("/api/templates/", json=sample_template_payload)
        sample_template_payload["name"] = "Another Template"
        client.post("/api/templates/", json=sample_template_payload)

        resp = client.get("/api/templates/")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_filter_by_tag(self, client, sample_template_payload, created_template):
        resp = client.get("/api/templates/?tag=users")
        assert resp.status_code == 200
        assert any(t["id"] == created_template["id"] for t in resp.json())

    def test_list_filter_by_tag_no_match(self, client, created_template):
        resp = client.get("/api/templates/?tag=nonexistent_tag")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_pagination(self, client, sample_template_payload):
        for i in range(5):
            sample_template_payload["name"] = f"Template {i}"
            client.post("/api/templates/", json=sample_template_payload)

        resp = client.get("/api/templates/?skip=2&limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestGetTemplate:
    def test_get_existing(self, client, created_template):
        tid = created_template["id"]
        resp = client.get(f"/api/templates/{tid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == tid

    def test_get_nonexistent_returns_404(self, client):
        resp = client.get("/api/templates/99999")
        assert resp.status_code == 404


class TestUpdateTemplate:
    def test_patch_description(self, client, created_template):
        tid = created_template["id"]
        resp = client.patch(f"/api/templates/{tid}", json={"description": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated"
        # Name unchanged
        assert resp.json()["name"] == created_template["name"]

    def test_patch_name_conflict_returns_409(self, client, sample_template_payload, created_template):
        sample_template_payload["name"] = "Second Template"
        second = client.post("/api/templates/", json=sample_template_payload).json()
        resp = client.patch(
            f"/api/templates/{second['id']}",
            json={"name": created_template["name"]},
        )
        assert resp.status_code == 409

    def test_patch_nonexistent_returns_404(self, client):
        resp = client.patch("/api/templates/99999", json={"description": "x"})
        assert resp.status_code == 404

    def test_patch_is_active(self, client, created_template):
        tid = created_template["id"]
        resp = client.patch(f"/api/templates/{tid}", json={"is_active": False})
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False


class TestDeleteTemplate:
    def test_delete_existing(self, client, created_template):
        tid = created_template["id"]
        resp = client.delete(f"/api/templates/{tid}")
        assert resp.status_code == 200
        # Should now 404
        assert client.get(f"/api/templates/{tid}").status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/templates/99999")
        assert resp.status_code == 404
