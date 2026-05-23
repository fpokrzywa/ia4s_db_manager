def test_get_theme_is_public(server_url, common_data_url, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("DATABASE_URL", server_url)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    from dbmanager.webapp import app
    # No login at all.
    resp = TestClient(app).get("/api/theme")
    assert resp.status_code == 200
    body = resp.json()
    assert body["preset"] == "foundry"
    assert body["overrides"] == {}
    assert body["effective"]["--soot"] == "#15110c"


def test_patch_theme_admin_saves(client):
    resp = client.patch("/api/theme", json={
        "preset": "slate", "overrides": {"--iron": "#abcdef"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["preset"] == "slate"
    assert body["overrides"] == {"--iron": "#abcdef"}
    assert body["effective"]["--iron"] == "#abcdef"
    # And it persists.
    body2 = client.get("/api/theme").json()
    assert body2["preset"] == "slate"
    assert body2["overrides"] == {"--iron": "#abcdef"}


def test_patch_theme_non_admin_returns_403(non_admin_client):
    resp = non_admin_client.patch(
        "/api/theme", json={"preset": "slate", "overrides": {}})
    assert resp.status_code == 403


def test_patch_theme_invalid_preset_400(client):
    resp = client.patch("/api/theme", json={"preset": "nope", "overrides": {}})
    assert resp.status_code == 400


def test_patch_theme_invalid_color_400(client):
    resp = client.patch("/api/theme", json={
        "preset": "foundry", "overrides": {"--iron": "not-a-color"}})
    assert resp.status_code == 400


def test_patch_theme_uncurated_var_400(client):
    resp = client.patch("/api/theme", json={
        "preset": "foundry", "overrides": {"--soot-1": "#000000"}})
    assert resp.status_code == 400


def test_list_presets_admin_only(client, non_admin_client):
    a = client.get("/api/themes")
    assert a.status_code == 200
    body = a.json()
    assert set(body["presets"]) == {"foundry", "slate", "daylight"}
    assert "--iron" in body["curated_vars"]
    n = non_admin_client.get("/api/themes")
    assert n.status_code == 403
