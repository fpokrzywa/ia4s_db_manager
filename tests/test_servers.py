"""Tests for the server registry HTTP routes."""


def test_list_servers_includes_seed(client):
    resp = client.get("/api/servers")
    assert resp.status_code == 200
    labels = [s["label"] for s in resp.json()]
    assert "test-server" in labels
    assert all("password_enc" not in s for s in resp.json())


def test_create_server(client):
    resp = client.post("/api/servers", json={
        "label": "staging", "host": "stg.example.com", "port": 5432,
        "username": "admin", "password": "pw"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["label"] == "staging"
    assert "password_enc" not in body


def test_create_duplicate_label_conflicts(client):
    client.post("/api/servers", json={"label": "dup", "host": "h",
                                      "username": "u", "password": "pw"})
    resp = client.post("/api/servers", json={"label": "dup", "host": "h",
                                             "username": "u", "password": "pw"})
    assert resp.status_code == 409


def test_create_server_requires_password(client):
    resp = client.post("/api/servers", json={"label": "nopw", "host": "h",
                                             "username": "u"})
    assert resp.status_code == 400


def test_update_server(client):
    created = client.post("/api/servers", json={
        "label": "edit-me", "host": "h", "username": "u",
        "password": "pw"}).json()
    resp = client.patch(f"/api/servers/{created['id']}", json={
        "label": "edited", "host": "h2", "port": 5433, "username": "u",
        "sslmode": "require"})
    assert resp.status_code == 200
    assert resp.json()["host"] == "h2" and resp.json()["label"] == "edited"


def test_delete_server(client):
    created = client.post("/api/servers", json={
        "label": "temp", "host": "h", "username": "u",
        "password": "pw"}).json()
    assert client.delete(f"/api/servers/{created['id']}").status_code == 200
    assert client.delete(f"/api/servers/{created['id']}").status_code == 404


def test_set_and_get_active_server(client):
    created = client.post("/api/servers", json={
        "label": "pick-me", "host": "h", "username": "u",
        "password": "pw"}).json()
    set_resp = client.post("/api/active-server",
                           json={"server_id": created["id"]})
    assert set_resp.status_code == 200
    assert client.get("/api/active-server").json()["id"] == created["id"]


def test_test_endpoint_reports_failure(client):
    created = client.post("/api/servers", json={
        "label": "unreachable", "host": "203.0.113.9", "port": 5432,
        "username": "u", "password": "pw"}).json()
    resp = client.post(f"/api/servers/{created['id']}/test")
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_test_endpoint_does_not_leak_password(client):
    """A failed connection test must never echo the stored password."""
    secret = "p@ss-do-not-leak-7799"
    created = client.post("/api/servers", json={
        "label": "leak-check", "host": "203.0.113.9", "port": 5432,
        "username": "u", "password": secret}).json()
    resp = client.post(f"/api/servers/{created['id']}/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert secret not in (body.get("error") or "")


def test_patch_without_password_keeps_stored_password(client, common_data_url):
    """PATCH with no password field leaves the stored password unchanged."""
    from dbmanager import serverdb
    from dbmanager.authdb import auth_conn
    created = client.post("/api/servers", json={
        "label": "keep-pw", "host": "h", "username": "u",
        "password": "orig-secret"}).json()
    with auth_conn(common_data_url) as conn:
        before = serverdb.get_server(conn, created["id"])["password_enc"]
    resp = client.patch(f"/api/servers/{created['id']}", json={
        "label": "keep-pw2", "host": "h2", "username": "u"})
    assert resp.status_code == 200
    with auth_conn(common_data_url) as conn:
        after = serverdb.get_server(conn, created["id"])["password_enc"]
    assert after == before
