# Multi-User Login & Audit Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-password login with per-user accounts (email + bcrypt password) stored in the `common_data` database, plus an auth-event audit log, forced first-login password change, account lockout, and an in-app Users page.

**Architecture:** New auth tables (`users`, `user_sessions`) live in `common_data`. A thin custom auth layer (`passwords.py`, `authdb.py`, `auth.py`) sits on the app's existing signed-cookie sessions. Auth HTTP routes move to `routes/session.py`; user management to `routes/users.py`. Tests run against a throwaway database, never the real `common_data`.

**Tech Stack:** FastAPI, psycopg 3, `bcrypt`, vanilla-JS ES modules, pytest + pytest-postgresql.

**Spec:** `docs/superpowers/specs/2026-05-21-multi-user-auth-design.md`

**Branch:** all work on `feature/multi-user-auth` (Task 1 Step 1 creates it).

---

## Task 1: Settings change + password hashing

**Files:**
- Modify: `pyproject.toml`, `src/dbmanager/config.py`
- Create: `src/dbmanager/passwords.py`, `tests/test_passwords.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Create the branch**

```bash
cd s:/Development_2026/ia4service/database_manager
git checkout -b feature/multi-user-auth
```

- [ ] **Step 2: Add the `bcrypt` dependency to `pyproject.toml`**

In the `[project]` `dependencies` list, add `"bcrypt>=4.0"`. The list becomes:

```toml
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "psycopg[binary]>=3.2",
    "python-dotenv>=1.0",
    "itsdangerous>=2.0",
    "click>=8.1",
    "bcrypt>=4.0",
]
```

Then run: `pip install -e ".[dev]"`
Expected: installs `bcrypt`.

- [ ] **Step 3: Replace `tests/test_config.py` entirely**

```python
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
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `Settings` has no `common_data_url`.

- [ ] **Step 5: Replace `src/dbmanager/config.py` entirely**

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
    common_data_url: str
    app_secret: str

    @classmethod
    def from_env(cls) -> "Settings":
        db = os.environ.get("DATABASE_URL")
        if not db:
            raise RuntimeError("DATABASE_URL is required in environment or .env")
        common = os.environ.get("DATABASE_COMMON_DATA_URL")
        if not common:
            raise RuntimeError(
                "DATABASE_COMMON_DATA_URL is required in environment or .env")
        secret = os.environ.get("APP_SECRET")
        if not secret:
            raise RuntimeError("APP_SECRET is required in environment or .env")
        return cls(database_url=db, common_data_url=common, app_secret=secret)
```

- [ ] **Step 6: Write `tests/test_passwords.py`**

```python
from dbmanager.passwords import hash_password, verify_password


def test_hash_then_verify_succeeds():
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("hunter2")
    assert verify_password("wrong", h) is False


def test_hash_is_not_plaintext():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert len(h) > 20


def test_verify_handles_garbage_hash():
    assert verify_password("anything", "not-a-real-hash") is False
```

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest tests/test_passwords.py -v`
Expected: FAIL — no module `dbmanager.passwords`.

- [ ] **Step 8: Write `src/dbmanager/passwords.py`**

