# Lazy-Load Sidebar Tables & Connection Pooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the app feel snappy by fetching sidebar tables only on expand, and by reusing pooled Postgres connections instead of opening fresh ones per request.

**Architecture:** Frontend `loadSidebar` rewritten to render database rows without prefetching tables; tables are loaded on toggle-expand. Backend gets a new `pools.py` module providing three `psycopg_pool.ConnectionPool` helpers (`common_data_pool`, `server_pool`, `target_pool`); `deps.py` is refactored to borrow connections from those pools instead of opening fresh ones; FastAPI gets a `lifespan` that closes the pools at shutdown; the test suite adds a per-test teardown.

**Tech Stack:** FastAPI, psycopg 3, `psycopg-pool` (new dep), vanilla-JS ES modules, pytest.

**Spec:** `docs/superpowers/specs/2026-05-22-lazy-load-and-pool-design.md`

**Branch:** `feature/lazy-load-and-pool` (already created off `main`).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/dbmanager/web/app.js` | MODIFY — `loadSidebar` rewritten to lazy-load tables on expand. |
| `pyproject.toml` | MODIFY — add `psycopg-pool>=3.2`. |
| `src/dbmanager/pools.py` | NEW — `common_data_pool`, `server_pool`, `target_pool`, `close_all`. |
| `tests/test_pools.py` | NEW — pool reuse, `dict_row` configuration, LRU eviction, `close_all`. |
| `src/dbmanager/deps.py` | MODIFY — borrow from pools instead of cold-connect. |
| `src/dbmanager/webapp.py` | MODIFY — `lifespan` warms common_data, closes all pools on shutdown. |
| `tests/conftest.py` | MODIFY — per-test autouse fixture calls `pools.close_all()`. |

`src/dbmanager/db.py` (`server_conn`, `db_conn`) is UNCHANGED — it stays as the cold-connect path for CLI (`init-auth`) and any direct callers.

Suite baseline at start of this work: **100 passed**. Task 1 adds no backend tests → 100. Task 2 adds 5 new tests → 105. Task 3 adds no new tests but refactors connections to use pools → 105.

Test environment: tests run against a live Postgres via `DATABASE_URL` in `.env` (pytest-postgresql noproc mode). Run `pytest -q` as a SINGLE FOREGROUND invocation — overlapping runs collide on the test template database and produce spurious `dbm_pytest`/`InvalidCatalogName` errors. If you see those, re-run once cleanly.

---

## Task 1: Lazy-load sidebar tables (frontend)

**Files:** Modify `src/dbmanager/web/app.js` (the `loadSidebar` function).

No automated frontend test — verify with `node --check` and the unchanged backend suite.

- [ ] **Step 1: Replace `loadSidebar` in `src/dbmanager/web/app.js`**

`loadSidebar` is preceded by the comment line `// --- sidebar ----...` and the module-level `const expandedDbs = new Set();`. Replace from the `async function loadSidebar()` line through its closing `}` (do NOT touch the comment, the `expandedDbs` const, or `selectDatabase` / `selectTable` / `openConsole` below it):

```js
async function loadSidebar() {
  const sidebar = document.getElementById("sidebar");
  sidebar.innerHTML = "";

  const newBtn = document.createElement("button");
  newBtn.textContent = "+ New database";
  newBtn.style.width = "100%";
  newBtn.onclick = () => newDatabaseDialog(loadSidebar);
  sidebar.append(newBtn);

  const consoleBtn = document.createElement("div");
  consoleBtn.className = "tree-item";
  consoleBtn.textContent = "▸ SQL Console";
  consoleBtn.onclick = () => openConsole();
  sidebar.append(consoleBtn);

  const usersBtn = document.createElement("div");
  usersBtn.className = "tree-item";
  usersBtn.textContent = "▸ Users";
  usersBtn.onclick = () => renderUsers();
  sidebar.append(usersBtn);

  const serversBtn = document.createElement("div");
  serversBtn.className = "tree-item";
  serversBtn.textContent = "▸ Servers";
  serversBtn.onclick = () => renderServers();
  sidebar.append(serversBtn);

  const databases = await get("/api/databases");
  for (const db of databases) {
    const dbEl = document.createElement("div");
    dbEl.className = "tree-item tree-db";
    dbEl.textContent = db.name;
    dbEl.oncontextmenu = (e) => {
      e.preventDefault();
      dropDatabaseDialog(db.name, loadSidebar);
    };
    dbEl.onclick = () => selectDatabase(db.name);
    dbEl.ondblclick = () => newTableDialog(db.name, loadSidebar);
    sidebar.append(dbEl);

    const tablesEl = document.createElement("div");
    sidebar.append(tablesEl);
    let loaded = false;

    const populate = async () => {
      const placeholder = document.createElement("div");
      placeholder.className = "tree-item tree-table";
      placeholder.textContent = "Loading…";
      placeholder.style.fontStyle = "italic";
      tablesEl.append(placeholder);
      let tables;
      try {
        tables = await get(`/api/databases/${encodeURIComponent(db.name)}/tables`);
      } catch { tables = []; }
      tablesEl.textContent = "";
      for (const t of tables) {
        const tEl = document.createElement("div");
        tEl.className = "tree-item tree-table";
        tEl.textContent = t.name;
        tEl.onclick = () => selectTable(db.name, t.name);
        tablesEl.append(tEl);
      }
      loaded = true;
    };

    const toggle = document.createElement("span");
    toggle.className = "tree-toggle";
    const expanded = expandedDbs.has(db.name);
    tablesEl.hidden = !expanded;
    toggle.textContent = expanded ? "−" : "+";
    if (expanded) populate();
    toggle.onclick = async (e) => {
      e.stopPropagation();
      const willExpand = tablesEl.hidden;
      tablesEl.hidden = !willExpand;
      toggle.textContent = willExpand ? "−" : "+";
      if (willExpand) {
        expandedDbs.add(db.name);
        if (!loaded) await populate();
      } else {
        expandedDbs.delete(db.name);
      }
    };
    dbEl.append(toggle);
  }
}
```

