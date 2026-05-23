import pytest
from dbmanager import pools


@pytest.fixture(autouse=True)
def _close_pools_after():
    yield
    pools.close_all()


def test_common_data_pool_returns_same_pool(monkeypatch, common_data_url):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    a = pools.common_data_pool()
    b = pools.common_data_pool()
    assert a is b


def test_common_data_pool_connection_uses_dict_rows(monkeypatch, common_data_url):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    p = pools.common_data_pool()
    with p.connection() as conn:
        row = conn.execute("SELECT 1 AS n").fetchone()
        assert row["n"] == 1


def test_server_pool_returns_same_pool(server_url):
    a = pools.server_pool(server_url)
    b = pools.server_pool(server_url)
    assert a is b
    with a.connection() as conn:
        assert conn.execute("SELECT 1 AS n").fetchone()["n"] == 1


def test_target_pool_lru_eviction(monkeypatch):
    """The (LRU+1)-th distinct (server, dbname) evicts the oldest pool."""
    class FakePool:
        def __init__(self, *a, **kw):
            self.closed = False
        def close(self):
            self.closed = True

    def fake_make(conninfo, *, autocommit):
        p = FakePool()
        pools._all_pools.append(p)
        return p

    monkeypatch.setattr(pools, "_make_pool", fake_make)

    pool0 = pools.target_pool("host=server-x", "db0")
    for i in range(1, pools._TARGET_POOL_LRU + 1):
        pools.target_pool("host=server-x", f"db{i}")
    assert ("host=server-x", "db0") not in pools._target_pools
    assert pool0.closed


def test_close_all_closes_pools_and_clears_registry(monkeypatch, common_data_url):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    p = pools.common_data_pool()
    assert not p.closed
    pools.close_all()
    assert p.closed
    assert pools._common_pools == {}
    assert pools._all_pools == []
