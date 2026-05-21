import uuid
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(server_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", server_url)
    from dbmanager.webapp import app
    c = TestClient(app)
    c.post("/api/login", json={"password": "test-password"})
    return c


@pytest.fixture
def db(client):
    name = f"dbm_q_{uuid.uuid4().hex[:8]}"
    client.post("/api/databases", json={"name": name})
    yield name
    client.delete(f"/api/databases/{name}?force=true")


def test_query_select_returns_rows(client, db):
    resp = client.post(f"/api/databases/{db}/query",
                       json={"sql": "SELECT 1 AS one, 'x' AS letter"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["columns"] == ["one", "letter"]
    assert data["rows"][0] == {"one": 1, "letter": "x"}


def test_query_ddl_returns_message(client, db):
    resp = client.post(f"/api/databases/{db}/query",
                       json={"sql": "CREATE TABLE t (id int)"})
    assert resp.status_code == 200
    assert resp.json()["columns"] == []


def test_query_syntax_error_is_400(client, db):
    resp = client.post(f"/api/databases/{db}/query",
                       json={"sql": "SELCT bad"})
    assert resp.status_code == 400


def test_query_empty_is_400(client, db):
    resp = client.post(f"/api/databases/{db}/query", json={"sql": "   "})
    assert resp.status_code == 400