```python
"""Password hashing with bcrypt."""
from __future__ import annotations
import bcrypt


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the plaintext password."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if the plaintext matches the bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_config.py tests/test_passwords.py -v`
Expected: PASS (6 tests). Then `pytest -q` — the full suite still passes (the running app doesn't read `app_password`; `webapp.py` uses `app_secret`).

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml src/dbmanager/config.py src/dbmanager/passwords.py tests/test_config.py tests/test_passwords.py
git commit -m "feat: bcrypt passwords and common_data_url setting"
```

---

## Task 2: Auth data layer (`authdb.py`) + schema

**Files:**
- Create: `src/dbmanager/authdb.py`, `tests/test_authdb.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add a `common_data_url` fixture to `tests/conftest.py`**

The current `conftest.py` ends with the `server_url` fixture. Add this fixture
after it:

```python


@pytest.fixture
def common_data_url(postgresql):
    """A throwaway database with the auth schema applied and a seeded test
    user (test@example.com / test-password, no forced change)."""
    info = postgresql.info
    url = (f"postgresql://{info.user}:{info.password or ''}"
           f"@{info.host}:{info.port}/{info.dbname}")
    from dbmanager.authdb import apply_schema
    from dbmanager.passwords import hash_password
    apply_schema(url)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO users (email, password_hash, must_change_password) "
            "VALUES (%s, %s, false) ON CONFLICT (email) DO NOTHING",
            ("test@example.com", hash_password("test-password")))
    return url
```

Also ensure `conftest.py` imports `psycopg` at the top (alongside the existing
imports): add `import psycopg` if it is not already there.

- [ ] **Step 2: Write `tests/test_authdb.py`**

```python
import psycopg
from dbmanager import authdb
from dbmanager.passwords import hash_password


def test_create_and_get_user(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        created = authdb.create_user(conn, "ALICE@x.com", hash_password("pw"))
        assert created["email"] == "alice@x.com"          # lowercased
        assert created["must_change_password"] is True
        fetched = authdb.get_user_by_email(conn, "alice@x.com")
        assert fetched["id"] == created["id"]
        assert authdb.get_user_by_id(conn, created["id"])["email"] == "alice@x.com"


def test_get_missing_user_returns_none(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        assert authdb.get_user_by_email(conn, "nobody@x.com") is None


def test_record_event_appends_row(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        authdb.record_event(conn, email="a@x.com", user_id=None,
                            event="login_failed", ip_address="1.2.3.4",
                            user_agent="pytest")
    with psycopg.connect(common_data_url) as conn:
        row = conn.execute(
            "SELECT event, ip_address FROM user_sessions WHERE email=%s",
            ("a@x.com",)).fetchone()
    assert row == ("login_failed", "1.2.3.4")


def test_note_failed_attempt_locks_at_threshold(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.create_user(conn, "lock@x.com", hash_password("pw"))
        locked = False
        for _ in range(5):
            locked = authdb.note_failed_attempt(conn, user["id"], 5, 15)
        assert locked is True
        refetched = authdb.get_user_by_id(conn, user["id"])
        assert refetched["locked_until"] is not None


def test_note_successful_login_resets_attempts(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.create_user(conn, "ok@x.com", hash_password("pw"))
        authdb.note_failed_attempt(conn, user["id"], 5, 15)
        authdb.note_successful_login(conn, user["id"])
        refetched = authdb.get_user_by_id(conn, user["id"])
        assert refetched["failed_attempts"] == 0
        assert refetched["last_login_at"] is not None


def test_set_password_clears_must_change_and_lock(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.create_user(conn, "sp@x.com", hash_password("old"))
        authdb.set_password(conn, user["id"], hash_password("new"),
                            must_change=False)
        refetched = authdb.get_user_by_id(conn, user["id"])
        assert refetched["must_change_password"] is False


def test_list_users_excludes_password_hash(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        authdb.create_user(conn, "lu@x.com", hash_password("pw"))
        rows = authdb.list_users(conn)
    assert all("password_hash" not in r for r in rows)
    assert any(r["email"] == "lu@x.com" for r in rows)


def test_update_user_deactivates_and_unlocks(common_data_url):
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.create_user(conn, "uu@x.com", hash_password("pw"))
        authdb.note_failed_attempt(conn, user["id"], 5, 15)
        updated = authdb.update_user(conn, user["id"], is_active=False,
                                     unlock=True)
        assert updated["is_active"] is False
        assert updated["failed_attempts"] == 0
        assert updated["locked_until"] is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_authdb.py -v`
Expected: FAIL — no module `dbmanager.authdb`.

- [ ] **Step 4: Write `src/dbmanager/authdb.py`**

```python
"""Auth data layer — schema and queries for the users / user_sessions tables
in the common_data database. Connections are autocommit so audit-log writes
and failed-attempt counters persist even when the caller then raises."""
from __future__ import annotations
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row

AUTH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id                   serial PRIMARY KEY,
    email                text UNIQUE NOT NULL,
    password_hash        text NOT NULL,
    must_change_password boolean NOT NULL DEFAULT true,
    is_active            boolean NOT NULL DEFAULT true,
    failed_attempts      integer NOT NULL DEFAULT 0,
    locked_until         timestamptz,
    last_login_at        timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

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


@contextmanager
def auth_conn(common_data_url: str):
    """Yield an autocommit connection to the common_data database."""
    conn = psycopg.connect(common_data_url, row_factory=dict_row,
                           autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def apply_schema(common_data_url: str) -> None:
    """Create the auth tables if they do not already exist."""
    with auth_conn(common_data_url) as conn:
        conn.execute(AUTH_SCHEMA_SQL)


def get_user_by_email(conn, email: str) -> dict | None:
    return conn.execute(
        "SELECT * FROM users WHERE email = %s", (email.strip().lower(),)
    ).fetchone()


def get_user_by_id(conn, user_id: int) -> dict | None:
    return conn.execute(
        "SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


def create_user(conn, email: str, password_hash: str,
                must_change: bool = True) -> dict:
    return conn.execute("""
        INSERT INTO users (email, password_hash, must_change_password)
        VALUES (%s, %s, %s) RETURNING *
    """, (email.strip().lower(), password_hash, must_change)).fetchone()


def set_password(conn, user_id: int, password_hash: str,
                 must_change: bool) -> None:
    conn.execute("""
        UPDATE users SET password_hash = %s, must_change_password = %s,
            failed_attempts = 0, locked_until = NULL, updated_at = now()
        WHERE id = %s
    """, (password_hash, must_change, user_id))


def record_event(conn, *, email: str, user_id: int | None, event: str,
                 ip_address: str | None, user_agent: str | None) -> None:
    conn.execute("""
        INSERT INTO user_sessions (user_id, email, event, ip_address, user_agent)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, email.strip().lower(), event, ip_address, user_agent))


def note_successful_login(conn, user_id: int) -> None:
    conn.execute("""
        UPDATE users SET failed_attempts = 0, locked_until = NULL,
            last_login_at = now(), updated_at = now()
        WHERE id = %s
    """, (user_id,))


def note_failed_attempt(conn, user_id: int, max_attempts: int,
                        lock_minutes: int) -> bool:
    """Increment failed attempts; lock the account when the threshold is
    reached. Returns True if the account is now locked."""
    row = conn.execute("""
        UPDATE users SET failed_attempts = failed_attempts + 1,
            updated_at = now()
        WHERE id = %s RETURNING failed_attempts
    """, (user_id,)).fetchone()
    if row["failed_attempts"] >= max_attempts:
        conn.execute("""
            UPDATE users SET locked_until = now() + make_interval(mins => %s)
            WHERE id = %s
        """, (lock_minutes, user_id))
        return True
    return False


def list_users(conn) -> list[dict]:
    return conn.execute("""
        SELECT id, email, must_change_password, is_active, failed_attempts,
               locked_until, last_login_at, created_at
        FROM users ORDER BY email
    """).fetchall()


def update_user(conn, user_id: int, *, is_active: bool | None = None,
                unlock: bool = False) -> dict | None:
    """Set the active flag and/or clear the lock. Returns the updated row."""
    sets = []
    params: list = []
    if is_active is not None:
        sets.append("is_active = %s")
        params.append(is_active)
    if unlock:
        sets.append("failed_attempts = 0")
        sets.append("locked_until = NULL")
    if not sets:
        return get_user_by_id(conn, user_id)
    sets.append("updated_at = now()")
    params.append(user_id)
    return conn.execute(
        f"UPDATE users SET {', '.join(sets)} WHERE id = %s RETURNING *",
        params).fetchone()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_authdb.py -v`
Expected: PASS (8 tests). Then `pytest -q` — full suite still passes.

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/authdb.py tests/test_authdb.py tests/conftest.py
git commit -m "feat: auth data layer and schema"
```

---

## Task 3: Auth logic (`authenticate`, `change_password`)

**Files:**
- Modify: `src/dbmanager/auth.py`
- Create: `tests/test_authenticate.py`

This task ADDS new functions to `auth.py`. It leaves the existing
`password_matches` and `require_session` untouched — they are still used by
the old login and are removed in Task 5.

- [ ] **Step 1: Write `tests/test_authenticate.py`**

```python
import pytest
from fastapi import HTTPException
from dbmanager import auth, authdb
from dbmanager.passwords import hash_password


def _make_user(common_data_url, email, password, **cols):
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.create_user(conn, email, hash_password(password))
        if cols:
            sets = ", ".join(f"{k} = %s" for k in cols)
            conn.execute(f"UPDATE users SET {sets} WHERE id = %s",
                         [*cols.values(), user["id"]])
        return user["id"]


def test_authenticate_success(common_data_url):
    _make_user(common_data_url, "u@x.com", "Password1")
    result = auth.authenticate(common_data_url, "U@x.com", "Password1",
                               "1.1.1.1", "pytest")
    assert result.email == "u@x.com"
    assert result.must_change_password is True


def test_authenticate_wrong_password(common_data_url):
    _make_user(common_data_url, "u@x.com", "Password1")
    with pytest.raises(HTTPException) as exc:
        auth.authenticate(common_data_url, "u@x.com", "wrong", None, None)
    assert exc.value.status_code == 401


def test_authenticate_unknown_email(common_data_url):
    with pytest.raises(HTTPException) as exc:
        auth.authenticate(common_data_url, "ghost@x.com", "x", None, None)
    assert exc.value.status_code == 401


def test_authenticate_inactive_account(common_data_url):
    _make_user(common_data_url, "off@x.com", "Password1", is_active=False)
    with pytest.raises(HTTPException) as exc:
        auth.authenticate(common_data_url, "off@x.com", "Password1", None, None)
    assert exc.value.status_code == 403


def test_authenticate_locks_after_five_failures(common_data_url):
    _make_user(common_data_url, "brute@x.com", "Password1")
    for _ in range(5):
        with pytest.raises(HTTPException):
            auth.authenticate(common_data_url, "brute@x.com", "wrong", None, None)
    # Even the correct password is now refused with a lock message.
    with pytest.raises(HTTPException) as exc:
        auth.authenticate(common_data_url, "brute@x.com", "Password1", None, None)
    assert exc.value.status_code == 403
    assert "lock" in exc.value.detail.lower()


def test_change_password_success(common_data_url):
    uid = _make_user(common_data_url, "cp@x.com", "OldPass1")
    auth.change_password(common_data_url, uid, "OldPass1", "NewPass123",
                         None, None)
    result = auth.authenticate(common_data_url, "cp@x.com", "NewPass123",
                               None, None)
    assert result.must_change_password is False


def test_change_password_wrong_current(common_data_url):
    uid = _make_user(common_data_url, "cp@x.com", "OldPass1")
    with pytest.raises(HTTPException) as exc:
        auth.change_password(common_data_url, uid, "WRONG", "NewPass123",
                             None, None)
    assert exc.value.status_code == 400


def test_change_password_too_short(common_data_url):
    uid = _make_user(common_data_url, "cp@x.com", "OldPass1")
    with pytest.raises(HTTPException) as exc:
        auth.change_password(common_data_url, uid, "OldPass1", "short",
                             None, None)
    assert exc.value.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_authenticate.py -v`
Expected: FAIL — `auth` has no attribute `authenticate`.

- [ ] **Step 3: Append the new functions to `src/dbmanager/auth.py`**

Keep the existing file content. Add these imports to the top (the file
currently imports `hmac` and `from fastapi import HTTPException, Request`):

```python
from dataclasses import dataclass
from datetime import datetime, timezone

from dbmanager import authdb
from dbmanager.passwords import hash_password, verify_password
```

Then append at the end of the file:

```python


MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
MIN_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class AuthResult:
    user_id: int
    email: str
    must_change_password: bool


def _is_locked(user: dict) -> bool:
    until = user.get("locked_until")
    return until is not None and until > datetime.now(timezone.utc)


def authenticate(common_data_url: str, email: str, password: str,
                 ip: str | None, user_agent: str | None) -> AuthResult:
    """Verify email + password against common_data. Raises HTTPException on
    any failure and records every attempt in the audit log."""
    email = (email or "").strip().lower()
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.get_user_by_email(conn, email)
        if user is None:
            authdb.record_event(conn, email=email, user_id=None,
                                event="login_failed", ip_address=ip,
                                user_agent=user_agent)
            raise HTTPException(401, "incorrect email or password")
        if not user["is_active"]:
            authdb.record_event(conn, email=email, user_id=user["id"],
                                event="login_failed", ip_address=ip,
                                user_agent=user_agent)
            raise HTTPException(403, "this account is deactivated")
        if _is_locked(user):
            authdb.record_event(conn, email=email, user_id=user["id"],
                                event="login_failed", ip_address=ip,
                                user_agent=user_agent)
            raise HTTPException(
                403, "account temporarily locked — try again later")
        if not verify_password(password, user["password_hash"]):
            locked = authdb.note_failed_attempt(
                conn, user["id"], MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES)
            authdb.record_event(conn, email=email, user_id=user["id"],
                                event="login_failed", ip_address=ip,
                                user_agent=user_agent)
            if locked:
                authdb.record_event(conn, email=email, user_id=user["id"],
                                    event="account_locked", ip_address=ip,
                                    user_agent=user_agent)
            raise HTTPException(401, "incorrect email or password")
        authdb.note_successful_login(conn, user["id"])
        authdb.record_event(conn, email=email, user_id=user["id"],
                            event="login_success", ip_address=ip,
                            user_agent=user_agent)
        return AuthResult(user_id=user["id"], email=user["email"],
                          must_change_password=user["must_change_password"])


def change_password(common_data_url: str, user_id: int, current: str,
                    new: str, ip: str | None, user_agent: str | None) -> None:
    """Change the logged-in user's password. Raises HTTPException on failure."""
    if len(new) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            400,
            f"new password must be at least {MIN_PASSWORD_LENGTH} characters")
    if new == current:
        raise HTTPException(400, "new password must differ from the current one")
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.get_user_by_id(conn, user_id)
        if user is None:
            raise HTTPException(404, "user not found")
        if not verify_password(current, user["password_hash"]):
            raise HTTPException(400, "current password is incorrect")
        authdb.set_password(conn, user_id, hash_password(new),
                            must_change=False)
        authdb.record_event(conn, email=user["email"], user_id=user_id,
                            event="password_changed", ip_address=ip,
                            user_agent=user_agent)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_authenticate.py -v`
Expected: PASS (8 tests). Then `pytest -q` — full suite still passes (the
existing `password_matches`/`require_session` are unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/dbmanager/auth.py tests/test_authenticate.py
git commit -m "feat: authenticate and change-password logic"
```