Notes:
- The `−` characters are MINUS SIGN U+2212 (matching the existing convention from the collapsible-sidebar feature) — paired with ASCII `+`.
- The previous `if (tables.length)` guard that hid the toggle for empty databases is deliberately dropped — we no longer know the table count until the user expands. A user who expands an empty database sees an empty list and can re-collapse.

- [ ] **Step 2: Syntax-check the changed JS**

Run: `node --check src/dbmanager/web/app.js`
Expected: no output, exit 0.

- [ ] **Step 3: Run the full suite to confirm no backend regression**

Run: `pytest -q`
Expected: PASS — **100 passed** (Task 1 changes no backend code).

- [ ] **Step 4: Commit**

```bash
git add src/dbmanager/web/app.js
git commit -m "feat: lazy-load sidebar tables on expand"
```
End the commit message with the trailer:
`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

---

## Task 2: `pools.py` module + tests

**Files:** Modify `pyproject.toml`; create `src/dbmanager/pools.py`, `tests/test_pools.py`.

- [ ] **Step 1: Add the `psycopg-pool` dependency to `pyproject.toml`**

In the `[project]` `dependencies` list, add `"psycopg-pool>=3.2"` (after the existing `"psycopg[binary]>=3.2"` entry):

```toml
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "psycopg[binary]>=3.2",
    "psycopg-pool>=3.2",
    "python-dotenv>=1.0",
    "itsdangerous>=2.0",
    "click>=8.1",
    "bcrypt>=4.0",
    "cryptography>=42",
]
```

Run: `pip install -e ".[dev]"` — expected: installs `psycopg-pool`.

- [ ] **Step 2: Write `tests/test_pools.py`**

Create the file:

```python
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

    pool0 = pools.target_pool("server-x", "db0")
    for i in range(1, pools._TARGET_POOL_LRU + 1):
        pools.target_pool("server-x", f"db{i}")
    assert ("server-x", "db0") not in pools._target_pools
    assert pool0.closed


def test_close_all_closes_pools_and_clears_registry(monkeypatch, common_data_url):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    p = pools.common_data_pool()
    assert not p.closed
    pools.close_all()
    assert p.closed
    assert pools._common_pools == {}
    assert pools._all_pools == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_pools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dbmanager.pools'`.

- [ ] **Step 4: Create `src/dbmanager/pools.py`**

```python
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
    target_conninfo = make_conninfo(conninfo, dbname=dbname)
    pool = _make_pool(target_conninfo, autocommit=False)
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_pools.py -v`
Expected: PASS — 5 tests pass.

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: PASS — **105 passed** (100 existing + 5 new).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/dbmanager/pools.py tests/test_pools.py
git commit -m "feat: psycopg-pool ConnectionPool helpers"
```
End the commit message with the trailer:
`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

---

## Task 3: Use the pools (deps + lifespan + test teardown)

**Files:** Modify `src/dbmanager/deps.py`, `src/dbmanager/webapp.py`, `tests/conftest.py`.

This task is the integration — every API request now borrows pooled connections instead of opening fresh ones. The suite must stay green after it.

- [ ] **Step 1: Replace `src/dbmanager/deps.py` entirely**

```python
"""Request-scoped database access for the route layer.

`active_server` resolves the session's chosen server (decrypting its stored
password) into a libpq conninfo string. `server_db`/`target_db` borrow
pooled connections to that server."""
from __future__ import annotations
from contextlib import contextmanager
from fastapi import HTTPException, Request
from dbmanager import pools, serverdb


def active_server(request: Request) -> str:
    """FastAPI dependency: the maintenance conninfo for the session's active
    server. Falls back to the default server; raises 503 if none registered."""
    with pools.common_data_pool().connection() as conn:
        server_id = request.session.get("server_id")
        server = serverdb.get_server(conn, server_id) if server_id else None
        if server is None:
            server = serverdb.default_server(conn)
        if server is None:
            raise HTTPException(
                503, "no Postgres server is registered — add one on the "
                     "Servers page")
        return serverdb.conninfo_for(server)


@contextmanager
def server_db(server: str):
    """Autocommit connection to the active server's maintenance database
    (borrowed from a pool)."""
    try:
        with pools.server_pool(server).connection() as conn:
            yield conn
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503,
                            detail=f"database error: {exc}") from exc


@contextmanager
def target_db(server: str, dbname: str):
    """Transactional connection to `dbname` on the active server (borrowed
    from a pool)."""
    try:
        with pools.target_pool(server, dbname).connection() as conn:
            yield conn
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503,
                            detail=f"database error: {exc}") from exc
```

