# Postgres Database Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-hosted web app that gives one operator full CRUD over a Postgres server — create/drop databases, full table DDL, row editing, and a SQL console.

**Architecture:** A FastAPI backend serves a single static vanilla-JS page. Postgres has no `USE database`, so the app keeps an autocommit *server* connection to the `postgres` maintenance database (for database-level operations) and transactional *per-database* connections (for tables, rows, SQL). A single password gates the app via a signed session cookie. Packaged as a Docker container.

**Tech Stack:** Python 3.11+, FastAPI, `psycopg` 3, `python-dotenv`, `click`, vanilla JS ES modules, `pytest` + `pytest-postgresql`, Docker.

**Reference:** This mirrors the FORGE project at `S:\Development_2026\news_agent` — same FastAPI + static-page + psycopg pattern, same per-request-connection style, same `HTTPException` error conventions.

**Spec:** `docs/superpowers/specs/2026-05-21-postgres-database-manager-design.md`

---

## File Structure

Backend package `src/dbmanager/`:

| File | Responsibility |
|---|---|
| `config.py` | `Settings` dataclass loaded from `.env`. |
| `db.py` | `server_conn()` (autocommit) and `db_conn()` (transactional) connection helpers. |
| `sqlbuild.py` | Identifier-safe SQL builders + validation. (Named `sqlbuild`, not `sql`, to avoid shadowing `psycopg.sql`.) |
| `inspect.py` | Introspection queries for databases, tables, columns, constraints, indexes. |
| `auth.py` | Password check + session-cookie guard dependency. |
| `deps.py` | Request-scoped DB context managers that turn connection failures into HTTP 503. |
| `webapp.py` | FastAPI app: middleware, login routes, static mount, router registration. |
| `routes/databases.py` | Database list/create/drop. |
| `routes/tables.py` | Table list/inspect/create/rename/drop + column/constraint/index DDL. |
| `routes/rows.py` | Paginated row browsing + insert/update/delete. |
| `routes/query.py` | SQL console execution. |
| `cli.py` | `click` CLI with a `web` subcommand. |

Frontend `src/dbmanager/web/` (ES modules, no build step):

| File | Responsibility |
|---|---|
| `index.html` | App shell + login screen markup. |
| `app.css` | All styles. |
| `api.js` | `fetch` wrapper; redirects to login on 401. |
| `app.js` | Entry point: login flow, sidebar tree, panel routing. |
| `databases.js` | Database overview + create/drop UI. |
| `tables.js` | Table Structure tab + DDL controls. |
| `rows.js` | Data grid + row insert/update/delete. |
| `query.js` | SQL console. |

Tests `tests/`: `conftest.py`, `test_config.py`, `test_auth.py`, `test_sqlbuild.py`, `test_inspect.py`, `test_databases.py`, `test_tables.py`, `test_rows.py`, `test_query.py`.

---

# Phase 1 — Foundation

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `src/dbmanager/__init__.py`, `src/dbmanager/routes/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Initialise git**

```bash
cd s:/Development_2026/ia4service/database_manager
git init
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "dbmanager"
version = "0.1.0"
description = "Postgres Database Manager — web app for full CRUD over a Postgres server"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "psycopg[binary]>=3.2",
    "python-dotenv>=1.0",
    "itsdangerous>=2.0",
    "click>=8.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-postgresql>=6.0",
    "httpx>=0.27",
]

[project.scripts]
dbmanager = "dbmanager.cli:cli"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
dbmanager = ["web/*.html", "web/*.css", "web/*.js"]
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.egg-info/
.pytest_cache/
.venv/
venv/
.env
```

- [ ] **Step 4: Create `.env.example`**

```
# Point at the 'postgres' maintenance database — the app substitutes the
# database name per request for table and row operations.
DATABASE_URL=postgresql://admin:password@127.0.0.1:5432/postgres
# Password required to log in to the web UI.
APP_PASSWORD=change-me
# Random 32+ character string used to sign session cookies.
APP_SECRET=change-me-to-a-long-random-string
```

- [ ] **Step 5: Create empty package files**

Create `src/dbmanager/__init__.py`, `src/dbmanager/routes/__init__.py`, and `tests/__init__.py`, each empty.

- [ ] **Step 6: Install and verify**

Run: `pip install -e ".[dev]"`
Expected: installs successfully; `python -c "import dbmanager"` exits 0.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore .env.example src tests
git commit -m "chore: project scaffold"
```

---

## Task 2: Settings from environment

**Files:**
- Create: `src/dbmanager/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
import os
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dbmanager.config'`

- [ ] **Step 3: Write `src/dbmanager/config.py`**

```python
"""Loads .env and exposes typed settings."""
from __future__ import annotations
from dataclasses import dataclass
import os
from dotenv import load_dotenv

# Load .env once at import; env vars already set win.
load_dotenv(override=False)


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_password: str
    app_secret: str

    @classmethod
    def from_env(cls) -> "Settings":
        db = os.environ.get("DATABASE_URL")
        if not db:
            raise RuntimeError("DATABASE_URL is required in environment or .env")
        password = os.environ.get("APP_PASSWORD")
        if not password:
            raise RuntimeError("APP_PASSWORD is required in environment or .env")
        secret = os.environ.get("APP_SECRET")
        if not secret:
            raise RuntimeError("APP_SECRET is required in environment or .env")
        return cls(database_url=db, app_password=password, app_secret=secret)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dbmanager/config.py tests/test_config.py
git commit -m "feat: settings loaded from environment"
```

---

## Task 3: Connection helpers

**Files:**
- Create: `src/dbmanager/db.py`
- Test: `tests/test_db.py`, `tests/conftest.py`

- [ ] **Step 1: Create `tests/conftest.py`**

This sets import-time env defaults (so `webapp` imports cleanly) and provides a `server_url` fixture pointing at the test cluster's `postgres` database.

```python
import os

# Set before any dbmanager module is imported.
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/postgres")
os.environ.setdefault("APP_PASSWORD", "test-password")
os.environ.setdefault("APP_SECRET", "test-secret-key-at-least-32-characters")

import pytest


@pytest.fixture
def server_url(postgresql):
    """A DATABASE_URL pointing at the test cluster's 'postgres' database."""
    info = postgresql.info
    return (
        f"postgresql://{info.user}:{info.password or ''}"
        f"@{info.host}:{info.port}/postgres"
    )
```

- [ ] **Step 2: Write the failing test**

```python
from dbmanager.db import server_conn, db_conn


def test_server_conn_is_autocommit(server_url):
    with server_conn(server_url) as conn:
        assert conn.autocommit is True
        row = conn.execute("SELECT 1 AS one").fetchone()
        assert row["one"] == 1


def test_db_conn_targets_named_database(server_url):
    with db_conn(server_url, "postgres") as conn:
        row = conn.execute("SELECT current_database() AS db").fetchone()
        assert row["db"] == "postgres"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dbmanager.db'`

- [ ] **Step 4: Write `src/dbmanager/db.py`**

```python
"""Postgres connection helpers.

server_conn -> autocommit connection to the 'postgres' maintenance database,
used for CREATE/DROP DATABASE (which cannot run inside a transaction).
db_conn -> transactional connection to a named database, used for everything
else (table DDL, row CRUD, the SQL console).
"""
from __future__ import annotations
from contextlib import contextmanager
import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row


@contextmanager
def server_conn(database_url: str):
    """Yield an autocommit connection to the maintenance database."""
    conn = psycopg.connect(database_url, row_factory=dict_row, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def db_conn(database_url: str, dbname: str):
    """Yield a transactional connection to `dbname` on the same server."""
    conninfo = make_conninfo(database_url, dbname=dbname)
    conn = psycopg.connect(conninfo, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/db.py tests/test_db.py tests/conftest.py
git commit -m "feat: server and per-database connection helpers"
```

---

## Task 4: Auth helpers

**Files:**
- Create: `src/dbmanager/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from fastapi import HTTPException
from dbmanager.auth import password_matches, require_session


class FakeRequest:
    def __init__(self, session):
        self.session = session


def test_password_matches_true():
    assert password_matches("hunter2", "hunter2") is True


def test_password_matches_false():
    assert password_matches("wrong", "hunter2") is False


def test_require_session_allows_authenticated():
    require_session(FakeRequest({"authenticated": True}))  # no raise


def test_require_session_rejects_anonymous():
    with pytest.raises(HTTPException) as exc:
        require_session(FakeRequest({}))
    assert exc.value.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dbmanager.auth'`

- [ ] **Step 3: Write `src/dbmanager/auth.py`**

```python
"""Password check and session-cookie guard."""
from __future__ import annotations
import hmac
from fastapi import HTTPException, Request


def password_matches(supplied: str, expected: str) -> bool:
    """Constant-time comparison of the supplied login password."""
    return hmac.compare_digest(supplied, expected)


def require_session(request: Request) -> None:
    """FastAPI dependency: reject requests without an authenticated session."""
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="authentication required")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dbmanager/auth.py tests/test_auth.py
git commit -m "feat: password check and session guard"
```

---

## Task 5: Request-scoped DB dependencies

**Files:**
- Create: `src/dbmanager/deps.py`

- [ ] **Step 1: Write `src/dbmanager/deps.py`**