---

## Task 4: `init-auth` CLI command

**Files:**
- Modify: `src/dbmanager/cli.py`
- Create: `tests/test_init_auth.py`

- [ ] **Step 1: Write `tests/test_init_auth.py`**

```python
import psycopg
from click.testing import CliRunner
from dbmanager.cli import cli


def test_init_auth_creates_user(common_data_url, monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    result = CliRunner().invoke(cli, ["init-auth", "--email",
                                      "new@example.com", "--password",
                                      "TempPass123"])
    assert result.exit_code == 0, result.output
    with psycopg.connect(common_data_url) as conn:
        row = conn.execute(
            "SELECT must_change_password FROM users WHERE email = %s",
            ("new@example.com",)).fetchone()
    assert row is not None
    assert row[0] is True


def test_init_auth_is_idempotent(common_data_url, monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    runner = CliRunner()
    runner.invoke(cli, ["init-auth", "--email", "dup@example.com",
                        "--password", "TempPass123"])
    result = runner.invoke(cli, ["init-auth", "--email", "dup@example.com",
                                 "--password", "TempPass123"])
    assert result.exit_code == 0
    assert "already exists" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_init_auth.py -v`
Expected: FAIL — no `init-auth` command.

- [ ] **Step 3: Add the command to `src/dbmanager/cli.py`**

