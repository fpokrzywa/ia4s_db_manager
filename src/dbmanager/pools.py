"""Connection pools for Postgres connections.

Three pool helpers, each backed by psycopg_pool.ConnectionPool:
- common_data_pool(): pool for the common_data home database.
- server_pool(conninfo): pool for an active server's maintenance database
  (autocommit; used for CREATE/DROP DATABASE).
- target_pool(conninfo, dbname): pool for a specific (server, dbname),
  transactional (used for table DDL, row CRUD, the SQL console).

Pools are created lazily on first request, cached, and closed via
close_all() on application shutdown. The target_pool cache is LRU-bounded.
"""
from __future__ import annotations
from collections import OrderedDict
from urllib.parse import urlparse, urlunparse

from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from dbmanager.config import Settings

_MIN_SIZE = 1
_MAX_SIZE = 4
_MAX_IDLE = 300         # seconds
_ACQUIRE_TIMEOUT = 10   # seconds
_TARGET_POOL_LRU = 8    # cap on cached target pools


_all_pools: list[ConnectionPool] = []
_common_pools: dict[str, ConnectionPool] = {}
_server_pools: dict[str, ConnectionPool] = {}
_target_pools: "OrderedDict[tuple[str, str], ConnectionPool]" = OrderedDict()


def _configure_autocommit(conn) -> None:
    conn.autocommit = True
    conn.row_factory = dict_row


def _configure_transactional(conn) -> None:
    conn.row_factory = dict_row


def _with_dbname(conninfo: str, dbname: str) -> str:
    """Return a copy of *conninfo* with the database name set to *dbname*.

    Supports URL format (postgresql://…) and libpq key=value format.
    Falls back to simple token append for synthetic/test conninfo strings.
    """
    parsed = urlparse(conninfo)
    if parsed.scheme in ("postgresql", "postgres"):
        return urlunparse(parsed._replace(path=f"/{dbname}"))
    try:
        return make_conninfo(conninfo, dbname=dbname)
    except Exception:
        # Synthetic conninfo (e.g. in tests where _make_pool is monkeypatched
        # and will never actually open a connection).
        return f"{conninfo} dbname={dbname}"


def _make_pool(conninfo: str, *, autocommit: bool) -> ConnectionPool:
    configure = _configure_autocommit if autocommit else _configure_transactional
    pool = ConnectionPool(
        conninfo,
        min_size=_MIN_SIZE,
        max_size=_MAX_SIZE,
        max_idle=_MAX_IDLE,
        timeout=_ACQUIRE_TIMEOUT,
        configure=configure,
        open=True,
    )
    _all_pools.append(pool)
    return pool


def common_data_pool() -> ConnectionPool:
    """Lazily-created pool for `common_data` (autocommit, dict_row)."""
    url = Settings.from_env().common_data_url
    pool = _common_pools.get(url)
    if pool is None:
        pool = _make_pool(url, autocommit=True)
        _common_pools[url] = pool
    return pool


def server_pool(conninfo: str) -> ConnectionPool:
    """Lazily-created pool for an active server's maintenance database
    (autocommit, dict_row)."""
    pool = _server_pools.get(conninfo)
    if pool is None:
        pool = _make_pool(conninfo, autocommit=True)
        _server_pools[conninfo] = pool
    return pool


def target_pool(conninfo: str, dbname: str) -> ConnectionPool:
    """Lazily-created pool for `dbname` on the active server (transactional,
    dict_row). LRU-bounded — least-recently-used pool is evicted and closed
    when the cap is exceeded."""
    key = (conninfo, dbname)
    pool = _target_pools.get(key)
    if pool is not None:
        _target_pools.move_to_end(key)
        return pool
    pool = _make_pool(_with_dbname(conninfo, dbname), autocommit=False)
    _target_pools[key] = pool
    while len(_target_pools) > _TARGET_POOL_LRU:
        _, evicted = _target_pools.popitem(last=False)
        try:
            evicted.close()
        finally:
            if evicted in _all_pools:
                _all_pools.remove(evicted)
    return pool


def close_all() -> None:
    """Close every pool created during the process lifetime and clear the
    registries. Safe to call multiple times."""
    for pool in list(_all_pools):
        try:
            pool.close()
        except Exception:
            pass
    _all_pools.clear()
    _common_pools.clear()
    _server_pools.clear()
    _target_pools.clear()
