"""Pytest configuration.

pytest-postgresql cannot start a throwaway cluster on this machine (no local
Postgres toolchain), so tests run against the existing Postgres server using
pytest-postgresql's "noproc" mode. Connection details come from DATABASE_URL
in .env; each test run creates and drops its own databases.
"""
import os

import psycopg
from dotenv import load_dotenv

# Load the real DATABASE_URL from .env before anything else reads the env.
load_dotenv()
os.environ.setdefault("APP_SECRET", "test-secret-key-at-least-32-characters")

import pytest
from psycopg.conninfo import conninfo_to_dict
from pytest_postgresql import factories

_params = conninfo_to_dict(os.environ["DATABASE_URL"])


def _drop_stale_test_databases() -> None:
    """Drop any dbm_pytest* databases left behind by an interrupted prior run,
    so pytest-postgresql can recreate its template/test databases cleanly."""
    import psycopg

    server = (
        f"postgresql://{_params.get('user')}:{_params.get('password') or ''}"
        f"@{_params.get('host', '127.0.0.1')}:{_params.get('port', 5432)}/postgres"
    )
    try:
        with psycopg.connect(server, autocommit=True, connect_timeout=10) as conn:
            conn.execute("UPDATE pg_database SET datistemplate = false "
                         "WHERE datname LIKE 'dbm_pytest%'")
            stale = conn.execute("SELECT datname FROM pg_database "
                                 "WHERE datname LIKE 'dbm_pytest%'").fetchall()
            for (name,) in stale:
                conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    except Exception:
        pass  # best-effort; pytest-postgresql will surface any real problem


_drop_stale_test_databases()

postgresql_noproc = factories.postgresql_noproc(
    host=_params.get("host", "127.0.0.1"),
    port=int(_params.get("port", 5432)),
    user=_params.get("user"),
    password=_params.get("password"),
    dbname="dbm_pytest",
)
postgresql = factories.postgresql("postgresql_noproc")


@pytest.fixture
def server_url(postgresql):
    """A DATABASE_URL pointing at the server's 'postgres' database."""
    info = postgresql.info
    return (
        f"postgresql://{info.user}:{info.password or ''}"
        f"@{info.host}:{info.port}/postgres"
    )


@pytest.fixture
def common_data_url(postgresql):
    """A throwaway database with the auth schema applied and a seeded test
    user (test@example.com / test-password, no forced change)."""
    info = postgresql.info
    url = (f"postgresql://{info.user}:{info.password or ''}"
           f"@{info.host}:{info.port}/{info.dbname}")
    from dbmanager.authdb import apply_schema
    from dbmanager.serverdb import apply_schema as apply_servers_schema
    from dbmanager.passwords import hash_password
    apply_schema(url)
    apply_servers_schema(url)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO users (email, password_hash, must_change_password) "
            "VALUES (%s, %s, false) ON CONFLICT (email) DO NOTHING",
            ("test@example.com", hash_password("test-password")))
    return url


@pytest.fixture
def client(server_url, common_data_url, monkeypatch):
    """A TestClient logged in as the seeded test user, with a default server
    (the throwaway Postgres) registered."""
    from fastapi.testclient import TestClient
    from psycopg.conninfo import conninfo_to_dict
    from dbmanager import authdb, serverdb
    monkeypatch.setenv("DATABASE_URL", server_url)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    p = conninfo_to_dict(server_url)
    with authdb.auth_conn(common_data_url) as conn:
        if not serverdb.list_servers(conn):
            serverdb.create_server(
                conn, label="test-server", host=p.get("host"),
                port=int(p.get("port") or 5432), username=p.get("user"),
                password=p.get("password") or "", maintenance_db="postgres",
                is_default=True)
    from dbmanager.webapp import app
    c = TestClient(app)
    resp = c.post("/api/login", json={"email": "test@example.com",
                                      "password": "test-password"})
    assert resp.status_code == 200, resp.text
    return c