The file currently ends with the `web` command. Append:

```python


@cli.command("init-auth")
@click.option("--email", required=True, help="Email of the first user.")
@click.option("--password", required=True, help="Temporary password.")
def init_auth(email: str, password: str) -> None:
    """Create the auth tables in common_data and seed the first user."""
    from dbmanager import authdb
    from dbmanager.config import Settings
    from dbmanager.passwords import hash_password

    settings = Settings.from_env()
    authdb.apply_schema(settings.common_data_url)
    with authdb.auth_conn(settings.common_data_url) as conn:
        if authdb.get_user_by_email(conn, email) is not None:
            click.echo(f"user {email} already exists — tables ensured, "
                       f"no change made")
            return
        authdb.create_user(conn, email, hash_password(password),
                           must_change=True)
    click.echo(f"created user {email} — must change password on first login")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_init_auth.py -v`
Expected: PASS (2 tests). Then `pytest -q` — full suite still passes.

- [ ] **Step 5: Commit**

```bash
git add src/dbmanager/cli.py tests/test_init_auth.py
git commit -m "feat: init-auth CLI command"
```

---

## Task 5: Switch to email/password login (session routes + webapp + fixtures)

This is the atomic cutover: it replaces the single-password login everywhere
at once so the suite stays green. It creates `routes/session.py`, rewrites
`webapp.py`, updates `auth.py` (`require_session` now checks `user_id`;
`password_matches` removed), moves the shared `client` test fixture into
`conftest.py`, removes the per-file `client` fixtures, rewrites
`tests/test_webapp.py`, updates `tests/test_auth.py`, and adds
`tests/test_session.py`.

**Files:**
- Create: `src/dbmanager/routes/session.py`, `tests/test_session.py`
- Modify: `src/dbmanager/webapp.py`, `src/dbmanager/auth.py`,
  `tests/conftest.py`, `tests/test_auth.py`, `tests/test_webapp.py`,
  `tests/test_databases.py`, `tests/test_tables.py`, `tests/test_rows.py`,
  `tests/test_query.py`

- [ ] **Step 1: Write `src/dbmanager/routes/session.py`**

