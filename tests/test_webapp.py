from fastapi.testclient import TestClient


def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Database Manager" in resp.text


def test_server_info_returns_host_port(client):
    resp = client.get("/api/server-info")
    assert resp.status_code == 200
    data = resp.json()
    assert "host" in data and "port" in data


def test_server_info_requires_auth(server_url, common_data_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", server_url)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    from dbmanager.webapp import app
    resp = TestClient(app).get("/api/server-info")
    assert resp.status_code == 401
