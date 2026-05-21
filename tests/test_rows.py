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
    name = f"dbm_r_{uuid.uuid4().hex[:8]}"
    client.post("/api/databases", json={"name": name})
    client.post(f"/api/databases/{name}/tables", json={
        "name": "people",
        "columns": [
            {"name": "id", "type": "integer", "nullable": False,
             "primary_key": True},
            {"name": "name", "type": "text"},
        ],
    })
    yield name
    client.delete(f"/api/databases/{name}?force=true")


def test_insert_list_update_delete_row(client, db):
    base = f"/api/databases/{db}/tables/people/rows"

    ins = client.post(base, json={"values": {"id": 1, "name": "Ada"}})
    assert ins.status_code == 201

    listed = client.get(base).json()
    assert listed["total"] == 1
    assert listed["primary_key"] == ["id"]
    assert listed["editable"] is True
    assert listed["rows"][0]["name"] == "Ada"

    upd = client.patch(base, json={"pk": {"id": 1}, "values": {"name": "Grace"}})
    assert upd.status_code == 200
    assert client.get(base).json()["rows"][0]["name"] == "Grace"

    dele = client.request("DELETE", base, json={"pk": {"id": 1}})
    assert dele.status_code == 200
    assert client.get(base).json()["total"] == 0


def test_grid_not_editable_without_primary_key(client, db):
    client.post(f"/api/databases/{db}/tables", json={
        "name": "logs", "columns": [{"name": "msg", "type": "text"}]})
    listed = client.get(f"/api/databases/{db}/tables/logs/rows").json()
    assert listed["editable"] is False


def test_filter_rows(client, db):
    base = f"/api/databases/{db}/tables/people/rows"
    client.post(base, json={"values": {"id": 1, "name": "Ada"}})
    client.post(base, json={"values": {"id": 2, "name": "Bob"}})
    filtered = client.get(f"{base}?filter_column=name&filter_value=Ada").json()
    assert filtered["total"] == 1
    assert filtered["rows"][0]["name"] == "Ada"