```python
"""Session routes — login, logout, current user, password change."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from dbmanager import auth, authdb
from dbmanager.config import Settings

router = APIRouter(prefix="/api", tags=["session"])


class LoginBody(BaseModel):
    email: str
    password: str


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


def _client(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


@router.post("/login")
def login(body: LoginBody, request: Request) -> dict:
    """Authenticate with email + password and start a session."""
    settings = Settings.from_env()
    ip, ua = _client(request)
    result = auth.authenticate(settings.common_data_url, body.email,
                               body.password, ip, ua)
    request.session["user_id"] = result.user_id
    request.session["email"] = result.email
    return {"ok": True, "must_change_password": result.must_change_password}


@router.post("/logout")
def logout(request: Request) -> dict:
    """End the session."""
    request.session.clear()
    return {"ok": True}


@router.get("/me", dependencies=[Depends(auth.require_session)])
def me(request: Request) -> dict:
    """The current user and whether a password change is still required."""
    settings = Settings.from_env()
    with authdb.auth_conn(settings.common_data_url) as conn:
        user = authdb.get_user_by_id(conn, request.session["user_id"])
    if user is None:
        request.session.clear()
        raise HTTPException(401, "authentication required")
    return {"email": user["email"],
            "must_change_password": user["must_change_password"]}


@router.post("/change-password",
             dependencies=[Depends(auth.require_session)])
def change_password(body: ChangePasswordBody, request: Request) -> dict:
    """Change the current user's password."""
    settings = Settings.from_env()
    ip, ua = _client(request)
    auth.change_password(settings.common_data_url, request.session["user_id"],
                         body.current_password, body.new_password, ip, ua)
    return {"ok": True}
```

- [ ] **Step 2: Update `src/dbmanager/auth.py`**

Two changes to the EXISTING top portion of the file:

(a) Remove the now-unused single-password helper. Delete the `import hmac`
line and delete the entire `password_matches` function:

```python
def password_matches(supplied: str, expected: str) -> bool:
    """Constant-time comparison of the supplied login password."""
    return hmac.compare_digest(supplied, expected)
```

(b) Change `require_session` to check the new session key. It currently is:

```python
def require_session(request: Request) -> None:
    """FastAPI dependency: reject requests without an authenticated session."""
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="authentication required")
```

Replace its body so it reads:

```python
def require_session(request: Request) -> None:
    """FastAPI dependency: reject requests without a logged-in session."""
    if not request.session.get("user_id"):
        raise HTTPException(status_code=401, detail="authentication required")
```

Leave the Task 3 additions (`authenticate`, `change_password`, etc.) intact.

- [ ] **Step 3: Replace `src/dbmanager/webapp.py` entirely**

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
from dbmanager.config import Settings
from dbmanager.routes import databases, query, rows, session, tables

WEB_DIR = Path(__file__).resolve().parent / "web"
_settings = Settings.from_env()