- [ ] **Step 2: Add a `lifespan` to `src/dbmanager/webapp.py`**

The current top of `webapp.py` imports and constructs `app` like this:

```python
"""Database Manager — FastAPI app: static files and routers."""
from __future__ import annotations
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.conninfo import conninfo_to_dict
from starlette.middleware.sessions import SessionMiddleware

from dbmanager.auth import require_session
from dbmanager.deps import active_server
from dbmanager.config import Settings
from dbmanager.routes import databases, query, rows, servers, session, tables, users

WEB_DIR = Path(__file__).resolve().parent / "web"
_settings = Settings.from_env()

app = FastAPI(title="Database Manager", docs_url="/api/docs", redoc_url=None)
```

Change the imports to also pull in `asynccontextmanager` and `pools`, define a `lifespan`, and pass it to `FastAPI`:

```python
"""Database Manager — FastAPI app: static files and routers."""
from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.conninfo import conninfo_to_dict
from starlette.middleware.sessions import SessionMiddleware

from dbmanager import pools
from dbmanager.auth import require_session
from dbmanager.deps import active_server
from dbmanager.config import Settings
from dbmanager.routes import databases, query, rows, servers, session, tables, users

WEB_DIR = Path(__file__).resolve().parent / "web"
_settings = Settings.from_env()


@asynccontextmanager
async def lifespan(_app):
    """Warm the common_data pool at startup; close all pools at shutdown."""
    pools.common_data_pool()
    yield
    pools.close_all()


app = FastAPI(title="Database Manager", docs_url="/api/docs", redoc_url=None,
              lifespan=lifespan)
```

Leave everything else in `webapp.py` unchanged (`SessionMiddleware`, the static-files mount, the routes, the index handler, `server_info`).

- [ ] **Step 3: Add the per-test pool teardown to `tests/conftest.py`**

At the END of `tests/conftest.py` (after the existing `client` fixture), append:

```python


@pytest.fixture(autouse=True)
def _close_pools_after_each_test():
    """Pools are keyed by URL; each test gets a fresh throwaway database, so
    pools created during one test must not bleed into the next."""
    yield
    from dbmanager import pools
    pools.close_all()
```

(The `pytest` import is already at the top of `conftest.py`.)

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: PASS — **105 passed**, and noticeably faster (target ~1 minute vs ~11 minutes previously, with significant variance). If you see spurious `dbm_pytest`/`InvalidCatalogName` errors, re-run once cleanly; persistent unrelated DB-infra errors are an environment issue — report as a concern.

- [ ] **Step 5: Commit**

```bash
git add src/dbmanager/deps.py src/dbmanager/webapp.py tests/conftest.py
git commit -m "feat: deps and lifespan use pooled connections"
```
End the commit message with the trailer:
`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

> **Note:** the running dev server on `:8962` must be restarted after this task before pooled connections are live in the browser — the Python process does not hot-reload. Operational step, not part of the commit.

---

# Self-Review Notes

- **Spec coverage:** lazy-load `loadSidebar` rewrite with eager-fetch for `expandedDbs` entries (Task 1); the three pool helpers `common_data_pool` / `server_pool` / `target_pool`, the LRU bound on `target_pool`, the `close_all` cleanup, `dict_row` and autocommit configuration via the pool `configure` callback, the `psycopg-pool>=3.2` dependency (Task 2); the `deps.py` refactor to borrow pooled connections, the FastAPI `lifespan` warming `common_data` and closing on shutdown, the conftest per-test `close_all` teardown (Task 3). The unchanged `db.py` cold-connect helpers remain available for CLI/scripts as the spec specifies.
- **Test coverage:** pool identity reuse, `dict_row` configuration, LRU eviction (via monkeypatched fake to avoid needing many real databases), `close_all` (Task 2). Existing 100 tests cover every route through `deps`, so they exercise the pooled paths after Task 3 with no new test additions required.
- **Type consistency:** `common_data_pool() / server_pool(conninfo) / target_pool(conninfo, dbname)` all return `psycopg_pool.ConnectionPool`. `pool.connection()` is the borrow context manager used uniformly in `deps.py`. Pool `configure` callbacks set `row_factory = dict_row` everywhere; autocommit pools also set `autocommit = True`. Module-level registries (`_all_pools`, `_common_pools`, `_server_pools`, `_target_pools`) are all cleared by `close_all`.
- **Green between tasks:** Task 1 is frontend-only (suite 100 → 100). Task 2 adds the pools module + tests without any caller using it yet (suite 100 → 105). Task 3 wires the pools into `deps.py` and is the atomic switch (suite 105 → 105, much faster). After Task 3 the dev server needs a restart to load the new code.
