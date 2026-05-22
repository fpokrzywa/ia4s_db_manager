import pytest
from dbmanager.config import Settings


def test_from_env_reads_all_values(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/postgres")
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", "postgresql://localhost/common_data")
    monkeypatch.setenv("APP_SECRET", "x" * 32)
    s = Settings.from_env()
    assert s.database_url == "postgresql://localhost/postgres"
    assert s.common_data_url == "postgresql://localhost/common_data"
    assert s.app_secret == "x" * 32


def test_from_env_missing_common_data_url_raises(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/postgres")
    monkeypatch.delenv("DATABASE_COMMON_DATA_URL", raising=False)
    monkeypatch.setenv("APP_SECRET", "x" * 32)
    with pytest.raises(RuntimeError, match="DATABASE_COMMON_DATA_URL"):
        Settings.from_env()


def test_from_env_short_app_secret_raises(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/postgres")
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", "postgresql://localhost/common_data")
    monkeypatch.setenv("APP_SECRET", "short")
    with pytest.raises(RuntimeError, match="APP_SECRET"):
        Settings.from_env()


def test_from_env_allows_missing_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", "postgresql://localhost/common_data")
    monkeypatch.setenv("APP_SECRET", "x" * 32)
    assert Settings.from_env().database_url is None
