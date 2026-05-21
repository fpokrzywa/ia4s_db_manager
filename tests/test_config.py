import pytest
from dbmanager.config import Settings


def test_from_env_reads_all_values(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/postgres")
    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setenv("APP_SECRET", "x" * 32)
    s = Settings.from_env()
    assert s.database_url == "postgresql://localhost/postgres"
    assert s.app_password == "secret"
    assert s.app_secret == "x" * 32


def test_from_env_missing_value_raises(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setenv("APP_SECRET", "x" * 32)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        Settings.from_env()