app = FastAPI(title="Database Manager", docs_url="/api/docs", redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=_settings.app_secret,
                   https_only=False)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the single-page app shell."""
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/server-info", dependencies=[Depends(require_session)])
def server_info() -> dict:
    """Host and port of the configured Postgres server — no credentials."""
    info = conninfo_to_dict(Settings.from_env().database_url)
    return {"host": info.get("host") or "", "port": info.get("port") or ""}


# session router self-guards /me and /change-password; login/logout are open.
app.include_router(session.router)
app.include_router(databases.router, dependencies=[Depends(require_session)])
app.include_router(tables.router, dependencies=[Depends(require_session)])
app.include_router(rows.router, dependencies=[Depends(require_session)])
app.include_router(query.router, dependencies=[Depends(require_session)])
```

- [ ] **Step 4: Add a shared `client` fixture to `tests/conftest.py`**

Append after the `common_data_url` fixture:

```python


@pytest.fixture
def client(server_url, common_data_url, monkeypatch):
    """A TestClient logged in as the seeded test user."""
    from fastapi.testclient import TestClient
    monkeypatch.setenv("DATABASE_URL", server_url)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    from dbmanager.webapp import app
    c = TestClient(app)
    resp = c.post("/api/login", json={"email": "test@example.com",
                                      "password": "test-password"})
    assert resp.status_code == 200, resp.text
    return c
```

- [ ] **Step 5: Remove the per-file `client` fixture from the four route test files**

In each of `tests/test_databases.py`, `tests/test_tables.py`,
`tests/test_rows.py`, `tests/test_query.py`, DELETE the local `client`
fixture (the block `@pytest.fixture` / `def client(server_url, monkeypatch):`
... `return c`). The shared one in `conftest.py` replaces it. Leave every
other fixture (e.g. `db`) and every test in those files unchanged — they
depend on `client` by name and now resolve to the conftest fixture.

In `tests/test_databases.py`, the `test_requires_auth` test builds its own
`TestClient`. Replace that test with:

```python
def test_requires_auth(server_url, common_data_url, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("DATABASE_URL", server_url)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    from dbmanager.webapp import app
    resp = TestClient(app).get("/api/databases")
    assert resp.status_code == 401
```

- [ ] **Step 6: Replace `tests/test_webapp.py` entirely**

```python
from fastapi.testclient import TestClient


def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Database Manager" in resp.text


def test_server_info_returns_host_port(client):
    resp = client.get("/api/server-info")
    assert resp.status_code == 200
    data = resp.json()
    assert "host" in data and "port" in data


def test_server_info_requires_auth(server_url, common_data_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", server_url)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    from dbmanager.webapp import app
    resp = TestClient(app).get("/api/server-info")
    assert resp.status_code == 401
```

- [ ] **Step 7: Update `tests/test_auth.py`**

`test_auth.py` currently tests `password_matches` (removed) and the old
`require_session`. Replace the ENTIRE file with:

```python
import pytest
from fastapi import HTTPException
from dbmanager.auth import require_session


class FakeRequest:
    def __init__(self, session):
        self.session = session


def test_require_session_allows_logged_in():
    require_session(FakeRequest({"user_id": 1}))  # no raise


def test_require_session_rejects_anonymous():
    with pytest.raises(HTTPException) as exc:
        require_session(FakeRequest({}))
    assert exc.value.status_code == 401
```

- [ ] **Step 8: Write `tests/test_session.py`**

```python
import pytest
from fastapi.testclient import TestClient
from dbmanager import authdb
from dbmanager.passwords import hash_password


@pytest.fixture
def app_client(server_url, common_data_url, monkeypatch):
    """A bare (not logged-in) TestClient wired to the test databases."""
    monkeypatch.setenv("DATABASE_URL", server_url)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    from dbmanager.webapp import app
    return TestClient(app)


def test_login_success(app_client):
    resp = app_client.post("/api/login", json={"email": "test@example.com",
                                               "password": "test-password"})
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is False


def test_login_wrong_password(app_client):
    resp = app_client.post("/api/login", json={"email": "test@example.com",
                                               "password": "nope"})
    assert resp.status_code == 401


def test_login_unknown_email(app_client):
    resp = app_client.post("/api/login", json={"email": "ghost@example.com",
                                               "password": "x"})
    assert resp.status_code == 401


def test_login_reports_must_change(common_data_url, app_client):
    with authdb.auth_conn(common_data_url) as conn:
        authdb.create_user(conn, "fresh@example.com", hash_password("TempPass1"))
    resp = app_client.post("/api/login", json={"email": "fresh@example.com",
                                               "password": "TempPass1"})
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is True


def test_me_requires_auth(app_client):
    assert app_client.get("/api/me").status_code == 401


def test_me_after_login(app_client):
    app_client.post("/api/login", json={"email": "test@example.com",
                                        "password": "test-password"})
    resp = app_client.get("/api/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@example.com"


def test_change_password_flow(common_data_url, app_client):
    with authdb.auth_conn(common_data_url) as conn:
        authdb.create_user(conn, "chg@example.com", hash_password("TempPass1"))
    app_client.post("/api/login", json={"email": "chg@example.com",
                                        "password": "TempPass1"})
    resp = app_client.post("/api/change-password", json={
        "current_password": "TempPass1", "new_password": "BrandNew123"})
    assert resp.status_code == 200
    fresh = TestClient(app_client.app)
    ok = fresh.post("/api/login", json={"email": "chg@example.com",
                                        "password": "BrandNew123"})
    assert ok.status_code == 200
    assert ok.json()["must_change_password"] is False


def test_logout_clears_session(app_client):
    app_client.post("/api/login", json={"email": "test@example.com",
                                        "password": "test-password"})
    assert app_client.post("/api/logout").status_code == 200
    assert app_client.get("/api/me").status_code == 401
```

- [ ] **Step 9: Run the full suite**

Run: `pytest -q`
Expected: PASS — every test, including the updated route-test files,
`test_session.py`, `test_authenticate.py`, `test_authdb.py`. If a route test
fails because its `client` fixture was not removed (a duplicate-fixture
error) or `test_requires_auth` was missed, fix that file per Step 5.

- [ ] **Step 10: Commit**

```bash
git add src/dbmanager/routes/session.py src/dbmanager/webapp.py src/dbmanager/auth.py tests/
git commit -m "feat: switch to per-user email/password login"
```

---

## Task 6: User management routes

**Files:**
- Create: `src/dbmanager/routes/users.py`, `tests/test_users.py`
- Modify: `src/dbmanager/webapp.py`

- [ ] **Step 1: Write `tests/test_users.py`**

```python
def test_list_users_includes_seed(client):
    resp = client.get("/api/users")
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert "test@example.com" in emails
    assert all("password_hash" not in u for u in resp.json())


def test_create_user(client):
    resp = client.post("/api/users", json={"email": "new@example.com",
                                           "password": "TempPass123"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new@example.com"
    assert body["must_change_password"] is True
    assert "password_hash" not in body


def test_create_duplicate_user_conflicts(client):
    client.post("/api/users", json={"email": "dup@example.com",
                                    "password": "TempPass123"})
    resp = client.post("/api/users", json={"email": "dup@example.com",
                                           "password": "TempPass123"})
    assert resp.status_code == 409


def test_create_user_short_password(client):
    resp = client.post("/api/users", json={"email": "x@example.com",
                                           "password": "short"})
    assert resp.status_code == 400


def test_deactivate_and_reactivate_user(client):
    created = client.post("/api/users", json={"email": "tog@example.com",
                                              "password": "TempPass123"}).json()
    off = client.patch(f"/api/users/{created['id']}", json={"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False
    on = client.patch(f"/api/users/{created['id']}", json={"is_active": True})
    assert on.json()["is_active"] is True


def test_reset_password_sets_must_change(client):
    created = client.post("/api/users", json={"email": "rst@example.com",
                                              "password": "TempPass123"}).json()
    resp = client.patch(f"/api/users/{created['id']}",
                        json={"password": "ResetPass123"})
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is True


def test_patch_missing_user_404(client):
    resp = client.patch("/api/users/999999", json={"is_active": False})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_users.py -v`
Expected: FAIL — 404 on `/api/users` (router not registered).

- [ ] **Step 3: Write `src/dbmanager/routes/users.py`**

```python
"""User management routes."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager import authdb
from dbmanager.config import Settings
from dbmanager.passwords import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])

MIN_PASSWORD_LENGTH = 8


class CreateUserBody(BaseModel):
    email: str
    password: str


class UpdateUserBody(BaseModel):
    is_active: bool | None = None
    password: str | None = None
    unlock: bool = False


def _public(user: dict) -> dict:
    """A user row with the password hash stripped out."""
    return {k: v for k, v in user.items() if k != "password_hash"}


