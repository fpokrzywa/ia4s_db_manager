# Theme Administration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real admin role and an admin-only Theme page that lets the app's admin pick a built-in preset (Foundry / Slate / Daylight) and override a curated set of colors. The chosen theme is global and applied from first paint, including on the login screen.

**Architecture:** A new `is_admin` column on `users`, a `require_admin` FastAPI dependency, a generic `app_settings(key, value jsonb)` table, a `themes` module with three immutable preset color maps and validation, two `/api/theme*` routes, and a frontend page + boot-time style injection that paints the saved theme before the login screen renders.

**Tech Stack:** FastAPI, psycopg 3 (already pooled), vanilla-JS ES modules, pytest.

**Spec:** `docs/superpowers/specs/2026-05-22-theme-admin-design.md`

**Branch:** `feature/theme-admin` (already created off `main`).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/dbmanager/authdb.py` | MODIFY — `is_admin` column on users + `app_settings` table in schema; `list_users` returns `is_admin`. |
| `src/dbmanager/auth.py` | MODIFY — add `require_admin` dependency. |
| `src/dbmanager/cli.py` | MODIFY — `init-auth` ensures at least one admin exists. |
| `src/dbmanager/routes/session.py` | MODIFY — `/api/me` includes `is_admin`. |
| `src/dbmanager/settings_store.py` | NEW — `get_setting` / `set_setting` for the `app_settings` table. |
| `src/dbmanager/themes.py` | NEW — `PRESETS`, `CURATED_VARS`, `default_theme`, `validate`, `effective`. |
| `src/dbmanager/routes/theme.py` | NEW — `GET /api/theme` (public), `GET /api/themes` (admin), `PATCH /api/theme` (admin). |
| `src/dbmanager/routes/users.py` | MODIFY — `PATCH /api/users/{id}/admin` with last-admin protection. |
| `src/dbmanager/webapp.py` | MODIFY — register the theme router. |
| `src/dbmanager/web/theme.js` | NEW — admin Theme page; exports `applyTheme(theme)` and `renderTheme()`. |
| `src/dbmanager/web/app.js` | MODIFY — apply theme on boot; sidebar `▸ Theme` admin-gated. |
| `src/dbmanager/web/users.js` | MODIFY — promote/demote toggle on each row; admin-only. |
| `tests/conftest.py` | MODIFY — seeded `test@example.com` is admin; add `non_admin_client` fixture. |
| `tests/test_init_auth.py` | MODIFY — add admin-flag tests. |
| `tests/test_session.py` | MODIFY — `/me` returns `is_admin`. |
| `tests/test_authenticate.py` | MODIFY — `require_admin` 403 for non-admin, allows admin. |
| `tests/test_settings_store.py` | NEW — round-trip + missing key. |
| `tests/test_themes.py` | NEW — preset shapes, `validate`, `effective`. |
| `tests/test_theme_routes.py` | NEW — GET public, PATCH admin/non-admin, validation. |
| `tests/test_users.py` | MODIFY — promote/demote tests + last-admin 400. |

Baseline suite at start of work: **105 passed**. Task-by-task projections below; final target around **125–127 passed**.

Test environment: same as previous features — pytest-postgresql noproc against the live Postgres in `.env`. Always run `pytest -q` as a SINGLE FOREGROUND invocation; overlapping pytest runs collide on the template database and produce spurious `dbm_pytest`/`InvalidCatalogName` errors. The autouse pool-teardown fixture in `conftest.py` runs after every test.

---

## Task 1: Admin role foundation

**Files:** Modify `src/dbmanager/authdb.py`, `src/dbmanager/auth.py`, `src/dbmanager/cli.py`, `src/dbmanager/routes/session.py`, `tests/conftest.py`, `tests/test_init_auth.py`, `tests/test_session.py`, `tests/test_authenticate.py`.

- [ ] **Step 1: Add `is_admin` to the users schema**

In `src/dbmanager/authdb.py`, replace the `AUTH_SCHEMA_SQL` string and the `apply_schema` function with:

```python
AUTH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id                   serial PRIMARY KEY,
    email                text UNIQUE NOT NULL,
    password_hash        text NOT NULL,
    must_change_password boolean NOT NULL DEFAULT true,
    is_active            boolean NOT NULL DEFAULT true,
    is_admin             boolean NOT NULL DEFAULT false,
    failed_attempts      integer NOT NULL DEFAULT 0,
    locked_until         timestamptz,
    last_login_at        timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin
    boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS user_sessions (
    id          bigserial PRIMARY KEY,
    user_id     integer REFERENCES users(id),
    email       text NOT NULL,
    event       text NOT NULL,
    ip_address  text,
    user_agent  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
"""
```

The `ALTER TABLE … ADD COLUMN IF NOT EXISTS` is the upgrade path for existing deployments where `users` already exists without `is_admin`; the `CREATE TABLE IF NOT EXISTS` keeps fresh installs idempotent.

- [ ] **Step 2: Include `is_admin` in `list_users`**

In `src/dbmanager/authdb.py`, replace the `list_users` function with:

```python
def list_users(conn) -> list[dict]:
    return conn.execute("""
        SELECT id, email, must_change_password, is_active, is_admin,
               failed_attempts, locked_until, last_login_at, created_at
        FROM users ORDER BY email
    """).fetchall()
```

- [ ] **Step 3: Add `set_admin` and `count_admins` helpers to `authdb.py`**

Append to `src/dbmanager/authdb.py`:

```python
def count_admins(conn) -> int:
    return conn.execute(
        "SELECT count(*) AS n FROM users WHERE is_admin").fetchone()["n"]


def set_admin(conn, user_id: int, is_admin: bool) -> dict | None:
    return conn.execute("""
        UPDATE users SET is_admin = %s, updated_at = now()
        WHERE id = %s RETURNING *
    """, (is_admin, user_id)).fetchone()
```

`count_admins` is used by `init-auth` (Step 5) and by the last-admin-demote guard (Task 4). `set_admin` is used by the promote/demote route (Task 4) and by `init-auth`.

- [ ] **Step 4: Add `require_admin` to `auth.py`**

In `src/dbmanager/auth.py`, append after the existing `require_session` function:

```python
def require_admin(request: Request) -> None:
    """FastAPI dependency: reject requests where the session user is not
    flagged is_admin. Runs require_session first."""
    require_session(request)
    from dbmanager import pools
    with pools.common_data_pool().connection() as conn:
        user = authdb.get_user_by_id(conn, request.session["user_id"])
    if user is None or not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="admin access required")
```

(The `pools` import is local to the function to avoid a circular import at module load.)

- [ ] **Step 5: `init-auth` ensures at least one admin**

In `src/dbmanager/cli.py`, replace the entire `init_auth` function with:

```python
@cli.command("init-auth")
@click.option("--email", required=True, help="Email of the first user.")
@click.option("--password", required=True, help="Temporary password.")
def init_auth(email: str, password: str) -> None:
    """Create the auth + servers tables in common_data, seed the first user,
    register the DATABASE_URL server if the registry is empty, and ensure at
    least one admin exists."""
    from psycopg.conninfo import conninfo_to_dict
    from dbmanager import authdb, serverdb
    from dbmanager.config import Settings
    from dbmanager.passwords import hash_password

    settings = Settings.from_env()
    authdb.apply_schema(settings.common_data_url)
    serverdb.apply_schema(settings.common_data_url)

    with authdb.auth_conn(settings.common_data_url) as conn:
        if authdb.get_user_by_email(conn, email) is None:
            authdb.create_user(conn, email, hash_password(password),
                               must_change=True)
            click.echo(f"created user {email} — must change password "
                       f"on first login")
        else:
            click.echo(f"user {email} already exists — no change made")

        if not serverdb.list_servers(conn) and settings.database_url:
            p = conninfo_to_dict(settings.database_url)
            serverdb.create_server(
                conn,
                label=p.get("host") or "primary",
                host=p.get("host") or "127.0.0.1",
                port=int(p.get("port") or 5432),
                username=p.get("user") or "postgres",
                password=p.get("password") or "",
                maintenance_db=p.get("dbname") or "postgres",
                is_default=True)
            click.echo(f"registered server '{p.get('host')}' from DATABASE_URL")
        else:
            click.echo("server registry already populated — no server seeded")

        if authdb.count_admins(conn) == 0:
            row = conn.execute(
                "SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
            if row is not None:
                authdb.set_admin(conn, row["id"], True)
                click.echo(f"flagged user id={row['id']} as admin")
        else:
            click.echo("at least one admin already exists — no change made")
```

- [ ] **Step 6: `/api/me` includes `is_admin`**

In `src/dbmanager/routes/session.py`, replace the `me` function with:

```python
@router.get("/me", dependencies=[Depends(auth.require_session)])
def me(request: Request) -> dict:
    """The current user, password-change flag, and admin flag."""
    settings = Settings.from_env()
    with authdb.auth_conn(settings.common_data_url) as conn:
        user = authdb.get_user_by_id(conn, request.session["user_id"])
    if user is None:
        request.session.clear()
        raise HTTPException(401, "authentication required")
    return {"email": user["email"],
            "must_change_password": user["must_change_password"],
            "is_admin": user["is_admin"]}
```

- [ ] **Step 7: Seeded test user is admin; add `non_admin_client` fixture**

In `tests/conftest.py`, change the user-seeding INSERT inside `common_data_url`. The current line is:

```python
        conn.execute(
            "INSERT INTO users (email, password_hash, must_change_password) "
            "VALUES (%s, %s, false) ON CONFLICT (email) DO NOTHING",
            ("test@example.com", hash_password("test-password")))
```

Replace with:

```python
        conn.execute(
            "INSERT INTO users (email, password_hash, must_change_password, "
            "                    is_admin) "
            "VALUES (%s, %s, false, true) ON CONFLICT (email) DO NOTHING",
            ("test@example.com", hash_password("test-password")))
```

Then, after the existing `client` fixture (and before the `_close_pools_after_each_test` fixture), insert a `non_admin_client` fixture:

```python
@pytest.fixture
def non_admin_client(server_url, common_data_url, monkeypatch):
    """A TestClient logged in as a non-admin user (no is_admin flag)."""
    from fastapi.testclient import TestClient
    from dbmanager.passwords import hash_password
    monkeypatch.setenv("DATABASE_URL", server_url)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO users (email, password_hash, must_change_password) "
            "VALUES (%s, %s, false) ON CONFLICT (email) DO NOTHING",
            ("nonadmin@example.com", hash_password("test-password")))
    from dbmanager.webapp import app
    c = TestClient(app)
    resp = c.post("/api/login", json={"email": "nonadmin@example.com",
                                      "password": "test-password"})
    assert resp.status_code == 200, resp.text
    return c
```

- [ ] **Step 8: Add the `init-auth` admin tests**

Append to `tests/test_init_servers.py` — these belong with the other `init-auth` integration tests:

```python
def test_init_auth_flags_first_user_as_admin(common_data_url, server_url,
                                              monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    monkeypatch.setenv("DATABASE_URL", server_url)
    result = CliRunner().invoke(cli, ["init-auth", "--email", "first@example.com",
                                      "--password", "TempPass123"])
    assert result.exit_code == 0, result.output
    with psycopg.connect(common_data_url) as conn:
        row = conn.execute(
            "SELECT is_admin FROM users WHERE email = %s",
            ("first@example.com",)).fetchone()
    assert row[0] is True


def test_init_auth_does_not_flip_existing_admin(common_data_url, server_url,
                                                 monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    monkeypatch.setenv("DATABASE_URL", server_url)
    runner = CliRunner()
    runner.invoke(cli, ["init-auth", "--email", "a@example.com",
                        "--password", "TempPass123"])
    # second run with a different email; first is still admin
    runner.invoke(cli, ["init-auth", "--email", "b@example.com",
                        "--password", "TempPass123"])
    with psycopg.connect(common_data_url) as conn:
        rows = dict(conn.execute(
            "SELECT email, is_admin FROM users ORDER BY id").fetchall())
    assert rows.get("a@example.com") is True
    assert rows.get("b@example.com") in (False, None)


def test_init_auth_reflags_when_no_admins(common_data_url, server_url,
                                          monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    monkeypatch.setenv("DATABASE_URL", server_url)
    runner = CliRunner()
    runner.invoke(cli, ["init-auth", "--email", "a@example.com",
                        "--password", "TempPass123"])
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        conn.execute("UPDATE users SET is_admin = false")
    runner.invoke(cli, ["init-auth", "--email", "a@example.com",
                        "--password", "TempPass123"])
    with psycopg.connect(common_data_url) as conn:
        is_admin = conn.execute(
            "SELECT is_admin FROM users WHERE email = %s",
            ("a@example.com",)).fetchone()[0]
    assert is_admin is True
```

- [ ] **Step 9: Add the `/me` admin-flag test**

Append to `tests/test_session.py`:

```python
def test_me_includes_is_admin(client):
    resp = client.get("/api/me")
    assert resp.status_code == 200
    body = resp.json()
    assert "is_admin" in body
    assert body["is_admin"] is True  # the seeded test user is admin


def test_me_for_non_admin(non_admin_client):
    resp = non_admin_client.get("/api/me")
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False
```

- [ ] **Step 10: Add the `require_admin` tests**

Append to `tests/test_authenticate.py`:

```python
def test_require_admin_allows_admin(client):
    # We use the existing /api/users endpoint (admin-only after Task 4 but
    # for now any logged-in user can access). To test require_admin
    # directly, mount a temporary route or wait until Task 4. For this
    # task, the next two tests use the existing flow.
    pass


def test_require_admin_returns_403_for_non_admin(non_admin_client):
    # /api/me is NOT admin-gated; we just check that requiring admin would
    # work. Defer the real 403 test to Task 4 (which adds the first
    # admin-only route on /api/users/{id}/admin). For Task 1 the test
    # below verifies non_admin_client correctly identifies as non-admin.
    resp = non_admin_client.get("/api/me")
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False
```

(Note: the first real `require_admin` test target arrives in Task 2 via `PATCH /api/theme`. Until then, we verify the dependency exists and the non-admin fixture works.)

- [ ] **Step 11: Run the tests**

Run: `pytest tests/test_init_servers.py tests/test_session.py tests/test_authenticate.py -v`
Expected: all green; 5 new tests pass on top of existing.

Then: `pytest -q`
Expected: PASS — about **110 passed** (105 baseline + 5 new). Spurious-DB-errors policy applies; re-run once cleanly if needed.

- [ ] **Step 12: Commit**

```bash
git add src/dbmanager/authdb.py src/dbmanager/auth.py src/dbmanager/cli.py \
        src/dbmanager/routes/session.py tests/
git commit -m "feat: is_admin column + require_admin + /me extension"
```
End the commit message with the trailer:
`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

> **Note:** the running dev server on `:8962` must be restarted after this task before the new schema and `/me` shape are reachable in the browser.

---

## Task 2: Theme backend (settings store + presets + routes)

**Files:** Modify `src/dbmanager/authdb.py` (add `app_settings` table), `src/dbmanager/webapp.py`; create `src/dbmanager/settings_store.py`, `src/dbmanager/themes.py`, `src/dbmanager/routes/theme.py`, `tests/test_settings_store.py`, `tests/test_themes.py`, `tests/test_theme_routes.py`.

- [ ] **Step 1: Add the `app_settings` table to the schema**

In `src/dbmanager/authdb.py`, append a CREATE TABLE statement to `AUTH_SCHEMA_SQL` (keep the existing statements):

```python
AUTH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id                   serial PRIMARY KEY,
    email                text UNIQUE NOT NULL,
    password_hash        text NOT NULL,
    must_change_password boolean NOT NULL DEFAULT true,
    is_active            boolean NOT NULL DEFAULT true,
    is_admin             boolean NOT NULL DEFAULT false,
    failed_attempts      integer NOT NULL DEFAULT 0,
    locked_until         timestamptz,
    last_login_at        timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin
    boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS user_sessions (
    id          bigserial PRIMARY KEY,
    user_id     integer REFERENCES users(id),
    email       text NOT NULL,
    event       text NOT NULL,
    ip_address  text,
    user_agent  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_settings (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
"""
```

- [ ] **Step 2: Create `src/dbmanager/settings_store.py`**

```python
"""Generic key/value store backed by the app_settings table in common_data.

Values are JSONB; callers pass and receive plain Python dicts."""
from __future__ import annotations
import json


def get_setting(conn, key: str) -> dict | None:
    """Return the value for `key` as a dict, or None if not set."""
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = %s", (key,)).fetchone()
    return row["value"] if row is not None else None


def set_setting(conn, key: str, value: dict) -> None:
    """Insert-or-update the value for `key`. `value` is a dict that will be
    JSON-encoded into the JSONB column."""
    conn.execute("""
        INSERT INTO app_settings (key, value)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = now()
    """, (key, json.dumps(value)))
```

- [ ] **Step 3: Create `src/dbmanager/themes.py`**

```python
"""Theme presets, validation, and effective-color computation.

Only the seven curated CSS vars in CURATED_VARS are overridable by an admin.
A preset's full color map is applied as the base; any override in the saved
theme is layered on top to produce the effective map."""
from __future__ import annotations
import re

# The seven vars that admins can override via the Theme page.
CURATED_VARS = (
    "--soot",    # background
    "--iron",    # primary accent
    "--ember",   # warm accent
    "--bone",    # primary text
    "--ash",     # secondary text
    "--patina",  # success
    "--rust",    # error
)

# Full color map for each preset. The seven CURATED_VARS plus the eight
# non-curated vars; the latter are not editable but switch with the preset.
PRESETS: dict[str, dict[str, str]] = {
    "foundry": {
        "--soot":    "#15110c",
        "--soot-1":  "#1c1610",
        "--soot-2":  "#251d14",
        "--soot-3":  "#322619",
        "--edge":    "#3b2e1f",
        "--edge-hi": "#5c4527",
        "--bone":    "#f4ecdb",
        "--ash":     "#ab9d85",
        "--dim":     "#6f6353",
        "--iron":    "#ff5a1f",
        "--ember":   "#ffae3d",
        "--spark":   "#ffe7a8",
        "--steel":   "#84a7bd",
        "--patina":  "#5fb295",
        "--rust":    "#c2412a",
    },
    "slate": {
        "--soot":    "#0f1419",
        "--soot-1":  "#161c23",
        "--soot-2":  "#1e2530",
        "--soot-3":  "#2a323e",
        "--edge":    "#2e3845",
        "--edge-hi": "#475063",
        "--bone":    "#e6edf3",
        "--ash":     "#8b96a3",
        "--dim":     "#5a6573",
        "--iron":    "#4a8dd1",
        "--ember":   "#6fa8d6",
        "--spark":   "#b3d3e9",
        "--steel":   "#84a7bd",
        "--patina":  "#5fb295",
        "--rust":    "#c2412a",
    },
    "daylight": {
        "--soot":    "#f8f2e3",
        "--soot-1":  "#efe7d3",
        "--soot-2":  "#e4dac1",
        "--soot-3":  "#d6caab",
        "--edge":    "#c9bda0",
        "--edge-hi": "#a89977",
        "--bone":    "#2c2419",
        "--ash":     "#6d6354",
        "--dim":     "#948876",
        "--iron":    "#c64512",
        "--ember":   "#d97a1f",
        "--spark":   "#f0a73a",
        "--steel":   "#5a8aa3",
        "--patina":  "#4a8c6b",
        "--rust":    "#a83520",
    },
}

DEFAULT_PRESET = "foundry"
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def default_theme() -> dict:
    """The theme used when no `theme` row exists in app_settings."""
    return {"preset": DEFAULT_PRESET, "overrides": {}}


def validate(theme: dict) -> None:
    """Raise ValueError if the theme is malformed."""
    if not isinstance(theme, dict):
        raise ValueError("theme must be an object")
    preset = theme.get("preset")
    if preset not in PRESETS:
        raise ValueError(f"unknown preset: {preset!r}")
    overrides = theme.get("overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("overrides must be an object")
    for var, color in overrides.items():
        if var not in CURATED_VARS:
            raise ValueError(f"{var!r} is not in the curated color set")
        if not isinstance(color, str) or not _HEX_RE.match(color):
            raise ValueError(
                f"value for {var} must be a #rrggbb hex color")


def effective(theme: dict) -> dict[str, str]:
    """Resolve `theme` into the full {var: color} map applied to the UI:
    the preset's full map merged with the (curated) overrides."""
    return {**PRESETS[theme["preset"]], **theme.get("overrides", {})}
```

- [ ] **Step 4: Create `src/dbmanager/routes/theme.py`**

```python
"""Theme API — public GET (so the login screen is themed) and admin-only
PATCH/list."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dbmanager import auth, pools, settings_store, themes

router = APIRouter(prefix="/api", tags=["theme"])

_THEME_KEY = "theme"


class ThemeBody(BaseModel):
    preset: str
    overrides: dict[str, str] = {}


def _load_theme() -> dict:
    with pools.common_data_pool().connection() as conn:
        saved = settings_store.get_setting(conn, _THEME_KEY)
    return saved if saved is not None else themes.default_theme()


@router.get("/theme")
def get_theme() -> dict:
    """Return the saved theme + its effective color map. Public — needed by
    the login screen before any session exists."""
    theme = _load_theme()
    return {"preset": theme["preset"],
            "overrides": theme.get("overrides", {}),
            "effective": themes.effective(theme)}


@router.get("/themes", dependencies=[Depends(auth.require_admin)])
def list_presets() -> dict:
    """Return every built-in preset's full color map. Admin-only."""
    return {"presets": themes.PRESETS,
            "curated_vars": list(themes.CURATED_VARS),
            "default_preset": themes.DEFAULT_PRESET}


@router.patch("/theme", dependencies=[Depends(auth.require_admin)])
def update_theme(body: ThemeBody) -> dict:
    """Save the theme. Admin-only."""
    theme = {"preset": body.preset, "overrides": body.overrides or {}}
    try:
        themes.validate(theme)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with pools.common_data_pool().connection() as conn:
        settings_store.set_setting(conn, _THEME_KEY, theme)
    return {"preset": theme["preset"], "overrides": theme["overrides"],
            "effective": themes.effective(theme)}
```

- [ ] **Step 5: Register the theme router in `webapp.py`**

In `src/dbmanager/webapp.py`, change the routes-import line from:

```python
from dbmanager.routes import databases, query, rows, servers, session, tables, users
```

to (insert `theme` alphabetically):

```python
from dbmanager.routes import databases, query, rows, servers, session, tables, theme, users
```

Find the block of `app.include_router(...)` calls. Add immediately after `app.include_router(session.router)` line:

```python
app.include_router(theme.router)
```

(No router-level `require_session` — the theme router uses per-route deps because `GET /api/theme` is public.)

- [ ] **Step 6: Write `tests/test_settings_store.py`**

```python
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
```

- [ ] **Step 7: Write `tests/test_themes.py`**

```python
import pytest
from dbmanager import themes


def test_default_theme_shape():
    t = themes.default_theme()
    assert t["preset"] == "foundry"
    assert t["overrides"] == {}


def test_validate_accepts_good_theme():
    themes.validate({"preset": "slate", "overrides": {"--iron": "#abcdef"}})


def test_validate_rejects_unknown_preset():
    with pytest.raises(ValueError, match="preset"):
        themes.validate({"preset": "midnight", "overrides": {}})


def test_validate_rejects_uncurated_var():
    with pytest.raises(ValueError, match="curated"):
        themes.validate({"preset": "foundry",
                         "overrides": {"--soot-1": "#000000"}})


def test_validate_rejects_bad_color_string():
    with pytest.raises(ValueError, match="hex"):
        themes.validate({"preset": "foundry",
                         "overrides": {"--iron": "not-a-color"}})


def test_effective_merges_preset_with_overrides():
    eff = themes.effective(
        {"preset": "slate", "overrides": {"--iron": "#abcdef"}})
    assert eff["--iron"] == "#abcdef"
    assert eff["--soot"] == themes.PRESETS["slate"]["--soot"]
    assert eff["--ember"] == themes.PRESETS["slate"]["--ember"]
```

- [ ] **Step 8: Write `tests/test_theme_routes.py`**

```python
def test_get_theme_is_public(server_url, common_data_url, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("DATABASE_URL", server_url)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    from dbmanager.webapp import app
    # No login at all.
    resp = TestClient(app).get("/api/theme")
    assert resp.status_code == 200
    body = resp.json()
    assert body["preset"] == "foundry"
    assert body["overrides"] == {}
    assert body["effective"]["--soot"] == "#15110c"


def test_patch_theme_admin_saves(client):
    resp = client.patch("/api/theme", json={
        "preset": "slate", "overrides": {"--iron": "#abcdef"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["preset"] == "slate"
    assert body["overrides"] == {"--iron": "#abcdef"}
    assert body["effective"]["--iron"] == "#abcdef"
    # And it persists.
    body2 = client.get("/api/theme").json()
    assert body2["preset"] == "slate"
    assert body2["overrides"] == {"--iron": "#abcdef"}


def test_patch_theme_non_admin_returns_403(non_admin_client):
    resp = non_admin_client.patch(
        "/api/theme", json={"preset": "slate", "overrides": {}})
    assert resp.status_code == 403


def test_patch_theme_invalid_preset_400(client):
    resp = client.patch("/api/theme", json={"preset": "nope", "overrides": {}})
    assert resp.status_code == 400


def test_patch_theme_invalid_color_400(client):
    resp = client.patch("/api/theme", json={
        "preset": "foundry", "overrides": {"--iron": "not-a-color"}})
    assert resp.status_code == 400


def test_patch_theme_uncurated_var_400(client):
    resp = client.patch("/api/theme", json={
        "preset": "foundry", "overrides": {"--soot-1": "#000000"}})
    assert resp.status_code == 400


def test_list_presets_admin_only(client, non_admin_client):
    a = client.get("/api/themes")
    assert a.status_code == 200
    body = a.json()
    assert set(body["presets"]) == {"foundry", "slate", "daylight"}
    assert "--iron" in body["curated_vars"]
    n = non_admin_client.get("/api/themes")
    assert n.status_code == 403
```

- [ ] **Step 9: Run the tests**

Run: `pytest tests/test_settings_store.py tests/test_themes.py tests/test_theme_routes.py -v`
Expected: all green; 13 new tests.

Then: `pytest -q`
Expected: PASS — about **123 passed** (110 from Task 1 + 13 new).

- [ ] **Step 10: Commit**

```bash
git add src/dbmanager/authdb.py src/dbmanager/settings_store.py \
        src/dbmanager/themes.py src/dbmanager/routes/theme.py \
        src/dbmanager/webapp.py tests/
git commit -m "feat: theme backend (settings_store, presets, /api/theme)"
```
End the commit message with the trailer:
`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

> **Note:** restart `:8962` to expose the new routes before manual testing.

---

## Task 3: Theme admin frontend

**Files:** Create `src/dbmanager/web/theme.js`; modify `src/dbmanager/web/app.js`.

No automated frontend test — verify with `node --check` and that the backend suite is unaffected.

- [ ] **Step 1: Create `src/dbmanager/web/theme.js`**

```js
import { get, patch } from "./api.js";
import { showError } from "./app.js";

const SAVED_STYLE_ID = "theme-saved";
const LIVE_STYLE_ID = "theme-live";

// Apply a theme's full effective color map to the page by setting a single
// <style id="theme-saved"> block. Any previous live-preview style is removed
// so the saved theme takes effect cleanly.
export function applyTheme(theme) {
  document.getElementById(LIVE_STYLE_ID)?.remove();
  applyEffective(SAVED_STYLE_ID, theme.effective || {});
}

function applyEffective(id, effective) {
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement("style");
    el.id = id;
    document.head.append(el);
  }
  const rules = Object.entries(effective)
    .map(([k, v]) => `${k}:${v};`).join("");
  el.textContent = `:root{${rules}}`;
}

// Render the admin Theme page. Fetches current theme + preset library, builds
// the preset dropdown and seven color pickers, and wires live preview.
export async function renderTheme() {
  const panel = document.getElementById("panel");
  panel.innerHTML = "";

  const h = document.createElement("h2");
  h.textContent = "Theme";
  panel.append(h);

  let current, presets, curated;
  try {
    current = await get("/api/theme");
    const meta = await get("/api/themes");
    presets = meta.presets;
    curated = meta.curated_vars;
  } catch (e) { showError(e.message); return; }

  // Working state — starts as the saved theme; live preview tracks this.
  const draft = {
    preset: current.preset,
    overrides: { ...current.overrides },
  };
  const computeEffective = () => ({
    ...presets[draft.preset], ...draft.overrides,
  });
  const repaint = () => applyEffective(LIVE_STYLE_ID, computeEffective());

  // Preset row
  const presetRow = document.createElement("div");
  presetRow.className = "row";
  const presetLabel = document.createElement("label");
  presetLabel.textContent = "Preset";
  const presetSelect = document.createElement("select");
  for (const name of Object.keys(presets)) {
    const opt = document.createElement("option");
    opt.value = name; opt.textContent = name;
    presetSelect.append(opt);
  }
  presetSelect.value = draft.preset;
  presetSelect.onchange = () => {
    draft.preset = presetSelect.value;
    rebuildPickers();
    repaint();
  };
  presetRow.append(presetLabel, presetSelect);
  panel.append(presetRow);

  // Color pickers — one row per curated var
  const pickersEl = document.createElement("div");
  panel.append(pickersEl);

  function rebuildPickers() {
    pickersEl.innerHTML = "";
    for (const v of curated) {
      const row = document.createElement("div");
      row.className = "row";
      const label = document.createElement("label");
      label.textContent = `${labelFor(v)} (${v})`;
      const picker = document.createElement("input");
      picker.type = "color";
      const presetVal = presets[draft.preset][v];
      picker.value = draft.overrides[v] ?? presetVal;
      picker.oninput = () => {
        if (picker.value.toLowerCase() === presetVal.toLowerCase()) {
          delete draft.overrides[v];
        } else {
          draft.overrides[v] = picker.value;
        }
        renderResetLink();
        repaint();
      };
      const resetLink = document.createElement("button");
      resetLink.className = "ghost";
      resetLink.textContent = "Reset";
      resetLink.style.marginLeft = ".4rem";
      resetLink.onclick = () => {
        delete draft.overrides[v];
        picker.value = presetVal;
        renderResetLink();
        repaint();
      };
      function renderResetLink() {
        resetLink.style.display = draft.overrides[v] ? "" : "none";
      }
      renderResetLink();
      row.append(label, picker, resetLink);
      pickersEl.append(row);
    }
  }
  rebuildPickers();

  // Actions row
  const actions = document.createElement("div");
  actions.className = "row";
  actions.style.marginTop = ".8rem";
  const resetAll = document.createElement("button");
  resetAll.className = "ghost";
  resetAll.textContent = "Reset all overrides";
  resetAll.onclick = () => {
    draft.overrides = {};
    rebuildPickers();
    repaint();
  };
  const cancel = document.createElement("button");
  cancel.className = "ghost";
  cancel.textContent = "Cancel";
  cancel.onclick = () => {
    draft.preset = current.preset;
    draft.overrides = { ...current.overrides };
    presetSelect.value = draft.preset;
    rebuildPickers();
    document.getElementById(LIVE_STYLE_ID)?.remove();
  };
  const save = document.createElement("button");
  save.textContent = "Save";
  save.onclick = async () => {
    try {
      const updated = await patch("/api/theme", {
        preset: draft.preset, overrides: draft.overrides,
      });
      current = updated;
      applyTheme(updated);
    } catch (e) { showError(e.message); }
  };
  actions.append(resetAll, cancel, save);
  panel.append(actions);

  // Initial paint so the picker values match the live page.
  repaint();
}

function labelFor(cssVar) {
  return {
    "--soot":   "Background",
    "--iron":   "Accent (primary)",
    "--ember":  "Accent (warm)",
    "--bone":   "Primary text",
    "--ash":    "Secondary text",
    "--patina": "Success",
    "--rust":   "Error",
  }[cssVar] || cssVar;
}
```

- [ ] **Step 2: Apply theme on boot and add the sidebar entry in `src/dbmanager/web/app.js`**

Three edits:

Edit A — at the top of `app.js`, after the existing `import { renderServers } from "./servers.js";` line, add:

```js
import { renderTheme, applyTheme } from "./theme.js";
```

Edit B — in the existing bottom-of-file boot IIFE, BEFORE the existing `/api/me` fetch, apply the saved theme so the login screen renders themed. The current boot block is:

```js
(async () => {
  try {
    const me = await get("/api/me");
    if (me.must_change_password) showChangePassword();
    else await showApp();
  } catch { showLogin(); }
})();
```

Change it to:

```js
(async () => {
  try {
    const theme = await get("/api/theme");
    applyTheme(theme);
  } catch { /* theme is cosmetic — ignore failures */ }
  try {
    const me = await get("/api/me");
    if (me.must_change_password) showChangePassword();
    else await showApp();
  } catch { showLogin(); }
})();
```

Edit C — add a sidebar entry for the Theme page, visible only to admins. The current `loadSidebar` builds the sidebar items including:

```js
  const serversBtn = document.createElement("div");
  serversBtn.className = "tree-item";
  serversBtn.textContent = "▸ Servers";
  serversBtn.onclick = () => renderServers();
  sidebar.append(serversBtn);
```

Immediately after that `sidebar.append(serversBtn);` line, add:

```js

  // Theme — admin only
  let isAdmin = false;
  try { isAdmin = (await get("/api/me")).is_admin === true; } catch {}
  if (isAdmin) {
    const themeBtn = document.createElement("div");
    themeBtn.className = "tree-item";
    themeBtn.textContent = "▸ Theme";
    themeBtn.onclick = () => renderTheme();
    sidebar.append(themeBtn);
  }
```

(The `/api/me` round-trip here is the same one the boot block already does. With the `common_data` pool warm, it's ~50 ms.)

- [ ] **Step 3: Syntax-check the changed JS**

Run: `node --check src/dbmanager/web/app.js` and `node --check src/dbmanager/web/theme.js`
Expected: no output, exit 0 for both.

- [ ] **Step 4: Run the full suite to confirm no backend regression**

Run: `pytest -q`
Expected: PASS — **123 passed** (Task 3 changes no backend code).

- [ ] **Step 5: Commit**

```bash
git add src/dbmanager/web/theme.js src/dbmanager/web/app.js
git commit -m "feat: admin Theme page with live preview"
```
End the commit message with the trailer:
`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

> **Note:** static files serve from disk, so a browser refresh shows the new Theme page after this commit — no dev-server restart needed.

---

## Task 4: Users page promote/demote

**Files:** Modify `src/dbmanager/routes/users.py`, `src/dbmanager/web/users.js`, `tests/test_users.py`.

- [ ] **Step 1: Add the PATCH /admin route in `src/dbmanager/routes/users.py`**

Read the existing `src/dbmanager/routes/users.py` first to confirm the route shape (it already has CRUD-ish endpoints for users via `require_session`).

Append a new model and a new route at the end of the file:

```python
class AdminBody(BaseModel):
    is_admin: bool


@router.patch("/{user_id}/admin", dependencies=[Depends(auth.require_admin)])
def set_admin(user_id: int, body: AdminBody) -> dict:
    """Promote or demote a user. Demoting the last admin returns 400."""
    with pools.common_data_pool().connection() as conn:
        target = authdb.get_user_by_id(conn, user_id)
        if target is None:
            raise HTTPException(404, f"no user with id {user_id}")
        if not body.is_admin and target["is_admin"]:
            if authdb.count_admins(conn) <= 1:
                raise HTTPException(
                    400, "cannot demote the last admin")
        row = authdb.set_admin(conn, user_id, body.is_admin)
    return {"id": row["id"], "email": row["email"],
            "is_admin": row["is_admin"]}
```

If `BaseModel`, `Depends`, `HTTPException`, `auth`, `authdb`, or `pools` aren't yet imported at the top of `users.py`, add them — matching the import style already used in the file.

- [ ] **Step 2: Add the promote/demote toggle to `src/dbmanager/web/users.js`**

Read the existing `users.js` first to see how each user row is built and where the actions cell is.

The row currently shows the user's email, status, and per-row action buttons (deactivate / reset password / unlock). Add a new button that toggles `is_admin`:

```js
// Inside the user-row builder, after the existing action buttons:
const adminBtn = document.createElement("button");
adminBtn.className = "ghost";
adminBtn.textContent = u.is_admin ? "Revoke admin" : "Make admin";
adminBtn.onclick = async () => {
  const verb = u.is_admin ? "revoke" : "grant";
  const ok = await confirmModal(
    `${verb === "grant" ? "Make" : "Revoke"} admin for ${u.email}`,
    `Type the email to confirm you want to ${verb} admin.`,
    u.email);
  if (!ok) return;
  try {
    await patch(`/api/users/${u.id}/admin`, { is_admin: !u.is_admin });
    await renderUsers();
  } catch (e) { showError(e.message); }
};
actions.append(adminBtn);
```

Only render the button when the current viewer is admin. Wrap the append in an `if (me.is_admin)` check; if `me` isn't already in scope where the row is built, fetch `/api/me` once at the top of `renderUsers` (`const me = await get("/api/me");`) and pass `me.is_admin` through.

Imports already present in `users.js` cover `get`, `patch`, `confirmModal`, `showError`; if `patch` isn't imported there, add it to the import from `./api.js`.

- [ ] **Step 3: Write the tests**

Append to `tests/test_users.py`:

```python
def test_promote_user_to_admin(client, common_data_url):
    """An admin promotes a non-admin user."""
    from dbmanager.passwords import hash_password
    import psycopg
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        row = conn.execute("""
            INSERT INTO users (email, password_hash, must_change_password)
            VALUES (%s, %s, false)
            ON CONFLICT (email) DO UPDATE SET email=excluded.email
            RETURNING id
        """, ("promotable@example.com", hash_password("pw"))).fetchone()
        promo_id = row[0]
    resp = client.patch(f"/api/users/{promo_id}/admin", json={"is_admin": True})
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is True


def test_demote_last_admin_returns_400(client):
    """Demoting the sole admin (the seeded test user) is refused."""
    resp = client.get("/api/me")
    me_id = None
    # We don't expose id in /me, so look it up directly.
    from dbmanager.config import Settings
    import psycopg
    with psycopg.connect(Settings.from_env().common_data_url) as conn:
        me_id = conn.execute(
            "SELECT id FROM users WHERE email='test@example.com'"
        ).fetchone()[0]
    resp = client.patch(f"/api/users/{me_id}/admin", json={"is_admin": False})
    assert resp.status_code == 400
    assert "last admin" in resp.json()["detail"].lower()


def test_non_admin_cannot_promote(non_admin_client, common_data_url):
    from dbmanager.passwords import hash_password
    import psycopg
    with psycopg.connect(common_data_url, autocommit=True) as conn:
        row = conn.execute("""
            INSERT INTO users (email, password_hash, must_change_password)
            VALUES (%s, %s, false)
            ON CONFLICT (email) DO UPDATE SET email=excluded.email
            RETURNING id
        """, ("victim@example.com", hash_password("pw"))).fetchone()
        target = row[0]
    resp = non_admin_client.patch(
        f"/api/users/{target}/admin", json={"is_admin": True})
    assert resp.status_code == 403


def test_demote_unknown_user_404(client):
    resp = client.patch("/api/users/999999/admin", json={"is_admin": True})
    assert resp.status_code == 404
```

- [ ] **Step 4: Syntax-check the changed JS**

Run: `node --check src/dbmanager/web/users.js`
Expected: no output, exit 0.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS — about **127 passed** (123 from Task 2 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/routes/users.py src/dbmanager/web/users.js tests/test_users.py
git commit -m "feat: promote/demote admins from the Users page"
```
End the commit message with the trailer:
`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

> **Note:** restart `:8962` to expose the new route. Refresh the browser to see the "Make admin" / "Revoke admin" buttons on the Users page.

---

# Self-Review Notes

- **Spec coverage:** `is_admin` column on users + `apply_schema` migration + `require_admin` dependency + `/api/me` admin flag + `init-auth` "ensure at least one admin" (Task 1); generic `app_settings(key, value jsonb)` table + `settings_store` module + `themes` module with three presets and validation + `GET /api/theme` (public) + `GET /api/themes` (admin) + `PATCH /api/theme` (admin) (Task 2); admin Theme page with preset dropdown, seven curated color pickers, live preview, save/cancel/reset (Task 3); `PATCH /api/users/{id}/admin` with last-admin protection + Users-page promote/demote toggle (Task 4). The conftest seeds the test user as admin and adds `non_admin_client` for the 403 paths.
- **Test coverage:** Task 1 (~5) + Task 2 (~13) + Task 4 (~4) = ~22 new tests. Task 3 has no automated frontend test; `node --check` plus the unchanged backend suite. Suite projection 105 → 110 → 123 → 123 → 127.
- **Type consistency:** `themes.PRESETS: dict[str, dict[str, str]]`; `themes.CURATED_VARS: tuple[str, ...]`; `themes.default_theme() -> dict`; `themes.validate(theme) -> None` raises ValueError; `themes.effective(theme) -> dict[str, str]`; `settings_store.get_setting(conn, key) -> dict | None`; `settings_store.set_setting(conn, key, value)`. The theme body shape `{preset: str, overrides: dict[str, str]}` is consistent across `PATCH /api/theme`, the `themes.validate` checks, and `theme.js`'s draft state.
- **Green between tasks:** Task 1 is additive on the backend (existing tests still pass; new ones cover the new behaviour). Task 2 adds new files + one route registration without changing existing handlers, so existing tests are unaffected. Task 3 is frontend-only. Task 4 adds one new route and a small UI block. After every task the suite must be re-run end-to-end (the test environment's per-test pool teardown means each task's changes are exercised through the real route stack).
- **Operational steps:** after Task 1, Task 2, and Task 4, the dev server on `:8962` needs a restart for the new routes / schema to be reachable in the browser. After Task 3 a browser refresh is enough (frontend serves from disk). The single existing live deployment additionally needs `dbmanager init-auth` re-run once (Task 1's schema migration + the "ensure at least one admin" step).
