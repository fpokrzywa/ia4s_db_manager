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