@router.get("")
def get_users() -> list[dict]:
    settings = Settings.from_env()
    with authdb.auth_conn(settings.common_data_url) as conn:
        return authdb.list_users(conn)


@router.post("", status_code=201)
def create_user(body: CreateUserBody) -> dict:
    email = body.email.strip().lower()
    if not email:
        raise HTTPException(400, "email is required")
    if len(body.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            400, f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    settings = Settings.from_env()
    with authdb.auth_conn(settings.common_data_url) as conn:
        try:
            user = authdb.create_user(conn, email, hash_password(body.password),
                                      must_change=True)
        except pgerrors.UniqueViolation as exc:
            raise HTTPException(
                409, f"a user with email '{email}' already exists") from exc
    return _public(user)


@router.patch("/{user_id}")
def update_user(user_id: int, body: UpdateUserBody) -> dict:
    settings = Settings.from_env()
    with authdb.auth_conn(settings.common_data_url) as conn:
        if authdb.get_user_by_id(conn, user_id) is None:
            raise HTTPException(404, f"no user with id {user_id}")
        if body.password is not None:
            if len(body.password) < MIN_PASSWORD_LENGTH:
                raise HTTPException(
                    400,
                    f"password must be at least {MIN_PASSWORD_LENGTH} characters")
            authdb.set_password(conn, user_id, hash_password(body.password),
                                must_change=True)
        if body.is_active is not None or body.unlock:
            authdb.update_user(conn, user_id, is_active=body.is_active,
                               unlock=body.unlock)
        user = authdb.get_user_by_id(conn, user_id)
    return _public(user)
```

- [ ] **Step 4: Register the router in `src/dbmanager/webapp.py`**

Add `users` to the routes import line so it reads:

```python
from dbmanager.routes import databases, query, rows, session, tables, users
```

Then add this line after `app.include_router(session.router)`:

```python
app.include_router(users.router, dependencies=[Depends(require_session)])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_users.py -v`
Expected: PASS (7 tests). Then `pytest -q` — full suite passes.

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/routes/users.py src/dbmanager/webapp.py tests/test_users.py
git commit -m "feat: user management routes"
```

---

## Task 7: Login + change-password frontend

**Files:**
- Modify: `src/dbmanager/web/index.html`, `src/dbmanager/web/app.js`

No automated frontend test — verify the files are served and the backend
suite still passes.

- [ ] **Step 1: Replace `src/dbmanager/web/index.html` entirely**

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
      <input id="login-email" type="email" placeholder="Email" autocomplete="username" required>
      <input id="login-password" type="password" placeholder="Password" autocomplete="current-password" required>
      <button type="submit">Log in</button>
      <p id="login-error" class="error"></p>
    </form>
  </div>

  <div id="change-password" class="login hidden">
    <form id="change-password-form" class="login-card">
      <h1>Set a new password</h1>
      <p class="notice">You must change your password before continuing.</p>
      <input id="cp-current" type="password" placeholder="Current password" autocomplete="current-password" required>
      <input id="cp-new" type="password" placeholder="New password (min 8 characters)" autocomplete="new-password" required>
      <input id="cp-confirm" type="password" placeholder="Confirm new password" autocomplete="new-password" required>
      <button type="submit">Change password</button>
      <p id="cp-error" class="error"></p>
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

- [ ] **Step 2: Replace the auth/boot section of `src/dbmanager/web/app.js`**

In `app.js`, replace everything from the line
`// --- auth / boot ------------------------------------------------------------`
to the end of the file with:

```js
// --- auth / boot ------------------------------------------------------------

const changePwEl = document.getElementById("change-password");

async function showApp() {
  loginEl.classList.add("hidden");
  changePwEl.classList.add("hidden");
  appEl.classList.remove("hidden");
  await loadSidebar();
  try {
    const info = await get("/api/server-info");
    document.getElementById("server-label").textContent =
      info.host ? `${info.host}:${info.port}` : "";
  } catch { /* label is cosmetic — ignore failures */ }
}
function showLogin() {
  appEl.classList.add("hidden");
  changePwEl.classList.add("hidden");
  loginEl.classList.remove("hidden");
}
function showChangePassword() {
  appEl.classList.add("hidden");
  loginEl.classList.add("hidden");
  changePwEl.classList.remove("hidden");
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("login-error");
  errEl.textContent = "";
  try {
    const r = await post("/api/login", {
      email: document.getElementById("login-email").value,
      password: document.getElementById("login-password").value,
    });
    if (r.must_change_password) showChangePassword();
    else await showApp();
  } catch (err) { errEl.textContent = err.message; }
});

document.getElementById("change-password-form")
  .addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("cp-error");
    errEl.textContent = "";
    const current = document.getElementById("cp-current").value;
    const next = document.getElementById("cp-new").value;
    const confirm = document.getElementById("cp-confirm").value;
    if (next !== confirm) {
      errEl.textContent = "new passwords do not match";
      return;
    }
    try {
      await post("/api/change-password",
        { current_password: current, new_password: next });
      await showApp();
    } catch (err) { errEl.textContent = err.message; }
  });

document.getElementById("logout").addEventListener("click", async () => {
  await post("/api/logout");
  showLogin();
});

(async function init() {
  try {
    const me = await get("/api/me");
    if (me.must_change_password) showChangePassword();
    else await showApp();
  } catch { showLogin(); }
})();
```

- [ ] **Step 3: Verify**

Confirm `GET /static/index.html` (or `/`) contains `id="login-email"` and
`id="change-password"`, and `GET /static/app.js` contains
`showChangePassword` and `/api/me`. Run `pytest -q` — backend suite passes.

- [ ] **Step 4: Commit**

```bash
git add src/dbmanager/web/index.html src/dbmanager/web/app.js
git commit -m "feat: email login and forced password-change screen"
```

---

## Task 8: Users management page

**Files:**
- Create: `src/dbmanager/web/users.js`
- Modify: `src/dbmanager/web/app.js`

- [ ] **Step 1: Create `src/dbmanager/web/users.js`**

```js
import { get, post, patch } from "./api.js";
import { formModal, showError } from "./app.js";

// Render the Users management panel.
export async function renderUsers() {
  const panel = document.getElementById("panel");
  panel.innerHTML = "";

  const h = document.createElement("h2");
  h.textContent = "Users";
  panel.append(h);

  const toolbar = document.createElement("div");
  toolbar.className = "toolbar";
  toolbar.append(mkBtn("+ User", addUserDialog, ""));
  panel.append(toolbar);

  const users = await get("/api/users");
  const table = document.createElement("table");
  table.className = "grid";
  table.innerHTML =
    "<thead><tr><th>Email</th><th>Status</th><th>Must change pw</th>" +
    "<th>Last login</th><th></th></tr></thead>";
  const body = document.createElement("tbody");
  for (const u of users) {
    const locked = u.locked_until && new Date(u.locked_until) > new Date();
    const status = !u.is_active ? "inactive" : locked ? "locked" : "active";
    const tr = document.createElement("tr");
    for (const text of [
      u.email, status, u.must_change_password ? "yes" : "no",
      u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "—",
    ]) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.append(td);
    }
    const actions = document.createElement("td");
    actions.append(
      mkBtn(u.is_active ? "Deactivate" : "Activate",
            () => setActive(u.id, !u.is_active), "ghost"),
      mkBtn("Reset password", () => resetPassword(u.id, u.email), "ghost"));
    if (locked) {
      actions.append(mkBtn("Unlock", () => unlockUser(u.id), "ghost"));
    }
    tr.append(actions);
    body.append(tr);
  }
  table.append(body);
  panel.append(table);
}

function mkBtn(text, onClick, cls) {
  const b = document.createElement("button");
  b.textContent = text;
  if (cls) b.className = cls;
  b.style.marginRight = "4px";
  b.onclick = onClick;
  return b;
}

async function addUserDialog() {
  const v = await formModal("Add user", [
    { name: "email", label: "Email", type: "text" },
    { name: "password", label: "Temp password", type: "text" },
  ]);
  if (!v) return;
  try {
    await post("/api/users", { email: v.email, password: v.password });
    await renderUsers();
  } catch (e) { showError(e.message); }
}

async function setActive(id, active) {
  try {
    await patch(`/api/users/${id}`, { is_active: active });
    await renderUsers();
  } catch (e) { showError(e.message); }
}

async function resetPassword(id, email) {
  const v = await formModal(`Reset password for ${email}`, [
    { name: "password", label: "New temp password", type: "text" },
  ]);
  if (!v) return;
  try {
    await patch(`/api/users/${id}`, { password: v.password });
    await renderUsers();
  } catch (e) { showError(e.message); }
}

async function unlockUser(id) {
  try {
    await patch(`/api/users/${id}`, { unlock: true });
    await renderUsers();
  } catch (e) { showError(e.message); }
}
```

- [ ] **Step 2: Wire the Users page into `src/dbmanager/web/app.js`**

Edit A — add the import. After the existing import line
`import { renderConsole as consoleView } from "./query.js";` add:

```js
import { renderUsers } from "./users.js";
```

Edit B — add a sidebar entry. In `loadSidebar`, the SQL Console item is built
by this block:

```js
  const consoleBtn = document.createElement("div");
  consoleBtn.className = "tree-item";
  consoleBtn.textContent = "▸ SQL Console";
  consoleBtn.onclick = () => openConsole();
  sidebar.append(consoleBtn);
```

Immediately after `sidebar.append(consoleBtn);`, add:

```js

  const usersBtn = document.createElement("div");
  usersBtn.className = "tree-item";
  usersBtn.textContent = "▸ Users";
  usersBtn.onclick = () => renderUsers();
  sidebar.append(usersBtn);
```

- [ ] **Step 3: Verify**

Confirm `GET /static/users.js` returns 200 and contains `renderUsers`, and
`GET /static/app.js` contains `import { renderUsers }` and `▸ Users`. Run
`pytest -q` — backend suite passes.

- [ ] **Step 4: Commit**

```bash
git add src/dbmanager/web/users.js src/dbmanager/web/app.js
git commit -m "feat: users management page"
```

---

# Self-Review Notes

- **Spec coverage:** schema (Task 2); bcrypt passwords + `common_data_url`
  config (Task 1); authenticate/lockout/change-password (Task 3); `init-auth`
  CLI (Task 4); login/logout/me/change-password routes + the login cutover
  (Task 5); users CRUD (Task 6); login email field + forced-change screen
  (Task 7); Users page (Task 8).
- **Green between tasks:** Tasks 1–4 add code without changing the session
  contract, so the suite stays green. Task 5 is the atomic cutover — it
  changes the login contract, `require_session`, and every affected test
  fixture together. Tasks 6–8 are additive.
- **Type consistency:** `authdb` connection helper is `auth_conn`; it is
  autocommit so failed-login audit writes persist. `authenticate` returns
  `AuthResult(user_id, email, must_change_password)`. The session cookie key
  is `user_id`. `routes/users.py` request bodies (`CreateUserBody`,
  `UpdateUserBody`) match the `authdb` functions. `_public()` strips
  `password_hash`; `list_users` already excludes it.
- **Not committed to the repo:** the first user's plaintext temporary
  password — it is passed to `init-auth` as a CLI argument at run time.
