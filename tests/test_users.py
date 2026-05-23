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


def test_promote_user_to_admin(client, common_data_url):
    """An admin promotes a non-admin user."""
    from dbmanager.passwords import hash_password
    import psycopg
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        row = conn.execute("""
            INSERT INTO users (email, password_hash, must_change_password)
            VALUES (%s, %s, false)
            ON CONFLICT (email) DO UPDATE SET email=excluded.email
            RETURNING id
        """, ("promotable@example.com", hash_password("pw"))).fetchone()
        promo_id = row[0]
    resp = client.patch(f"/api/users/{promo_id}/admin", json={"is_admin": True})
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is True


def test_demote_last_admin_returns_400(client):
    """Demoting the sole admin (the seeded test user) is refused."""
    from dbmanager.config import Settings
    import psycopg
    with psycopg.connect(Settings.from_env().common_data_url) as conn:
        me_id = conn.execute(
            "SELECT id FROM users WHERE email='test@example.com'"
        ).fetchone()[0]
    resp = client.patch(f"/api/users/{me_id}/admin", json={"is_admin": False})
    assert resp.status_code == 400
    assert "last admin" in resp.json()["detail"].lower()


def test_non_admin_cannot_promote(non_admin_client, common_data_url):
    from dbmanager.passwords import hash_password
    import psycopg
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        row = conn.execute("""
            INSERT INTO users (email, password_hash, must_change_password)
            VALUES (%s, %s, false)
            ON CONFLICT (email) DO UPDATE SET email=excluded.email
            RETURNING id
        """, ("victim@example.com", hash_password("pw"))).fetchone()
        target = row[0]
    resp = non_admin_client.patch(
        f"/api/users/{target}/admin", json={"is_admin": True})
    assert resp.status_code == 403


def test_demote_unknown_user_404(client):
    resp = client.patch("/api/users/999999/admin", json={"is_admin": True})
    assert resp.status_code == 404