No separate test — exercised by every route test. It wraps the Task 3 helpers so a failed connection becomes a clean HTTP 503, while `HTTPException`s raised mid-query pass through unchanged (same pattern as FORGE's `_db()`).

```python
"""Request-scoped database context managers for the route layer."""
from __future__ import annotations
from contextlib import contextmanager
from fastapi import HTTPException
from dbmanager.config import Settings
from dbmanager.db import server_conn, db_conn


@contextmanager
def server_db():
    """Autocommit connection to the maintenance database, or HTTP 503."""
    settings = Settings.from_env()
    try:
        with server_conn(settings.database_url) as conn:
            yield conn
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database error: {exc}") from exc


@contextmanager
def target_db(dbname: str):
    """Transactional connection to `dbname`, or HTTP 503."""
    settings = Settings.from_env()
    try:
        with db_conn(settings.database_url, dbname) as conn:
            yield conn
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database error: {exc}") from exc
```

- [ ] **Step 2: Verify it imports**

Run: `python -c "from dbmanager.deps import server_db, target_db"`
Expected: exits 0

- [ ] **Step 3: Commit**

```bash
git add src/dbmanager/deps.py
git commit -m "feat: request-scoped db dependencies"
```

---

## Task 6: FastAPI app skeleton with login

**Files:**
- Create: `src/dbmanager/webapp.py`, `src/dbmanager/cli.py`, `src/dbmanager/web/index.html` (placeholder)
- Test: `tests/test_webapp.py`

- [ ] **Step 1: Create placeholder `src/dbmanager/web/index.html`**

```html
<!doctype html>
<html><head><title>Database Manager</title></head>
<body><h1>Database Manager</h1></body></html>
```

- [ ] **Step 2: Write the failing test**

```python
from fastapi.testclient import TestClient
from dbmanager.webapp import app

client = TestClient(app)


def test_index_served():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Database Manager" in resp.text


def test_login_rejects_wrong_password():
    resp = client.post("/api/login", json={"password": "nope"})
    assert resp.status_code == 401


def test_login_accepts_correct_password():
    resp = client.post("/api/login", json={"password": "test-password"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_logout_clears_session():
    c = TestClient(app)
    c.post("/api/login", json={"password": "test-password"})
    resp = c.post("/api/logout")
    assert resp.status_code == 200
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_webapp.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dbmanager.webapp'`

- [ ] **Step 4: Write `src/dbmanager/webapp.py`**

Routers (`databases`, `tables`, `rows`, `query`) are added in later phases; this task leaves their `include_router` calls commented with a marker so later tasks know exactly where to add them.

```python
"""Database Manager — FastAPI app: login, static files, routers."""
from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from dbmanager.auth import password_matches
from dbmanager.config import Settings

WEB_DIR = Path(__file__).resolve().parent / "web"
_settings = Settings.from_env()

app = FastAPI(title="Database Manager", docs_url="/api/docs", redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=_settings.app_secret,
                   https_only=False)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


class LoginBody(BaseModel):
    password: str


@app.post("/api/login")
def login(body: LoginBody, request: Request) -> dict:
    """Check the password and start a session."""
    settings = Settings.from_env()
    if not password_matches(body.password, settings.app_password):
        raise HTTPException(status_code=401, detail="incorrect password")
    request.session["authenticated"] = True
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request) -> dict:
    """End the session."""
    request.session.clear()
    return {"ok": True}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the single-page app shell."""
    return FileResponse(WEB_DIR / "index.html")


# --- routers (added in later phases) ----------------------------------------
# ROUTER REGISTRATION MARKER — do not remove
```

- [ ] **Step 5: Write `src/dbmanager/cli.py`**

```python
"""Command-line entry point."""
from __future__ import annotations
import click
import uvicorn


@click.group()
def cli() -> None:
    """Database Manager."""


@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind address.")
@click.option("--port", default=8000, type=int, help="Bind port.")
@click.option("--reload", is_flag=True, help="Auto-reload on code change.")
def web(host: str, port: int, reload: bool) -> None:
    """Run the web app."""
    uvicorn.run("dbmanager.webapp:app", host=host, port=port, reload=reload)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_webapp.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
git add src/dbmanager/webapp.py src/dbmanager/cli.py src/dbmanager/web/index.html tests/test_webapp.py
git commit -m "feat: FastAPI app skeleton with login and CLI"
```

---

## Task 7: Frontend shell and login screen

**Files:**
- Modify: `src/dbmanager/web/index.html`
- Create: `src/dbmanager/web/app.css`, `src/dbmanager/web/api.js`, `src/dbmanager/web/app.js`

- [ ] **Step 1: Replace `src/dbmanager/web/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Database Manager</title>
  <link rel="stylesheet" href="/static/app.css">
</head>
<body>
  <div id="login" class="login hidden">
    <form id="login-form" class="login-card">
      <h1>Database Manager</h1>
      <input id="login-password" type="password" placeholder="Password" autocomplete="current-password" required>
      <button type="submit">Log in</button>
      <p id="login-error" class="error"></p>
    </form>
  </div>

  <div id="app" class="app hidden">
    <header class="topbar">
      <span class="title">Database Manager</span>
      <span id="server-label" class="server"></span>
      <button id="logout" class="ghost">Log out</button>
    </header>
    <div class="body">
      <aside id="sidebar" class="sidebar"></aside>
      <main id="panel" class="panel"></main>
    </div>
  </div>

  <script type="module" src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `src/dbmanager/web/app.css`**

```css
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 system-ui, sans-serif; color: #1c2128; background: #f6f8fa; }
.hidden { display: none !important; }
.error { color: #cf222e; min-height: 1.2em; margin: 4px 0 0; }

.login { display: flex; align-items: center; justify-content: center; height: 100vh; }
.login-card { background: #fff; padding: 32px; border-radius: 8px; box-shadow: 0 1px 6px rgba(0,0,0,.12); width: 300px; display: flex; flex-direction: column; gap: 12px; }
.login-card h1 { font-size: 18px; margin: 0 0 8px; }
input, select, textarea { font: inherit; padding: 6px 8px; border: 1px solid #d0d7de; border-radius: 6px; }
button { font: inherit; padding: 6px 12px; border: 1px solid #d0d7de; border-radius: 6px; background: #2da44e; color: #fff; cursor: pointer; }
button.ghost { background: #fff; color: #1c2128; }
button.danger { background: #cf222e; color: #fff; }
button:disabled { opacity: .5; cursor: not-allowed; }

.app { display: flex; flex-direction: column; height: 100vh; }
.topbar { display: flex; align-items: center; gap: 12px; padding: 8px 16px; background: #24292f; color: #fff; }
.topbar .title { font-weight: 600; }
.topbar .server { color: #adbac7; flex: 1; }
.body { display: flex; flex: 1; min-height: 0; }
.sidebar { width: 260px; background: #fff; border-right: 1px solid #d0d7de; overflow: auto; padding: 8px; }
.panel { flex: 1; overflow: auto; padding: 16px; }

.tree-item { padding: 4px 6px; cursor: pointer; border-radius: 4px; white-space: nowrap; }
.tree-item:hover { background: #f0f3f6; }
.tree-item.active { background: #ddf4ff; }
.tree-db { font-weight: 600; }
.tree-table { padding-left: 22px; }

table.grid { border-collapse: collapse; width: 100%; background: #fff; }
table.grid th, table.grid td { border: 1px solid #d0d7de; padding: 4px 8px; text-align: left; }
table.grid th { background: #f6f8fa; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.tabs { display: flex; gap: 4px; margin-bottom: 12px; }
.tabs button { background: #fff; color: #1c2128; }
.tabs button.active { background: #ddf4ff; }

.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,.4); display: flex; align-items: center; justify-content: center; }
.modal { background: #fff; padding: 24px; border-radius: 8px; width: 420px; display: flex; flex-direction: column; gap: 10px; max-height: 80vh; overflow: auto; }
.modal h2 { margin: 0; font-size: 16px; }
.row { display: flex; gap: 8px; align-items: center; }
.row label { width: 110px; }
.row > input, .row > select { flex: 1; }
.notice { color: #57606a; font-style: italic; }
```

- [ ] **Step 3: Create `src/dbmanager/web/api.js`**

```js
// Thin fetch wrapper. Throws Error(message) on failure; redirects to login on 401.
export async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(path, opts);
  if (resp.status === 401 && path !== "/api/login") {
    window.location.reload();
    throw new Error("session expired");
  }
  const data = resp.headers.get("content-type")?.includes("application/json")
    ? await resp.json() : null;
  if (!resp.ok) {
    throw new Error(data?.detail || `${resp.status} ${resp.statusText}`);
  }
  return data;
}

export const get = (p) => api("GET", p);
export const post = (p, b) => api("POST", p, b);
export const patch = (p, b) => api("PATCH", p, b);
export const del = (p, b) => api("DELETE", p, b);
```

- [ ] **Step 4: Create `src/dbmanager/web/app.js`**

The sidebar tree and panel routing land in Task 9; this version handles login/logout and shows an empty authenticated shell. `loadSidebar` is a stub later tasks replace.

```js
import { get, post } from "./api.js";

const loginEl = document.getElementById("login");
const appEl = document.getElementById("app");

async function showApp() {
  loginEl.classList.add("hidden");
  appEl.classList.remove("hidden");
  await loadSidebar();
}

function showLogin() {
  appEl.classList.add("hidden");
  loginEl.classList.remove("hidden");
}

async function loadSidebar() {
  // Replaced in Task 9.
  document.getElementById("sidebar").textContent = "Loading…";
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("login-error");
  errEl.textContent = "";
  try {
    await post("/api/login", {
      password: document.getElementById("login-password").value,
    });
    await showApp();
  } catch (err) {
    errEl.textContent = err.message;
  }
});

document.getElementById("logout").addEventListener("click", async () => {
  await post("/api/logout");
  showLogin();
});

// Probe the session: any authenticated endpoint works. Until Phase 2 adds
// /api/databases, fall back to showing the login screen.
(async function init() {
  try {
    await get("/api/databases");
    await showApp();
  } catch {
    showLogin();
  }
})();
```

- [ ] **Step 5: Verify in the browser**

Run: `dbmanager web` then open `http://127.0.0.1:8000`.
Expected: the login screen appears; a wrong password shows "incorrect password"; the correct password (`APP_PASSWORD` from `.env`) reveals the app shell with a "Loading…" sidebar. (`/api/databases` 404s for now, so first load shows the login screen — expected until Phase 2.)

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/web/
git commit -m "feat: frontend shell and login screen"
```

---

# Phase 2 — Databases

## Task 8: Database introspection + database routes

**Files:**
- Create: `src/dbmanager/inspect.py`, `src/dbmanager/sqlbuild.py`, `src/dbmanager/routes/databases.py`
- Modify: `src/dbmanager/webapp.py`
- Test: `tests/test_sqlbuild.py`, `tests/test_databases.py`

- [ ] **Step 1: Write the failing test for `sqlbuild`**

```python
import pytest
from fastapi import HTTPException
from dbmanager import sqlbuild


def test_validate_identifier_accepts_normal_name():
    sqlbuild.validate_identifier("my_table", "table name")  # no raise


def test_validate_identifier_rejects_empty():
    with pytest.raises(HTTPException) as exc:
        sqlbuild.validate_identifier("  ", "table name")
    assert exc.value.status_code == 400


def test_validate_identifier_rejects_overlong():
    with pytest.raises(HTTPException):
        sqlbuild.validate_identifier("x" * 64, "table name")


def test_validate_type_accepts_known_forms():
    for t in ["integer", "varchar(255)", "numeric(10, 2)", "text[]",
              "timestamp with time zone"]:
        sqlbuild.validate_type(t)  # no raise


def test_validate_type_rejects_injection():
    with pytest.raises(HTTPException):
        sqlbuild.validate_type("integer); DROP TABLE x; --")


def test_create_database_sql():
    rendered = sqlbuild.create_database("shop", owner=None, encoding=None).as_string()
    assert rendered == 'CREATE DATABASE "shop"'


def test_drop_database_force_sql():
    rendered = sqlbuild.drop_database("shop", force=True).as_string()
    assert rendered == 'DROP DATABASE "shop" WITH (FORCE)'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sqlbuild.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dbmanager.sqlbuild'`

- [ ] **Step 3: Write `src/dbmanager/sqlbuild.py`**

```python
"""Identifier-safe SQL builders and input validation.

Every object name reaches Postgres through psycopg.sql.Identifier — never a
formatted string. Column types and default expressions cannot be parameters,
so they are validated before being placed into SQL.
"""
from __future__ import annotations
import re
from fastapi import HTTPException
from psycopg import sql as pgsql

_TYPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]*(\([0-9, ]+\))?(\[\])?$")


def validate_identifier(name: str, label: str) -> str:
    """Return a stripped identifier or raise HTTP 400. Quoting handles safety;
    this is a sanity/UX check for empty and over-long names."""
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, f"{label} is required")
    if len(name.encode("utf-8")) > 63:
        raise HTTPException(400, f"{label} must be 63 bytes or fewer")
    return name


def validate_type(type_str: str) -> str:
    """Return a validated column type or raise HTTP 400."""
    type_str = (type_str or "").strip()
    if not _TYPE_RE.match(type_str):
        raise HTTPException(400, f"invalid column type: {type_str!r}")
    return type_str


def validate_default(expr: str) -> str:
    """Return a default expression or raise HTTP 400 (blocks statement breakout)."""
    expr = (expr or "").strip()
    if ";" in expr:
        raise HTTPException(400, "default expression may not contain ';'")
    return expr


def qualified(table: str, schema: str = "public") -> pgsql.Composable:
    """A schema-qualified table identifier."""
    return pgsql.Identifier(schema, table)


def create_database(name: str, owner: str | None,
                    encoding: str | None) -> pgsql.Composable:
    parts = [pgsql.SQL("CREATE DATABASE {}").format(pgsql.Identifier(name))]
    if owner:
        parts.append(pgsql.SQL("OWNER {}").format(pgsql.Identifier(owner)))
    if encoding:
        parts.append(pgsql.SQL("ENCODING {} TEMPLATE template0")
                     .format(pgsql.Literal(encoding)))
    return pgsql.SQL(" ").join(parts)


def drop_database(name: str, force: bool) -> pgsql.Composable:
    stmt = pgsql.SQL("DROP DATABASE {}").format(pgsql.Identifier(name))
    if force:
        stmt = pgsql.SQL("{} WITH (FORCE)").format(stmt)
    return stmt
```

- [ ] **Step 4: Run sqlbuild test to verify it passes**

Run: `pytest tests/test_sqlbuild.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Write `src/dbmanager/inspect.py`**

```python
"""Introspection queries against pg_catalog / information_schema."""
from __future__ import annotations

_DATABASES = """
    SELECT d.datname AS name,
           pg_get_userbyid(d.datdba) AS owner,
           pg_encoding_to_char(d.encoding) AS encoding,
           pg_database_size(d.datname) AS size_bytes
    FROM pg_database d
    WHERE d.datistemplate = false
    ORDER BY d.datname
"""

_TABLES = """
    SELECT t.table_name AS name,
           c.reltuples::bigint AS approx_rows,
           pg_total_relation_size(c.oid) AS size_bytes
    FROM information_schema.tables t
    JOIN pg_class c ON c.relname = t.table_name
    JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = t.table_schema
    WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
    ORDER BY t.table_name
"""

_COLUMNS = """
    SELECT column_name AS name, data_type, is_nullable,
           column_default, ordinal_position
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = %s
    ORDER BY ordinal_position
"""

_PRIMARY_KEY = """
    SELECT kcu.column_name AS name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON kcu.constraint_name = tc.constraint_name
     AND kcu.table_schema = tc.table_schema
    WHERE tc.table_schema = 'public' AND tc.table_name = %s
      AND tc.constraint_type = 'PRIMARY KEY'
    ORDER BY kcu.ordinal_position
"""

_CONSTRAINTS = """
    SELECT conname AS name,
           CASE contype WHEN 'p' THEN 'PRIMARY KEY'
                        WHEN 'f' THEN 'FOREIGN KEY'
                        WHEN 'u' THEN 'UNIQUE'
                        WHEN 'c' THEN 'CHECK' END AS type,
           pg_get_constraintdef(oid) AS definition
    FROM pg_constraint
    WHERE conrelid = ('public.' || quote_ident(%s))::regclass
    ORDER BY conname
"""

_INDEXES = """
    SELECT indexname AS name, indexdef AS definition
    FROM pg_indexes
    WHERE schemaname = 'public' AND tablename = %s
    ORDER BY indexname
"""


def list_databases(conn) -> list[dict]:
    return conn.execute(_DATABASES).fetchall()


def list_tables(conn) -> list[dict]:
    return conn.execute(_TABLES).fetchall()


def table_structure(conn, table: str) -> dict:
    """Columns, primary-key column names, constraints, and indexes."""
    columns = conn.execute(_COLUMNS, (table,)).fetchall()
    if not columns:
        return {}
    pk = [r["name"] for r in conn.execute(_PRIMARY_KEY, (table,)).fetchall()]
    constraints = conn.execute(_CONSTRAINTS, (table,)).fetchall()
    indexes = conn.execute(_INDEXES, (table,)).fetchall()
    return {"name": table, "columns": columns, "primary_key": pk,
            "constraints": constraints, "indexes": indexes}
```

- [ ] **Step 6: Write the failing test for database routes**

```python
import uuid
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(server_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", server_url)
    from dbmanager.webapp import app
    c = TestClient(app)
    c.post("/api/login", json={"password": "test-password"})
    return c


def test_list_databases_includes_postgres(client):
    resp = client.get("/api/databases")
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert "postgres" in names


def test_create_and_drop_database(client):
    name = f"dbm_test_{uuid.uuid4().hex[:8]}"
    created = client.post("/api/databases", json={"name": name})
    assert created.status_code == 201
    names = [d["name"] for d in client.get("/api/databases").json()]
    assert name in names
    dropped = client.delete(f"/api/databases/{name}")
    assert dropped.status_code == 200


def test_create_duplicate_database_conflicts(client):
    name = f"dbm_test_{uuid.uuid4().hex[:8]}"
    client.post("/api/databases", json={"name": name})
    dup = client.post("/api/databases", json={"name": name})
    assert dup.status_code == 409
    client.delete(f"/api/databases/{name}")


def test_requires_auth(server_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", server_url)
    from dbmanager.webapp import app
    resp = TestClient(app).get("/api/databases")
    assert resp.status_code == 401
```

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest tests/test_databases.py -v`
Expected: FAIL — 404 on `/api/databases` (router not registered)

- [ ] **Step 8: Write `src/dbmanager/routes/databases.py`**

```python
"""Database list / create / drop."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager import sqlbuild
from dbmanager.deps import server_db
from dbmanager.inspect import list_databases

router = APIRouter(prefix="/api/databases", tags=["databases"])


class CreateDatabaseBody(BaseModel):
    name: str
    owner: str | None = None
    encoding: str | None = None


@router.get("")
def get_databases() -> list[dict]:
    """Every non-template database with owner, encoding, and size."""
    with server_db() as conn:
        return list_databases(conn)


@router.post("", status_code=201)
def create_database(body: CreateDatabaseBody) -> dict:
    """Create a database."""
    name = sqlbuild.validate_identifier(body.name, "database name")
    owner = body.owner.strip() if body.owner and body.owner.strip() else None
    encoding = body.encoding.strip() if body.encoding and body.encoding.strip() else None
    stmt = sqlbuild.create_database(name, owner, encoding)
    with server_db() as conn:
        try:
            conn.execute(stmt)
        except pgerrors.DuplicateDatabase as exc:
            raise HTTPException(409, f"database '{name}' already exists") from exc
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"created": name}


@router.delete("/{name}")
def drop_database(name: str, force: bool = False) -> dict:
    """Drop a database. `force` terminates active connections first."""
    name = sqlbuild.validate_identifier(name, "database name")
    stmt = sqlbuild.drop_database(name, force)
    with server_db() as conn:
        try:
            conn.execute(stmt)
        except pgerrors.InvalidCatalogName as exc:
            raise HTTPException(404, f"no database named '{name}'") from exc
        except pgerrors.ObjectInUse as exc:
            raise HTTPException(
                409, f"database '{name}' has active connections — retry with force"
            ) from exc
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"dropped": name}
```

- [ ] **Step 9: Register the router in `src/dbmanager/webapp.py`**

Replace the line `# ROUTER REGISTRATION MARKER — do not remove` with:

```python
# ROUTER REGISTRATION MARKER — do not remove
from fastapi import Depends
from dbmanager.auth import require_session
from dbmanager.routes import databases

app.include_router(databases.router, dependencies=[Depends(require_session)])
```

- [ ] **Step 10: Run test to verify it passes**

Run: `pytest tests/test_databases.py -v`
Expected: PASS (4 tests)

- [ ] **Step 11: Commit**

```bash
git add src/dbmanager/inspect.py src/dbmanager/sqlbuild.py src/dbmanager/routes/databases.py src/dbmanager/webapp.py tests/test_sqlbuild.py tests/test_databases.py
git commit -m "feat: database list/create/drop"
```

---

## Task 9: Sidebar tree + database overview

**Files:**
- Create: `src/dbmanager/web/databases.js`
- Modify: `src/dbmanager/web/app.js`

- [ ] **Step 1: Create `src/dbmanager/web/databases.js`**

```js
import { get, post, del } from "./api.js";
import { confirmModal, formModal, fmtBytes, showError } from "./app.js";

// Render the database overview panel.
export async function renderDatabaseOverview(dbName) {
  const panel = document.getElementById("panel");
  const databases = await get("/api/databases");
  const db = databases.find((d) => d.name === dbName);
  const tables = await get(`/api/databases/${encodeURIComponent(dbName)}/tables`);
  panel.innerHTML = "";

  const h = document.createElement("h2");
  h.textContent = dbName;
  panel.append(h);

  const meta = document.createElement("p");
  meta.className = "notice";
  meta.textContent = db
    ? `owner ${db.owner} · ${db.encoding} · ${fmtBytes(db.size_bytes)} · ${tables.length} table(s)`
    : `${tables.length} table(s)`;
  panel.append(meta);

  const grid = document.createElement("table");
  grid.className = "grid";
  grid.innerHTML =
    "<thead><tr><th>Table</th><th>Approx rows</th><th>Size</th></tr></thead>";
  const body = document.createElement("tbody");
  for (const t of tables) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${t.name}</td><td>${t.approx_rows}</td><td>${fmtBytes(t.size_bytes)}</td>`;
    body.append(tr);
  }
  grid.append(body);
  panel.append(grid);
}

// "New database" dialog.
export async function newDatabaseDialog(reload) {
  const values = await formModal("Create database", [
    { name: "name", label: "Name", type: "text" },
    { name: "owner", label: "Owner (optional)", type: "text" },
  ]);
  if (!values) return;
  try {
    await post("/api/databases", { name: values.name, owner: values.owner || null });
    await reload();
  } catch (err) { showError(err.message); }
}

// Drop-database confirmation.
export async function dropDatabaseDialog(name, reload) {
  const ok = await confirmModal(
    `Drop database "${name}"`,
    `This permanently deletes the database and all its data. Type the name to confirm.`,
    name);
  if (!ok) return;
  try {
    await del(`/api/databases/${encodeURIComponent(name)}?force=true`);
    await reload();
  } catch (err) { showError(err.message); }
}
```

- [ ] **Step 2: Replace `src/dbmanager/web/app.js`**

This is the full app.js — shared UI helpers (`fmtBytes`, `showError`, `confirmModal`, `formModal`), the sidebar tree, and panel routing. `renderTableView` is imported from `tables.js` (Task 12) — until then a table click shows a placeholder; replace the stub import in Task 12.

```js
import { get, post } from "./api.js";
import { renderDatabaseOverview, newDatabaseDialog, dropDatabaseDialog }
  from "./databases.js";

const loginEl = document.getElementById("login");
const appEl = document.getElementById("app");
let selected = null;  // { db } or { db, table }

// --- shared helpers ---------------------------------------------------------

export function fmtBytes(n) {
  if (n == null) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = Number(n);
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(i ? 1 : 0)} ${u[i]}`;
}

export function showError(msg) { alert(msg); }

function modalShell() {
  const bg = document.createElement("div");
  bg.className = "modal-bg";
  const box = document.createElement("div");
  box.className = "modal";
  bg.append(box);
  document.body.append(bg);
  return { bg, box };
}

// Typed-confirmation modal. Resolves true only if the user types `phrase`.
export function confirmModal(title, message, phrase) {
  return new Promise((resolve) => {
    const { bg, box } = modalShell();
    box.innerHTML = `<h2>${title}</h2><p>${message}</p>`;
    const input = document.createElement("input");
    input.placeholder = phrase;
    const actions = document.createElement("div");
    actions.className = "row";
    const cancel = document.createElement("button");
    cancel.className = "ghost"; cancel.textContent = "Cancel";
    const ok = document.createElement("button");
    ok.className = "danger"; ok.textContent = "Confirm"; ok.disabled = true;
    input.addEventListener("input", () => { ok.disabled = input.value !== phrase; });
    cancel.onclick = () => { bg.remove(); resolve(false); };
    ok.onclick = () => { bg.remove(); resolve(true); };
    actions.append(cancel, ok);
    box.append(input, actions);
    input.focus();
  });
}

// Generic form modal. `fields` = [{name,label,type,options?}]. Resolves an
// object of values, or null if cancelled.
export function formModal(title, fields) {
  return new Promise((resolve) => {
    const { bg, box } = modalShell();
    box.innerHTML = `<h2>${title}</h2>`;
    const inputs = {};
    for (const f of fields) {
      const row = document.createElement("div");
      row.className = "row";
      const label = document.createElement("label");
      label.textContent = f.label;
      let el;
      if (f.type === "select") {
        el = document.createElement("select");
        for (const o of f.options) {
          const opt = document.createElement("option");
          opt.value = o; opt.textContent = o;
          el.append(opt);
        }
      } else if (f.type === "checkbox") {
        el = document.createElement("input");
        el.type = "checkbox";
      } else {
        el = document.createElement("input");
        el.type = f.type || "text";
      }
      inputs[f.name] = el;
      row.append(label, el);
      box.append(row);
    }
    const actions = document.createElement("div");
    actions.className = "row";
    const cancel = document.createElement("button");
    cancel.className = "ghost"; cancel.textContent = "Cancel";
    const ok = document.createElement("button");
    ok.textContent = "Save";
    cancel.onclick = () => { bg.remove(); resolve(null); };
    ok.onclick = () => {
      const out = {};
      for (const f of fields) {
        out[f.name] = f.type === "checkbox"
          ? inputs[f.name].checked : inputs[f.name].value.trim();
      }
      bg.remove(); resolve(out);
    };
    actions.append(cancel, ok);
    box.append(actions);
  });
}

// --- sidebar ----------------------------------------------------------------

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
    sidebar.append(dbEl);

    let tables;
    try {
      tables = await get(`/api/databases/${encodeURIComponent(db.name)}/tables`);
    } catch { tables = []; }
    for (const t of tables) {
      const tEl = document.createElement("div");
      tEl.className = "tree-item tree-table";
      tEl.textContent = t.name;
      tEl.onclick = () => selectTable(db.name, t.name);
      sidebar.append(tEl);
    }
  }
}

async function selectDatabase(db) {
  selected = { db };
  await renderDatabaseOverview(db);
}

async function selectTable(db, table) {
  selected = { db, table };
  await renderTableView(db, table);  // from tables.js (Task 12)
}

function openConsole() {
  renderConsole(selected?.db);  // from query.js (Task 14)
}

// Placeholders replaced in later phases.
async function renderTableView(db, table) {
  document.getElementById("panel").textContent = `${db}.${table}`;
}
function renderConsole(db) {
  document.getElementById("panel").textContent = "SQL Console";
}

// --- auth / boot ------------------------------------------------------------

async function showApp() {
  loginEl.classList.add("hidden");
  appEl.classList.remove("hidden");
  await loadSidebar();
}
function showLogin() {
  appEl.classList.add("hidden");
  loginEl.classList.remove("hidden");
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("login-error");
  errEl.textContent = "";
  try {
    await post("/api/login", {
      password: document.getElementById("login-password").value,
    });
    await showApp();
  } catch (err) { errEl.textContent = err.message; }
});

document.getElementById("logout").addEventListener("click", async () => {
  await post("/api/logout");
  showLogin();
});

(async function init() {
  try { await get("/api/databases"); await showApp(); }
  catch { showLogin(); }
})();
```

- [ ] **Step 3: Verify in the browser**

Run: `dbmanager web`, log in.
Expected: the sidebar lists databases; "+ New database" creates one (it appears in the tree); right-clicking a database opens the typed-confirm drop dialog; clicking a database shows its overview with a table list.

- [ ] **Step 4: Commit**

```bash
git add src/dbmanager/web/databases.js src/dbmanager/web/app.js
git commit -m "feat: sidebar tree and database overview UI"
```

---

# Phase 3 — Tables & DDL

## Task 10: Table DDL builders

**Files:**
- Modify: `src/dbmanager/sqlbuild.py`
- Test: `tests/test_sqlbuild.py`

- [ ] **Step 1: Add failing tests to `tests/test_sqlbuild.py`**

```python
def test_create_table_sql():
    cols = [
        {"name": "id", "type": "integer", "nullable": False,
         "default": None, "primary_key": True},
        {"name": "label", "type": "text", "nullable": True,
         "default": None, "primary_key": False},
    ]
    rendered = sqlbuild.create_table("items", cols).as_string()
    assert rendered == (
        'CREATE TABLE "public"."items" ('
        '"id" integer NOT NULL, "label" text, PRIMARY KEY ("id"))'
    )


def test_add_column_sql():
    col = {"name": "qty", "type": "integer", "nullable": False, "default": "0"}
    rendered = sqlbuild.add_column("items", col).as_string()
    assert rendered == (
        'ALTER TABLE "public"."items" '
        'ADD COLUMN "qty" integer NOT NULL DEFAULT 0'
    )


def test_drop_table_sql():
    assert sqlbuild.drop_table("items").as_string() == 'DROP TABLE "public"."items"'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sqlbuild.py -v`
Expected: FAIL — `AttributeError: module 'dbmanager.sqlbuild' has no attribute 'create_table'`

- [ ] **Step 3: Add the builders to `src/dbmanager/sqlbuild.py`**

Append these functions (keep existing ones). They reuse `validate_type`/`validate_default` and `qualified`.

```python
def _column_clause(col: dict) -> pgsql.Composable:
    """Render one column definition: "name" TYPE [NOT NULL] [DEFAULT expr]."""
    parts = [pgsql.SQL("{} ").format(pgsql.Identifier(col["name"])),
             pgsql.SQL(validate_type(col["type"]))]
    if not col.get("nullable", True):
        parts.append(pgsql.SQL(" NOT NULL"))
    default = col.get("default")
    if default not in (None, ""):
        parts.append(pgsql.SQL(" DEFAULT ") + pgsql.SQL(validate_default(default)))
    return pgsql.Composed(parts)


def create_table(name: str, columns: list[dict]) -> pgsql.Composable:
    """CREATE TABLE with an inline PRIMARY KEY for any primary-key columns."""
    if not columns:
        raise HTTPException(400, "a table needs at least one column")
    defs = [_column_clause(c) for c in columns]
    pk = [c["name"] for c in columns if c.get("primary_key")]
    if pk:
        defs.append(pgsql.SQL("PRIMARY KEY ({})").format(
            pgsql.SQL(", ").join(pgsql.Identifier(c) for c in pk)))
    return pgsql.SQL("CREATE TABLE {} ({})").format(
        qualified(name), pgsql.SQL(", ").join(defs))


def drop_table(name: str) -> pgsql.Composable:
    return pgsql.SQL("DROP TABLE {}").format(qualified(name))


def rename_table(name: str, new_name: str) -> pgsql.Composable:
    return pgsql.SQL("ALTER TABLE {} RENAME TO {}").format(
        qualified(name), pgsql.Identifier(new_name))


def add_column(table: str, col: dict) -> pgsql.Composable:
    return pgsql.SQL("ALTER TABLE {} ADD COLUMN {}").format(
        qualified(table), _column_clause(col))


def drop_column(table: str, column: str) -> pgsql.Composable:
    return pgsql.SQL("ALTER TABLE {} DROP COLUMN {}").format(
        qualified(table), pgsql.Identifier(column))


def alter_column(table: str, column: str, change: dict) -> list[pgsql.Composable]:
    """One ALTER COLUMN statement per requested change (applied in one txn)."""
    stmts: list[pgsql.Composable] = []
    base = pgsql.SQL("ALTER TABLE {} ").format(qualified(table))
    col = pgsql.Identifier(column)
    if change.get("type"):
        stmts.append(base + pgsql.SQL("ALTER COLUMN {} TYPE {}").format(
            col, pgsql.SQL(validate_type(change["type"]))))
    if change.get("nullable") is True:
        stmts.append(base + pgsql.SQL("ALTER COLUMN {} DROP NOT NULL").format(col))
    if change.get("nullable") is False:
        stmts.append(base + pgsql.SQL("ALTER COLUMN {} SET NOT NULL").format(col))
    if change.get("drop_default"):
        stmts.append(base + pgsql.SQL("ALTER COLUMN {} DROP DEFAULT").format(col))
    elif change.get("default") not in (None, ""):
        stmts.append(base + pgsql.SQL("ALTER COLUMN {} SET DEFAULT ").format(col)
                     + pgsql.SQL(validate_default(change["default"])))
    if change.get("new_name"):
        stmts.append(base + pgsql.SQL("RENAME COLUMN {} TO {}").format(
            col, pgsql.Identifier(change["new_name"])))
    return stmts


def add_constraint(table: str, body: dict) -> pgsql.Composable:
    """ADD CONSTRAINT for PRIMARY KEY, UNIQUE, or FOREIGN KEY."""
    ctype = body["type"]
    cols = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in body["columns"])
    head = pgsql.SQL("ALTER TABLE {} ADD ").format(qualified(table))
    if body.get("name"):
        head = head + pgsql.SQL("CONSTRAINT {} ").format(
            pgsql.Identifier(body["name"]))
    if ctype == "PRIMARY KEY":
        return head + pgsql.SQL("PRIMARY KEY ({})").format(cols)
    if ctype == "UNIQUE":
        return head + pgsql.SQL("UNIQUE ({})").format(cols)
    if ctype == "FOREIGN KEY":
        ref_cols = pgsql.SQL(", ").join(
            pgsql.Identifier(c) for c in body["ref_columns"])
        return head + pgsql.SQL("FOREIGN KEY ({}) REFERENCES {} ({})").format(
            cols, qualified(body["ref_table"]), ref_cols)
    raise HTTPException(400, f"unsupported constraint type: {ctype}")


def drop_constraint(table: str, name: str) -> pgsql.Composable:
    return pgsql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
        qualified(table), pgsql.Identifier(name))


def create_index(table: str, name: str, columns: list[str],
                 unique: bool) -> pgsql.Composable:
    kw = pgsql.SQL("CREATE UNIQUE INDEX" if unique else "CREATE INDEX")
    cols = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in columns)
    return pgsql.SQL("{} {} ON {} ({})").format(
        kw, pgsql.Identifier(name), qualified(table), cols)


def drop_index(name: str) -> pgsql.Composable:
    return pgsql.SQL("DROP INDEX {}").format(pgsql.Identifier(name))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sqlbuild.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dbmanager/sqlbuild.py tests/test_sqlbuild.py
git commit -m "feat: table and DDL sql builders"
```

---

## Task 11: Table routes

**Files:**
- Create: `src/dbmanager/routes/tables.py`
- Modify: `src/dbmanager/webapp.py`
- Test: `tests/test_tables.py`

- [ ] **Step 1: Write the failing test**

```python
import uuid
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(server_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", server_url)
    from dbmanager.webapp import app
    c = TestClient(app)
    c.post("/api/login", json={"password": "test-password"})
    return c


@pytest.fixture
def db(client):
    """A fresh database, dropped after the test."""
    name = f"dbm_t_{uuid.uuid4().hex[:8]}"
    client.post("/api/databases", json={"name": name})
    yield name
    client.delete(f"/api/databases/{name}?force=true")


def test_create_inspect_drop_table(client, db):
    create = client.post(f"/api/databases/{db}/tables", json={
        "name": "items",
        "columns": [
            {"name": "id", "type": "integer", "nullable": False,
             "primary_key": True},
            {"name": "label", "type": "text"},
        ],
    })
    assert create.status_code == 201

    listed = client.get(f"/api/databases/{db}/tables").json()
    assert "items" in [t["name"] for t in listed]

    struct = client.get(f"/api/databases/{db}/tables/items").json()
    assert struct["primary_key"] == ["id"]
    assert {c["name"] for c in struct["columns"]} == {"id", "label"}

    dropped = client.delete(f"/api/databases/{db}/tables/items")
    assert dropped.status_code == 200


def test_add_and_drop_column(client, db):
    client.post(f"/api/databases/{db}/tables", json={
        "name": "t", "columns": [{"name": "id", "type": "integer"}]})
    add = client.post(f"/api/databases/{db}/tables/t/columns",
                      json={"name": "note", "type": "text"})
    assert add.status_code == 201
    struct = client.get(f"/api/databases/{db}/tables/t").json()
    assert "note" in [c["name"] for c in struct["columns"]]
    drop = client.delete(f"/api/databases/{db}/tables/t/columns/note")
    assert drop.status_code == 200


def test_inspect_missing_table_404(client, db):
    resp = client.get(f"/api/databases/{db}/tables/nope")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tables.py -v`
Expected: FAIL — 404 on `/api/databases/{db}/tables` (router not registered)

- [ ] **Step 3: Write `src/dbmanager/routes/tables.py`**

```python
"""Table list/inspect/create/rename/drop and column/constraint/index DDL."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager import sqlbuild
from dbmanager.deps import target_db
from dbmanager.inspect import list_tables, table_structure

router = APIRouter(prefix="/api/databases/{db}/tables", tags=["tables"])


class ColumnDef(BaseModel):
    name: str
    type: str
    nullable: bool = True
    default: str | None = None
    primary_key: bool = False


class CreateTableBody(BaseModel):
    name: str
    columns: list[ColumnDef]


class RenameTableBody(BaseModel):
    new_name: str


class AlterColumnBody(BaseModel):
    new_name: str | None = None
    type: str | None = None
    nullable: bool | None = None
    default: str | None = None
    drop_default: bool = False


class ConstraintBody(BaseModel):
    type: str
    columns: list[str]
    name: str | None = None
    ref_table: str | None = None
    ref_columns: list[str] | None = None


class IndexBody(BaseModel):
    name: str
    columns: list[str]
    unique: bool = False


def _run(db: str, stmts):
    """Execute one statement or a list of them in a single transaction,
    mapping Postgres errors to HTTP status codes."""
    if not isinstance(stmts, (list, tuple)):
        stmts = [stmts]
    with target_db(db) as conn:
        try:
            for stmt in stmts:
                conn.execute(stmt)
        except pgerrors.DuplicateTable as exc:
            raise HTTPException(409, str(exc)) from exc
        except pgerrors.DuplicateColumn as exc:
            raise HTTPException(409, str(exc)) from exc
        except pgerrors.UndefinedTable as exc:
            raise HTTPException(404, str(exc)) from exc
        except pgerrors.UndefinedColumn as exc:
            raise HTTPException(404, str(exc)) from exc
        except pgerrors.UndefinedObject as exc:
            raise HTTPException(404, str(exc)) from exc
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("")
def get_tables(db: str) -> list[dict]:
    with target_db(db) as conn:
        return list_tables(conn)


@router.get("/{table}")
def get_table(db: str, table: str) -> dict:
    with target_db(db) as conn:
        struct = table_structure(conn, table)
    if not struct:
        raise HTTPException(404, f"no table '{table}' in database '{db}'")
    return struct


@router.post("", status_code=201)
def create_table(db: str, body: CreateTableBody) -> dict:
    name = sqlbuild.validate_identifier(body.name, "table name")
    _run(db, sqlbuild.create_table(name, [c.model_dump() for c in body.columns]))
    return {"created": name}


@router.patch("/{table}")
def rename_table(db: str, table: str, body: RenameTableBody) -> dict:
    new_name = sqlbuild.validate_identifier(body.new_name, "new table name")
    _run(db, sqlbuild.rename_table(table, new_name))
    return {"renamed": new_name}


@router.delete("/{table}")
def drop_table(db: str, table: str) -> dict:
    _run(db, sqlbuild.drop_table(table))
    return {"dropped": table}


@router.post("/{table}/columns", status_code=201)
def add_column(db: str, table: str, body: ColumnDef) -> dict:
    sqlbuild.validate_identifier(body.name, "column name")
    _run(db, sqlbuild.add_column(table, body.model_dump()))
    return {"added": body.name}


@router.patch("/{table}/columns/{column}")
def alter_column(db: str, table: str, column: str, body: AlterColumnBody) -> dict:
    stmts = sqlbuild.alter_column(table, column, body.model_dump())
    if not stmts:
        raise HTTPException(400, "no changes requested")
    _run(db, stmts)
    return {"altered": column}


@router.delete("/{table}/columns/{column}")
def drop_column(db: str, table: str, column: str) -> dict:
    _run(db, sqlbuild.drop_column(table, column))
    return {"dropped": column}


@router.post("/{table}/constraints", status_code=201)
def add_constraint(db: str, table: str, body: ConstraintBody) -> dict:
    _run(db, sqlbuild.add_constraint(table, body.model_dump()))
    return {"added": body.name or body.type}


@router.delete("/{table}/constraints/{name}")
def drop_constraint(db: str, table: str, name: str) -> dict:
    _run(db, sqlbuild.drop_constraint(table, name))
    return {"dropped": name}


@router.post("/{table}/indexes", status_code=201)
def create_index(db: str, table: str, body: IndexBody) -> dict:
    sqlbuild.validate_identifier(body.name, "index name")
    _run(db, sqlbuild.create_index(table, body.name, body.columns, body.unique))
    return {"created": body.name}


@router.delete("/{table}/indexes/{name}")
def drop_index(db: str, table: str, name: str) -> dict:
    _run(db, sqlbuild.drop_index(name))
    return {"dropped": name}
```

- [ ] **Step 4: Register the router in `src/dbmanager/webapp.py`**

After the existing `app.include_router(databases.router, ...)` line, add:

```python
from dbmanager.routes import tables

app.include_router(tables.router, dependencies=[Depends(require_session)])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_tables.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/routes/tables.py src/dbmanager/webapp.py tests/test_tables.py
git commit -m "feat: table and DDL routes"
```

---

## Task 12: Table view — Structure tab

**Files:**
- Create: `src/dbmanager/web/tables.js`
- Modify: `src/dbmanager/web/app.js`

- [ ] **Step 1: Create `src/dbmanager/web/tables.js`**

```js
import { get, post, patch, del } from "./api.js";
import { confirmModal, formModal, showError } from "./app.js";

let current = { db: null, table: null, tab: "data" };

// Entry point called by the sidebar. `refresh` reloads the sidebar tree.
export async function renderTableView(db, table, refresh) {
  current = { db, table, tab: current.tab || "data" };
  const panel = document.getElementById("panel");
  panel.innerHTML = "";

  const h = document.createElement("h2");
  h.textContent = `${db} · ${table}`;
  panel.append(h);

  const tabs = document.createElement("div");
  tabs.className = "tabs";
  for (const name of ["data", "structure"]) {
    const b = document.createElement("button");
    b.textContent = name[0].toUpperCase() + name.slice(1);
    if (current.tab === name) b.classList.add("active");
    b.onclick = () => { current.tab = name; renderTableView(db, table, refresh); };
    tabs.append(b);
  }
  panel.append(tabs);

  const content = document.createElement("div");
  panel.append(content);
  if (current.tab === "structure") await renderStructure(content, db, table, refresh);
  else await renderDataTab(content, db, table);
}

// renderDataTab is provided by rows.js (Task 13). Bound at load time.
let renderDataTab = async (el) => { el.textContent = "Data tab — Phase 4."; };
export function bindDataTab(fn) { renderDataTab = fn; }

async function renderStructure(el, db, table, refresh) {
  const base = `/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(table)}`;
  const struct = await get(base);

  const toolbar = document.createElement("div");
  toolbar.className = "toolbar";
  const addCol = mkBtn("+ Column", () => addColumnDialog(db, table, refresh));
  const addIdx = mkBtn("+ Index", () =>
    addIndexDialog(db, table, struct.columns.map((c) => c.name), refresh));
  const addFk = mkBtn("+ Constraint", () =>
    addConstraintDialog(db, table, struct.columns.map((c) => c.name), refresh));
  const dropTbl = mkBtn("Drop table", async () => {
    if (await confirmModal(`Drop table "${table}"`,
        "This permanently deletes the table and its data.", table)) {
      await del(base); await refresh();
    }
  }, "danger");
  toolbar.append(addCol, addIdx, addFk, dropTbl);
  el.append(toolbar);

  el.append(mkSection("Columns", ["Name", "Type", "Nullable", "Default", ""],
    struct.columns.map((c) => [
      c.name, c.data_type, c.is_nullable, c.column_default ?? "",
      rowActions([
        ["Edit", () => editColumnDialog(db, table, c, refresh)],
        ["Drop", async () => {
          if (await confirmModal(`Drop column "${c.name}"`,
              "This permanently deletes the column and its data.", c.name)) {
            await del(`${base}/columns/${encodeURIComponent(c.name)}`);
            await renderTableView(db, table, refresh);
          }
        }],
      ]),
    ])));

  el.append(mkSection("Constraints", ["Name", "Type", "Definition", ""],
    struct.constraints.map((c) => [
      c.name, c.type, c.definition,
      rowActions([["Drop", async () => {
        await del(`${base}/constraints/${encodeURIComponent(c.name)}`);
        await renderTableView(db, table, refresh);
      }]]),
    ])));

  el.append(mkSection("Indexes", ["Name", "Definition", ""],
    struct.indexes.map((i) => [
      i.name, i.definition,
      rowActions([["Drop", async () => {
        await del(`${base}/indexes/${encodeURIComponent(i.name)}`);
        await renderTableView(db, table, refresh);
      }]]),
    ])));
}

// --- dialogs ----------------------------------------------------------------

async function addColumnDialog(db, table, refresh) {
  const v = await formModal("Add column", [
    { name: "name", label: "Name", type: "text" },
    { name: "type", label: "Type", type: "text" },
    { name: "nullable", label: "Nullable", type: "checkbox" },
    { name: "default", label: "Default", type: "text" },
  ]);
  if (!v) return;
  try {
    await post(`/api/databases/${db}/tables/${table}/columns`, {
      name: v.name, type: v.type, nullable: v.nullable,
      default: v.default || null,
    });
    await renderTableView(db, table, refresh); await refresh();
  } catch (e) { showError(e.message); }
}

async function editColumnDialog(db, table, col, refresh) {
  const v = await formModal(`Edit column "${col.name}"`, [
    { name: "new_name", label: "Rename to", type: "text" },
    { name: "type", label: "New type", type: "text" },
  ]);
  if (!v) return;
  try {
    await patch(
      `/api/databases/${db}/tables/${table}/columns/${encodeURIComponent(col.name)}`,
      { new_name: v.new_name || null, type: v.type || null });
    await renderTableView(db, table, refresh); await refresh();
  } catch (e) { showError(e.message); }
}

async function addIndexDialog(db, table, columns, refresh) {
  const v = await formModal("Create index", [
    { name: "name", label: "Index name", type: "text" },
    { name: "column", label: "Column", type: "select", options: columns },
    { name: "unique", label: "Unique", type: "checkbox" },
  ]);
  if (!v) return;
  try {
    await post(`/api/databases/${db}/tables/${table}/indexes`,
      { name: v.name, columns: [v.column], unique: v.unique });
    await renderTableView(db, table, refresh);
  } catch (e) { showError(e.message); }
}

async function addConstraintDialog(db, table, columns, refresh) {
  const v = await formModal("Add constraint", [
    { name: "type", label: "Type", type: "select",
      options: ["UNIQUE", "PRIMARY KEY"] },
    { name: "column", label: "Column", type: "select", options: columns },
    { name: "name", label: "Name (optional)", type: "text" },
  ]);
  if (!v) return;
  try {
    await post(`/api/databases/${db}/tables/${table}/constraints`,
      { type: v.type, columns: [v.column], name: v.name || null });
    await renderTableView(db, table, refresh);
  } catch (e) { showError(e.message); }
}

// --- small DOM helpers ------------------------------------------------------

function mkBtn(text, onClick, cls) {
  const b = document.createElement("button");
  b.textContent = text;
  if (cls) b.className = cls;
  b.onclick = onClick;
  return b;
}

function rowActions(actions) {
  const span = document.createElement("span");
  for (const [label, fn] of actions) {
    const b = mkBtn(label, fn, "ghost");
    b.style.marginRight = "4px";
    span.append(b);
  }
  return span;
}

function mkSection(title, headers, rows) {
  const wrap = document.createElement("div");
  const h = document.createElement("h3");
  h.textContent = title;
  wrap.append(h);
  const table = document.createElement("table");
  table.className = "grid";
  table.innerHTML =
    `<thead><tr>${headers.map((x) => `<th>${x}</th>`).join("")}</tr></thead>`;
  const body = document.createElement("tbody");
  for (const cells of rows) {
    const tr = document.createElement("tr");
    for (const c of cells) {
      const td = document.createElement("td");
      if (c instanceof Node) td.append(c);
      else td.textContent = c;
      tr.append(td);
    }
    body.append(tr);
  }
  table.append(body);
  wrap.append(table);
  return wrap;
}

// Used by the create-table flow from the sidebar.
export async function newTableDialog(db, refresh) {
  const v = await formModal(`New table in "${db}"`, [
    { name: "name", label: "Table name", type: "text" },
    { name: "col", label: "First column", type: "text" },
    { name: "type", label: "Column type", type: "text" },
  ]);
  if (!v) return;
  try {
    await post(`/api/databases/${db}/tables`, {
      name: v.name,
      columns: [{ name: v.col, type: v.type, primary_key: true,
                  nullable: false }],
    });
    await refresh();
  } catch (e) { showError(e.message); }
}
```

- [ ] **Step 2: Wire `tables.js` into `app.js`**

In `src/dbmanager/web/app.js`, replace the placeholder `renderTableView` stub and add the import. Change the import block at the top to add:

```js
import { renderTableView as tableView, newTableDialog } from "./tables.js";
```

Replace the placeholder function:

```js
async function renderTableView(db, table) {
  document.getElementById("panel").textContent = `${db}.${table}`;
}
```

with:

```js
async function renderTableView(db, table) {
  await tableView(db, table, loadSidebar);
}
```

Then, inside `loadSidebar`, after the `dbEl` is appended and before the tables loop, add a per-database "new table" affordance:

```js
    dbEl.ondblclick = () => newTableDialog(db.name, loadSidebar);
```

- [ ] **Step 3: Verify in the browser**

Run: `dbmanager web`, log in.
Expected: double-clicking a database opens "New table"; creating it adds the table to the tree; clicking the table shows Data/Structure tabs; the Structure tab lists columns, constraints, and indexes and its toolbar adds a column/index/constraint and drops the table (with typed confirmation).

- [ ] **Step 4: Commit**

```bash
git add src/dbmanager/web/tables.js src/dbmanager/web/app.js
git commit -m "feat: table structure tab and DDL UI"
```

---

# Phase 4 — Row CRUD

## Task 13: Row routes

**Files:**
- Create: `src/dbmanager/routes/rows.py`
- Modify: `src/dbmanager/webapp.py`
- Test: `tests/test_rows.py`

- [ ] **Step 1: Write the failing test**

```python
import uuid
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(server_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", server_url)
    from dbmanager.webapp import app
    c = TestClient(app)
    c.post("/api/login", json={"password": "test-password"})
    return c


@pytest.fixture
def db(client):
    name = f"dbm_r_{uuid.uuid4().hex[:8]}"
    client.post("/api/databases", json={"name": name})
    client.post(f"/api/databases/{name}/tables", json={
        "name": "people",
        "columns": [
            {"name": "id", "type": "integer", "nullable": False,
             "primary_key": True},
            {"name": "name", "type": "text"},
        ],
    })
    yield name
    client.delete(f"/api/databases/{name}?force=true")


def test_insert_list_update_delete_row(client, db):
    base = f"/api/databases/{db}/tables/people/rows"

    ins = client.post(base, json={"values": {"id": 1, "name": "Ada"}})
    assert ins.status_code == 201

    listed = client.get(base).json()
    assert listed["total"] == 1
    assert listed["primary_key"] == ["id"]
    assert listed["editable"] is True
    assert listed["rows"][0]["name"] == "Ada"

    upd = client.patch(base, json={"pk": {"id": 1}, "values": {"name": "Grace"}})
    assert upd.status_code == 200
    assert client.get(base).json()["rows"][0]["name"] == "Grace"

    dele = client.request("DELETE", base, json={"pk": {"id": 1}})
    assert dele.status_code == 200
    assert client.get(base).json()["total"] == 0


def test_grid_not_editable_without_primary_key(client, db):
    client.post(f"/api/databases/{db}/tables", json={
        "name": "logs", "columns": [{"name": "msg", "type": "text"}]})
    listed = client.get(f"/api/databases/{db}/tables/logs/rows").json()
    assert listed["editable"] is False


def test_filter_rows(client, db):
    base = f"/api/databases/{db}/tables/people/rows"
    client.post(base, json={"values": {"id": 1, "name": "Ada"}})
    client.post(base, json={"values": {"id": 2, "name": "Bob"}})
    filtered = client.get(f"{base}?filter_column=name&filter_value=Ada").json()
    assert filtered["total"] == 1
    assert filtered["rows"][0]["name"] == "Ada"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rows.py -v`
Expected: FAIL — 404 on the rows endpoint (router not registered)

- [ ] **Step 3: Write `src/dbmanager/routes/rows.py`**

```python
"""Paginated row browsing and row insert/update/delete.

Rows are identified for update/delete by their primary-key columns. A table
with no primary key is returned as a read-only grid (editable=false).
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from psycopg import errors as pgerrors, sql as pgsql
from pydantic import BaseModel

from dbmanager.deps import target_db
from dbmanager.inspect import table_structure
from dbmanager.sqlbuild import qualified

router = APIRouter(prefix="/api/databases/{db}/tables/{table}/rows", tags=["rows"])


class InsertBody(BaseModel):
    values: dict


class UpdateBody(BaseModel):
    pk: dict
    values: dict


class DeleteBody(BaseModel):
    pk: dict


def _structure_or_404(conn, db: str, table: str) -> dict:
    struct = table_structure(conn, table)
    if not struct:
        raise HTTPException(404, f"no table '{table}' in database '{db}'")
    return struct


@router.get("")
def list_rows(db: str, table: str, page: int = 1, page_size: int = 50,
              filter_column: str | None = None,
              filter_value: str | None = None) -> dict:
    """A page of rows, plus total count and primary-key metadata."""
    page = max(page, 1)
    page_size = min(max(page_size, 1), 500)
    with target_db(db) as conn:
        struct = _structure_or_404(conn, db, table)
        col_names = {c["name"] for c in struct["columns"]}
        pk = struct["primary_key"]

        where = pgsql.SQL("")
        params: list = []
        if filter_column and filter_value is not None:
            if filter_column not in col_names:
                raise HTTPException(400, f"unknown column: {filter_column}")
            where = pgsql.SQL(" WHERE CAST({} AS text) ILIKE {}").format(
                pgsql.Identifier(filter_column), pgsql.Placeholder())
            params.append(f"%{filter_value}%")

        total = conn.execute(
            pgsql.SQL("SELECT count(*) AS n FROM {}{}").format(
                qualified(table), where), params).fetchone()["n"]

        order = (pgsql.SQL(" ORDER BY {}").format(
                    pgsql.SQL(", ").join(pgsql.Identifier(c) for c in pk))
                 if pk else pgsql.SQL(""))
        rows = conn.execute(
            pgsql.SQL("SELECT * FROM {}{}{} LIMIT {} OFFSET {}").format(
                qualified(table), where, order,
                pgsql.Placeholder(), pgsql.Placeholder()),
            params + [page_size, (page - 1) * page_size]).fetchall()

    return {"columns": [c["name"] for c in struct["columns"]],
            "rows": rows, "total": total, "page": page, "page_size": page_size,
            "primary_key": pk, "editable": bool(pk)}


@router.post("", status_code=201)
def insert_row(db: str, table: str, body: InsertBody) -> dict:
    if not body.values:
        raise HTTPException(400, "no values supplied")
    cols = list(body.values)
    stmt = pgsql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
        qualified(table),
        pgsql.SQL(", ").join(pgsql.Identifier(c) for c in cols),
        pgsql.SQL(", ").join(pgsql.Placeholder() for _ in cols))
    with target_db(db) as conn:
        try:
            row = conn.execute(stmt, [body.values[c] for c in cols]).fetchone()
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"inserted": row}


@router.patch("")
def update_row(db: str, table: str, body: UpdateBody) -> dict:
    if not body.pk:
        raise HTTPException(400, "primary-key values are required to update a row")
    if not body.values:
        raise HTTPException(400, "no values supplied")
    vcols, pcols = list(body.values), list(body.pk)
    stmt = pgsql.SQL("UPDATE {} SET {} WHERE {} RETURNING *").format(
        qualified(table),
        pgsql.SQL(", ").join(
            pgsql.SQL("{} = {}").format(pgsql.Identifier(c), pgsql.Placeholder())
            for c in vcols),
        pgsql.SQL(" AND ").join(
            pgsql.SQL("{} = {}").format(pgsql.Identifier(c), pgsql.Placeholder())
            for c in pcols))
    params = [body.values[c] for c in vcols] + [body.pk[c] for c in pcols]
    with target_db(db) as conn:
        try:
            row = conn.execute(stmt, params).fetchone()
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    if row is None:
        raise HTTPException(404, "no row matched the supplied primary key")
    return {"updated": row}


@router.delete("")
def delete_row(db: str, table: str, body: DeleteBody) -> dict:
    if not body.pk:
        raise HTTPException(400, "primary-key values are required to delete a row")
    pcols = list(body.pk)
    stmt = pgsql.SQL("DELETE FROM {} WHERE {} RETURNING *").format(
        qualified(table),
        pgsql.SQL(" AND ").join(
            pgsql.SQL("{} = {}").format(pgsql.Identifier(c), pgsql.Placeholder())
            for c in pcols))
    with target_db(db) as conn:
        try:
            row = conn.execute(stmt, [body.pk[c] for c in pcols]).fetchone()
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    if row is None:
        raise HTTPException(404, "no row matched the supplied primary key")
    return {"deleted": row}
```

- [ ] **Step 4: Register the router in `src/dbmanager/webapp.py`**

After the `tables` router line, add:

```python
from dbmanager.routes import rows

app.include_router(rows.router, dependencies=[Depends(require_session)])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_rows.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/routes/rows.py src/dbmanager/webapp.py tests/test_rows.py
git commit -m "feat: row browsing and CRUD routes"
```

---

## Task 14: Data grid UI

**Files:**
- Create: `src/dbmanager/web/rows.js`
- Modify: `src/dbmanager/web/tables.js`

- [ ] **Step 1: Create `src/dbmanager/web/rows.js`**

```js
import { get, post, patch, del } from "./api.js";
import { confirmModal, formModal, showError } from "./app.js";

let state = { db: null, table: null, page: 1, filterCol: "", filterVal: "" };

// Bound into tables.js via bindDataTab(). Renders the Data tab.
export async function renderDataTab(el, db, table) {
  if (state.db !== db || state.table !== table) {
    state = { db, table, page: 1, filterCol: "", filterVal: "" };
  }
  await draw(el, db, table);
}

async function draw(el, db, table) {
  const base = `/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(table)}/rows`;
  const qs = new URLSearchParams({ page: state.page, page_size: 50 });
  if (state.filterCol && state.filterVal) {
    qs.set("filter_column", state.filterCol);
    qs.set("filter_value", state.filterVal);
  }
  const data = await get(`${base}?${qs}`);
  el.innerHTML = "";

  // toolbar
  const toolbar = document.createElement("div");
  toolbar.className = "toolbar";
  const addBtn = mkBtn("+ Row", () => addRowDialog(el, db, table, data.columns));
  addBtn.disabled = !data.editable;
  const filterCol = document.createElement("select");
  for (const c of ["", ...data.columns]) {
    const o = document.createElement("option");
    o.value = c; o.textContent = c || "(filter column)";
    filterCol.append(o);
  }
  filterCol.value = state.filterCol;
  const filterVal = document.createElement("input");
  filterVal.placeholder = "filter value";
  filterVal.value = state.filterVal;
  const applyBtn = mkBtn("Filter", () => {
    state.filterCol = filterCol.value;
    state.filterVal = filterVal.value;
    state.page = 1;
    draw(el, db, table);
  });
  toolbar.append(addBtn, filterCol, filterVal, applyBtn);
  el.append(toolbar);

  if (!data.editable) {
    const note = document.createElement("p");
    note.className = "notice";
    note.textContent =
      "This table has no primary key — rows are read-only. Add a primary key, or use the SQL Console.";
    el.append(note);
  }

  // grid
  const table_ = document.createElement("table");
  table_.className = "grid";
  const headCells = data.columns.map((c) => `<th>${c}</th>`).join("");
  table_.innerHTML =
    `<thead><tr>${headCells}${data.editable ? "<th></th>" : ""}</tr></thead>`;
  const body = document.createElement("tbody");
  for (const row of data.rows) {
    const tr = document.createElement("tr");
    for (const c of data.columns) {
      const td = document.createElement("td");
      td.textContent = row[c] === null ? "∅" : String(row[c]);
      tr.append(td);
    }
    if (data.editable) {
      const td = document.createElement("td");
      const pk = Object.fromEntries(data.primary_key.map((k) => [k, row[k]]));
      td.append(
        mkBtn("Edit", () => editRowDialog(el, db, table, data.columns, pk, row), "ghost"),
        mkBtn("Delete", async () => {
          if (await confirmModal("Delete row",
              "This permanently deletes the row.",
              "delete")) {
            try {
              await del(`${base}`, { pk });
              await draw(el, db, table);
            } catch (e) { showError(e.message); }
          }
        }, "ghost"));
      tr.append(td);
    }
    body.append(tr);
  }
  table_.append(body);
  el.append(table_);

  // pager
  const pager = document.createElement("div");
  pager.className = "toolbar";
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  const prev = mkBtn("‹ Prev", () => { state.page--; draw(el, db, table); }, "ghost");
  const next = mkBtn("Next ›", () => { state.page++; draw(el, db, table); }, "ghost");
  prev.disabled = state.page <= 1;
  next.disabled = state.page >= pages;
  const label = document.createElement("span");
  label.textContent = `Page ${data.page} of ${pages} · ${data.total} row(s)`;
  pager.append(prev, next, label);
  el.append(pager);
}

async function addRowDialog(el, db, table, columns) {
  const v = await formModal("Insert row",
    columns.map((c) => ({ name: c, label: c, type: "text" })));
  if (!v) return;
  const values = {};
  for (const c of columns) if (v[c] !== "") values[c] = v[c];
  try {
    await post(`/api/databases/${db}/tables/${table}/rows`, { values });
    await draw(el, db, table);
  } catch (e) { showError(e.message); }
}

async function editRowDialog(el, db, table, columns, pk, row) {
  const fields = columns.map((c) => ({ name: c, label: c, type: "text" }));
  const v = await formModal("Edit row", fields);
  if (!v) return;
  // Send only the columns whose value changed.
  const values = {};
  for (const c of columns) {
    const before = row[c] === null ? "" : String(row[c]);
    if (v[c] !== before) values[c] = v[c];
  }
  if (Object.keys(values).length === 0) return;
  try {
    await patch(`/api/databases/${db}/tables/${table}/rows`, { pk, values });
    await draw(el, db, table);
  } catch (e) { showError(e.message); }
}

function mkBtn(text, onClick, cls) {
  const b = document.createElement("button");
  b.textContent = text;
  if (cls) b.className = cls;
  b.onclick = onClick;
  return b;
}
```

- [ ] **Step 2: Bind the Data tab in `src/dbmanager/web/tables.js`**

At the top of `tables.js`, add to the imports:

```js
import { renderDataTab as dataTab } from "./rows.js";
```

Then replace these lines:

```js
// renderDataTab is provided by rows.js (Task 13). Bound at load time.
let renderDataTab = async (el) => { el.textContent = "Data tab — Phase 4."; };
export function bindDataTab(fn) { renderDataTab = fn; }
```

with:

```js
const renderDataTab = dataTab;
```

- [ ] **Step 3: Verify in the browser**

Run: `dbmanager web`, log in, open a table.
Expected: the Data tab shows a paginated grid; "+ Row" inserts; per-row Edit/Delete work (Delete asks for typed confirmation); the column filter narrows results; a table with no primary key shows the read-only note and a disabled "+ Row".

- [ ] **Step 4: Commit**

```bash
git add src/dbmanager/web/rows.js src/dbmanager/web/tables.js
git commit -m "feat: row data grid UI"
```

---

# Phase 5 — SQL Console

## Task 15: Query route

**Files:**
- Create: `src/dbmanager/routes/query.py`
- Modify: `src/dbmanager/webapp.py`
- Test: `tests/test_query.py`

- [ ] **Step 1: Write the failing test**

```python
import uuid
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(server_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", server_url)
    from dbmanager.webapp import app
    c = TestClient(app)
    c.post("/api/login", json={"password": "test-password"})
    return c


@pytest.fixture
def db(client):
    name = f"dbm_q_{uuid.uuid4().hex[:8]}"
    client.post("/api/databases", json={"name": name})
    yield name
    client.delete(f"/api/databases/{name}?force=true")


def test_query_select_returns_rows(client, db):
    resp = client.post(f"/api/databases/{db}/query",
                       json={"sql": "SELECT 1 AS one, 'x' AS letter"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["columns"] == ["one", "letter"]
    assert data["rows"][0] == {"one": 1, "letter": "x"}


def test_query_ddl_returns_message(client, db):
    resp = client.post(f"/api/databases/{db}/query",
                       json={"sql": "CREATE TABLE t (id int)"})
    assert resp.status_code == 200
    assert resp.json()["columns"] == []


def test_query_syntax_error_is_400(client, db):
    resp = client.post(f"/api/databases/{db}/query",
                       json={"sql": "SELCT bad"})
    assert resp.status_code == 400


def test_query_empty_is_400(client, db):
    resp = client.post(f"/api/databases/{db}/query", json={"sql": "   "})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_query.py -v`
Expected: FAIL — 404 on the query endpoint (router not registered)

- [ ] **Step 3: Write `src/dbmanager/routes/query.py`**

```python
"""SQL console — runs arbitrary SQL against a chosen database."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager.deps import target_db

router = APIRouter(prefix="/api/databases/{db}/query", tags=["query"])


class QueryBody(BaseModel):
    sql: str


@router.post("")
def run_query(db: str, body: QueryBody) -> dict:
    """Execute `body.sql`. Result sets return columns+rows; other statements
    return an affected-row count. The transaction commits on success."""
    statement = body.sql.strip()
    if not statement:
        raise HTTPException(400, "no SQL provided")
    with target_db(db) as conn:
        try:
            cur = conn.execute(statement)
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
        if cur.description is None:
            return {"columns": [], "rows": [], "rowcount": cur.rowcount,
                    "message": f"{cur.rowcount} row(s) affected"}
        rows = cur.fetchall()
        columns = [d.name for d in cur.description]
    return {"columns": columns, "rows": rows, "rowcount": len(rows),
            "message": f"{len(rows)} row(s)"}
```

- [ ] **Step 4: Register the router in `src/dbmanager/webapp.py`**

After the `rows` router line, add:

```python
from dbmanager.routes import query

app.include_router(query.router, dependencies=[Depends(require_session)])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_query.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/routes/query.py src/dbmanager/webapp.py tests/test_query.py
git commit -m "feat: SQL console route"
```

---

## Task 16: SQL Console UI

**Files:**
- Create: `src/dbmanager/web/query.js`
- Modify: `src/dbmanager/web/app.js`

- [ ] **Step 1: Create `src/dbmanager/web/query.js`**

```js
import { get, post } from "./api.js";
import { showError } from "./app.js";

// Render the SQL console. `preferredDb` is the database last selected.
export async function renderConsole(preferredDb) {
  const panel = document.getElementById("panel");
  panel.innerHTML = "";

  const h = document.createElement("h2");
  h.textContent = "SQL Console";
  panel.append(h);

  const databases = await get("/api/databases");
  const picker = document.createElement("select");
  for (const d of databases) {
    const o = document.createElement("option");
    o.value = d.name; o.textContent = d.name;
    picker.append(o);
  }
  if (preferredDb) picker.value = preferredDb;

  const banner = document.createElement("p");
  banner.className = "notice";
  const setBanner = () => {
    banner.textContent = `Statements run against "${picker.value}".`;
  };
  picker.onchange = setBanner;
  setBanner();

  const editor = document.createElement("textarea");
  editor.rows = 8;
  editor.style.width = "100%";
  editor.placeholder = "SELECT * FROM ...";

  const runBtn = document.createElement("button");
  runBtn.textContent = "Run";

  const toolbar = document.createElement("div");
  toolbar.className = "toolbar";
  toolbar.append(picker, runBtn);

  const result = document.createElement("div");

  runBtn.onclick = async () => {
    result.innerHTML = "";
    try {
      const data = await post(
        `/api/databases/${encodeURIComponent(picker.value)}/query`,
        { sql: editor.value });
      const msg = document.createElement("p");
      msg.className = "notice";
      msg.textContent = data.message;
      result.append(msg);
      if (data.columns.length) result.append(resultGrid(data));
    } catch (e) { showError(e.message); }
  };

  panel.append(toolbar, banner, editor, result);
}

function resultGrid(data) {
  const table = document.createElement("table");
  table.className = "grid";
  table.innerHTML =
    `<thead><tr>${data.columns.map((c) => `<th>${c}</th>`).join("")}</tr></thead>`;
  const body = document.createElement("tbody");
  for (const row of data.rows) {
    const tr = document.createElement("tr");
    for (const c of data.columns) {
      const td = document.createElement("td");
      td.textContent = row[c] === null ? "∅" : String(row[c]);
      tr.append(td);
    }
    body.append(tr);
  }
  table.append(body);
  return table;
}
```

- [ ] **Step 2: Wire `query.js` into `app.js`**

In `src/dbmanager/web/app.js`, add to the import block at the top:

```js
import { renderConsole as consoleView } from "./query.js";
```

Replace the placeholder function:

```js
function renderConsole(db) {
  document.getElementById("panel").textContent = "SQL Console";
}
```

with:

```js
function renderConsole(db) {
  consoleView(db);
}
```

- [ ] **Step 3: Verify in the browser**

Run: `dbmanager web`, log in, click "▸ SQL Console".
Expected: a database picker with a banner naming the target database, a query editor, and a Run button; `SELECT` shows a result grid; DDL/DML shows an affected-row message; a bad statement shows the Postgres error.

- [ ] **Step 4: Commit**

```bash
git add src/dbmanager/web/query.js src/dbmanager/web/app.js
git commit -m "feat: SQL console UI"
```

---

# Phase 6 — Deployment

## Task 17: Docker packaging

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.dockerignore`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "dbmanager.webapp:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `.dockerignore`**

```
.git
.venv
venv
__pycache__
*.egg-info
.pytest_cache
tests
docs
.env
```

- [ ] **Step 3: Create `docker-compose.yml`**

The app connects to Postgres running on the VPS host. On Linux, `network_mode: host` lets the container reach `127.0.0.1:5432` directly.

```yaml
services:
  dbmanager:
    build: .
    container_name: dbmanager
    restart: unless-stopped
    env_file: .env
    network_mode: host
    # network_mode: host makes the container share the host network, so
    # DATABASE_URL can point at 127.0.0.1:5432 and the app listens on
    # the host's port 8000. If you prefer bridge networking instead,
    # remove network_mode, add `ports: ["8000:8000"]`, and set
    # DATABASE_URL host to `host.docker.internal` with:
    #   extra_hosts: ["host.docker.internal:host-gateway"]
```

- [ ] **Step 4: Build and verify**

Run: `docker compose build`
Expected: image builds without error.

Run: `docker compose up -d` then `curl -s http://127.0.0.1:8000/ | grep -o "Database Manager"`
Expected: prints `Database Manager`. Then `docker compose down`.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "chore: docker packaging"
```

---

## Task 18: Deployment documentation + README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# Postgres Database Manager

A self-hosted web app for full CRUD over a Postgres server: create/drop
databases, manage table structure, edit rows, and run SQL.

## Configuration

Copy `.env.example` to `.env` and set:

- `DATABASE_URL` — connection string pointing at the **`postgres`** maintenance
  database. The app substitutes the database name per request.
- `APP_PASSWORD` — the password for the web login.
- `APP_SECRET` — a random 32+ character string for signing session cookies.
  Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Run locally

```
pip install -e ".[dev]"
dbmanager web
```

Open http://127.0.0.1:8000.

## Run tests

```
pytest
```

## Deploy on a VPS (Docker)

```
git clone <repo> && cd database_manager
cp .env.example .env   # then edit .env
docker compose up -d --build
```

The app listens on port 8000.

### HTTPS

The login password crosses the network, so put a TLS-terminating reverse
proxy in front. Example Caddyfile:

```
db.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Caddy obtains and renews a certificate automatically. Do not expose port 8000
directly to the internet.

## Security notes

- A single password gates the entire app; the connected Postgres role's
  privileges set the ceiling on what the app can do.
- The SQL Console runs arbitrary SQL by design — that is the point of the
  tool. The login is the security boundary.
- Destructive actions (drop database/table/column, delete rows) require typed
  confirmation in the UI.
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: all tests across `test_config`, `test_auth`, `test_db`, `test_webapp`, `test_sqlbuild`, `test_inspect`, `test_databases`, `test_tables`, `test_rows`, `test_query` pass.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README and deployment guide"
```

---

# Self-Review Notes

- **Spec coverage:** login/session (Tasks 4, 6, 7); databases list/create/drop (Tasks 8, 9); table introspection + full DDL — columns, constraints, indexes (Tasks 10, 11, 12); row CRUD with PK-based editing and the no-PK read-only rule (Tasks 13, 14); SQL console (Tasks 15, 16); `.env` config (Tasks 1, 2); Docker + deployment + HTTPS guidance (Tasks 17, 18); `pytest`/`pytest-postgresql` testing throughout.
- **Naming:** the spec's `sql.py` is implemented as `sqlbuild.py` to avoid shadowing `psycopg.sql`; all other module names match the spec.
- **`test_inspect.py`** is listed in the file structure but introspection is covered indirectly by `test_databases.py` and `test_tables.py`; a dedicated `test_inspect.py` is optional and not a separate task.
- **Open decision (schema scope):** all introspection and DDL target the `public` schema, as the spec states.
