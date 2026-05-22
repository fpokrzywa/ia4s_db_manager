import uuid
import pytest
from fastapi.testclient import TestClient


def test_list_databases_includes_postgres(client):
    resp = client.get("/api/databases")
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert "postgres" in names


def test_create_and_drop_database(client):
    name = f"dbm_test_{uuid.uuid4().hex[:8]}"
    created = client.post("/api/databases", json={"name": name})
    assert created.status_code == 201
    names = [d["name"] for d in client.get("/api/databases").json()]
    assert name in names
    dropped = client.delete(f"/api/databases/{name}")
    assert dropped.status_code == 200


def test_create_duplicate_database_conflicts(client):
    name = f"dbm_test_{uuid.uuid4().hex[:8]}"
    client.post("/api/databases", json={"name": name})
    dup = client.post("/api/databases", json={"name": name})
    assert dup.status_code == 409
    client.delete(f"/api/databases/{name}")


def test_requires_auth(server_url, common_data_url, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("DATABASE_URL", server_url)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    from dbmanager.webapp import app
    resp = TestClient(app).get("/api/databases")
    assert resp.status_code == 401
