"""Tests for user management routes."""


def test_list_users_includes_seed(client):
    resp = client.get("/api/users")
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert "test@example.com" in emails
    assert all("password_hash" not in u for u in resp.json())


def test_create_user(client):
    resp = client.post("/api/users", json={"email": "new@example.com",
                                           "password": "TempPass123"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new@example.com"
    assert body["must_change_password"] is True
    assert "password_hash" not in body


def test_create_duplicate_user_conflicts(client):
    client.post("/api/users", json={"email": "dup@example.com",
                                    "password": "TempPass123"})
    resp = client.post("/api/users", json={"email": "dup@example.com",
                                           "password": "TempPass123"})
    assert resp.status_code == 409


def test_create_user_short_password(client):
    resp = client.post("/api/users", json={"email": "x@example.com",
                                           "password": "short"})
    assert resp.status_code == 400


def test_deactivate_and_reactivate_user(client):
    created = client.post("/api/users", json={"email": "tog@example.com",
                                              "password": "TempPass123"}).json()
    off = client.patch(f"/api/users/{created['id']}", json={"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False
    on = client.patch(f"/api/users/{created['id']}", json={"is_active": True})
    assert on.json()["is_active"] is True


def test_reset_password_sets_must_change(client):
    created = client.post("/api/users", json={"email": "rst@example.com",
                                              "password": "TempPass123"}).json()
    resp = client.patch(f"/api/users/{created['id']}",
                        json={"password": "ResetPass123"})
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is True


def test_patch_missing_user_404(client):
    resp = client.patch("/api/users/999999", json={"is_active": False})
    assert resp.status_code == 404
