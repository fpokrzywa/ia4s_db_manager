import pytest
from fastapi.testclient import TestClient
from dbmanager import authdb
from dbmanager.passwords import hash_password


@pytest.fixture
def app_client(server_url, common_data_url, monkeypatch):
    """A bare (not logged-in) TestClient wired to the test databases."""
    monkeypatch.setenv("DATABASE_URL", server_url)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    from dbmanager.webapp import app
    return TestClient(app)


def test_login_success(app_client):
    resp = app_client.post("/api/login", json={"email": "test@example.com",
                                               "password": "test-password"})
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is False


def test_login_wrong_password(app_client):
    resp = app_client.post("/api/login", json={"email": "test@example.com",
                                               "password": "nope"})
    assert resp.status_code == 401


def test_login_unknown_email(app_client):
    resp = app_client.post("/api/login", json={"email": "ghost@example.com",
                                               "password": "x"})
    assert resp.status_code == 401


def test_login_reports_must_change(common_data_url, app_client):
    with authdb.auth_conn(common_data_url) as conn:
        authdb.create_user(conn, "fresh@example.com", hash_password("TempPass1"))
    resp = app_client.post("/api/login", json={"email": "fresh@example.com",
                                               "password": "TempPass1"})
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is True


def test_me_requires_auth(app_client):
    assert app_client.get("/api/me").status_code == 401


def test_me_after_login(app_client):
    app_client.post("/api/login", json={"email": "test@example.com",
                                        "password": "test-password"})
    resp = app_client.get("/api/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@example.com"


def test_change_password_flow(common_data_url, app_client):
    with authdb.auth_conn(common_data_url) as conn:
        authdb.create_user(conn, "chg@example.com", hash_password("TempPass1"))
    app_client.post("/api/login", json={"email": "chg@example.com",
                                        "password": "TempPass1"})
    resp = app_client.post("/api/change-password", json={
        "current_password": "TempPass1", "new_password": "BrandNew123"})
    assert resp.status_code == 200
    fresh = TestClient(app_client.app)
    ok = fresh.post("/api/login", json={"email": "chg@example.com",
                                        "password": "BrandNew123"})
    assert ok.status_code == 200
    assert ok.json()["must_change_password"] is False


def test_logout_clears_session(app_client):
    app_client.post("/api/login", json={"email": "test@example.com",
                                        "password": "test-password"})
    assert app_client.post("/api/logout").status_code == 200
    assert app_client.get("/api/me").status_code == 401


def test_me_includes_is_admin(client):
    resp = client.get("/api/me")
    assert resp.status_code == 200
    body = resp.json()
    assert "is_admin" in body
    assert body["is_admin"] is True  # the seeded test user is admin


def test_me_for_non_admin(non_admin_client):
    resp = non_admin_client.get("/api/me")
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False
