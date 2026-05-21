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
    """A fresh database, dropped after the test."""
    name = f"dbm_t_{uuid.uuid4().hex[:8]}"
    client.post("/api/databases", json={"name": name})
    yield name
    client.delete(f"/api/databases/{name}?force=true")


def test_create_inspect_drop_table(client, db):
    create = client.post(f"/api/databases/{db}/tables", json={
        "name": "items",
        "columns": [
            {"name": "id", "type": "integer", "nullable": False,
             "primary_key": True},
            {"name": "label", "type": "text"},
        ],
    })
    assert create.status_code == 201

    listed = client.get(f"/api/databases/{db}/tables").json()
    assert "items" in [t["name"] for t in listed]

    struct = client.get(f"/api/databases/{db}/tables/items").json()
    assert struct["primary_key"] == ["id"]
    assert {c["name"] for c in struct["columns"]} == {"id", "label"}

    dropped = client.delete(f"/api/databases/{db}/tables/items")
    assert dropped.status_code == 200


def test_add_and_drop_column(client, db):
    client.post(f"/api/databases/{db}/tables", json={
        "name": "t", "columns": [{"name": "id", "type": "integer"}]})
    add = client.post(f"/api/databases/{db}/tables/t/columns",
                      json={"name": "note", "type": "text"})
    assert add.status_code == 201
    struct = client.get(f"/api/databases/{db}/tables/t").json()
    assert "note" in [c["name"] for c in struct["columns"]]
    drop = client.delete(f"/api/databases/{db}/tables/t/columns/note")
    assert drop.status_code == 200


def test_inspect_missing_table_404(client, db):
    resp = client.get(f"/api/databases/{db}/tables/nope")
    assert resp.status_code == 404
