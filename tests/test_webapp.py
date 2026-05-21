from fastapi.testclient import TestClient
from dbmanager.webapp import app

client = TestClient(app)


def test_index_served():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Database Manager" in resp.text


def test_login_rejects_wrong_password():
    resp = client.post("/api/login", json={"password": "nope"})
    assert resp.status_code == 401


def test_login_accepts_correct_password():
    resp = client.post("/api/login", json={"password": "test-password"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_logout_clears_session():
    c = TestClient(app)
    c.post("/api/login", json={"password": "test-password"})
    resp = c.post("/api/logout")
    assert resp.status_code == 200


def test_server_info_returns_host_port():
    c = TestClient(app)
    c.post("/api/login", json={"password": "test-password"})
    resp = c.get("/api/server-info")
    assert resp.status_code == 200
    data = resp.json()
    assert "host" in data and "port" in data


def test_server_info_requires_auth():
    resp = TestClient(app).get("/api/server-info")
    assert resp.status_code == 401
