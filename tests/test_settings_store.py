import psycopg
from dbmanager import settings_store


def test_set_and_get_round_trip(common_data_url):
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        settings_store.set_setting(conn, "x", {"a": 1, "b": [2, 3]})
        out = settings_store.get_setting(conn, "x")
    assert out == {"a": 1, "b": [2, 3]}


def test_get_missing_returns_none(common_data_url):
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        assert settings_store.get_setting(conn, "nope") is None


def test_set_overwrites_existing(common_data_url):
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        settings_store.set_setting(conn, "y", {"v": 1})
        settings_store.set_setting(conn, "y", {"v": 2})
        out = settings_store.get_setting(conn, "y")
    assert out == {"v": 2}
