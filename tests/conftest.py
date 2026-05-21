"""Pytest configuration.

pytest-postgresql cannot start a throwaway cluster on this machine (no local
Postgres toolchain), so tests run against the existing Postgres server using
pytest-postgresql's "noproc" mode. Connection details come from DATABASE_URL
in .env; each test run creates and drops its own databases.
"""
import os

from dotenv import load_dotenv

# Load the real DATABASE_URL from .env before anything else reads the env.
load_dotenv()
os.environ.setdefault("APP_PASSWORD", "test-password")
os.environ.setdefault("APP_SECRET", "test-secret-key-at-least-32-characters")

import pytest
from psycopg.conninfo import conninfo_to_dict
from pytest_postgresql import factories

_params = conninfo_to_dict(os.environ["DATABASE_URL"])

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
