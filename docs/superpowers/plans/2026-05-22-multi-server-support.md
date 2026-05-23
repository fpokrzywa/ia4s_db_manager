# Multi-Server Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single hardwired Postgres server with an in-app registry of servers, a top-bar picker to choose the active server per session, and connection passwords encrypted at rest.

**Architecture:** A `servers` table joins `users`/`user_sessions` in the `common_data` home database. The session cookie carries the active `server_id`; a FastAPI dependency resolves it (decrypting the password) into a connection string, and the four resource routers use that instead of `DATABASE_URL`. Server passwords are Fernet-encrypted with a key derived from `APP_SECRET`.

**Tech Stack:** FastAPI, psycopg 3, `cryptography` (Fernet), vanilla-JS ES modules, pytest.

**Spec:** `docs/superpowers/specs/2026-05-22-multi-server-support-design.md`

**Branch:** continue on the existing `feature/multi-user-auth` branch (this builds on the unmerged auth work). No new branch.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/dbmanager/crypto.py` | NEW — Fernet `encrypt`/`decrypt`, key derived from `APP_SECRET`. |
| `src/dbmanager/serverdb.py` | NEW — `servers` schema, CRUD, and `conninfo_for()` (record → libpq conninfo). |
| `src/dbmanager/deps.py` | MODIFY — `active_server` dependency; `server_db`/`target_db` take a server conninfo. |
| `src/dbmanager/config.py` | MODIFY — `database_url` becomes optional. |
| `src/dbmanager/routes/servers.py` | NEW — registry CRUD, connection test, active-server endpoints. |
| `src/dbmanager/routes/{databases,tables,rows,query}.py` | MODIFY — inject the active server. |
| `src/dbmanager/webapp.py` | MODIFY — `server-info` uses the active server; register the servers router. |
| `src/dbmanager/cli.py` | MODIFY — `init-auth` also creates the `servers` table and seeds from `DATABASE_URL`. |
| `src/dbmanager/web/servers.js` | NEW — Servers management page. |
| `src/dbmanager/web/app.js` | MODIFY — sidebar "Servers" entry + top-bar server picker. |
| `tests/conftest.py` | MODIFY — apply the servers schema; the `client` fixture seeds a default test server. |

`src/dbmanager/db.py` is unchanged — `server_conn(conninfo)` / `db_conn(conninfo, dbname)` already accept any conninfo string.

---

## Task 1: Password encryption (`crypto.py`)

**Files:** Modify `pyproject.toml`; create `src/dbmanager/crypto.py`, `tests/test_crypto.py`.

- [ ] **Step 1: Add the `cryptography` dependency to `pyproject.toml`**

In the `[project]` `dependencies` list add `"cryptography>=42"`:

```toml
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "psycopg[binary]>=3.2",
    "python-dotenv>=1.0",
    "itsdangerous>=2.0",
    "click>=8.1",
    "bcrypt>=4.0",
    "cryptography>=42",
]
```

Run: `pip install -e ".[dev]"` — expected: installs `cryptography`.

- [ ] **Step 2: Write `tests/test_crypto.py`**

```python
from dbmanager.crypto import encrypt, decrypt


def test_encrypt_decrypt_round_trip():
    token = encrypt("s3cr3t-password")
    assert token != "s3cr3t-password"
    assert decrypt(token) == "s3cr3t-password"


def test_encrypt_is_non_deterministic():
    assert encrypt("same") != encrypt("same")


def test_encrypt_handles_empty_string():
    assert decrypt(encrypt("")) == ""
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_crypto.py -v`
Expected: FAIL — no module `dbmanager.crypto`.

- [ ] **Step 4: Write `src/dbmanager/crypto.py`**

```python
"""Symmetric encryption for stored secrets (server passwords).

Uses Fernet with a key derived from APP_SECRET, so no extra environment
variable is required. Rotating APP_SECRET makes existing tokens undecryptable
(stored server passwords would need to be re-entered)."""
from __future__ import annotations
import base64
import hashlib
from cryptography.fernet import Fernet
from dbmanager.config import Settings


def _fernet() -> Fernet:
    secret = Settings.from_env().app_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt(plain: str) -> str:
    """Return a Fernet token for the plaintext."""
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    """Return the plaintext for a Fernet token produced by `encrypt`."""
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_crypto.py -v` (expected: 3 pass). Then `pytest -q` — full suite still passes.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/dbmanager/crypto.py tests/test_crypto.py
git commit -m "feat: Fernet encryption for stored secrets"
```

---

## Task 2: Server registry data layer (`serverdb.py`)

**Files:** Create `src/dbmanager/serverdb.py`, `tests/test_serverdb.py`; modify `tests/conftest.py`.

- [ ] **Step 1: Apply the servers schema in the `common_data_url` fixture**

In `tests/conftest.py`, the `common_data_url` fixture currently does
`apply_schema(url)` (auth schema) then seeds a test user. Change the import
block and add the servers-schema call. The fixture body's first lines are:

```python
    from dbmanager.authdb import apply_schema
    from dbmanager.passwords import hash_password
    apply_schema(url)
```

Replace those three lines with:

```python
    from dbmanager.authdb import apply_schema
    from dbmanager.serverdb import apply_schema as apply_servers_schema
    from dbmanager.passwords import hash_password
    apply_schema(url)
    apply_servers_schema(url)
```

- [ ] **Step 2: Write `tests/test_serverdb.py`**

```python
from dbmanager import serverdb
from dbmanager.authdb import auth_conn


def test_create_and_get_server(common_data_url):
    with auth_conn(common_data_url) as conn:
        created = serverdb.create_server(
            conn, label="prod", host="db.example.com", port=5432,
            username="admin", password="pw", is_default=True)
        assert created["label"] == "prod"
        fetched = serverdb.get_server(conn, created["id"])
        assert fetched["host"] == "db.example.com"
        assert fetched["password_enc"] != "pw"          # stored encrypted


def test_list_servers_excludes_password(common_data_url):
    with auth_conn(common_data_url) as conn:
        serverdb.create_server(conn, label="s1", host="h", port=5432,
                               username="u", password="pw")
        rows = serverdb.list_servers(conn)
    assert rows and all("password_enc" not in r for r in rows)


def test_default_server_prefers_is_default(common_data_url):
    with auth_conn(common_data_url) as conn:
        serverdb.create_server(conn, label="a", host="h", port=5432,
                               username="u", password="pw")
        b = serverdb.create_server(conn, label="b", host="h", port=5432,
                                   username="u", password="pw", is_default=True)
        assert serverdb.default_server(conn)["id"] == b["id"]


def test_setting_default_clears_other_defaults(common_data_url):
    with auth_conn(common_data_url) as conn:
        a = serverdb.create_server(conn, label="a", host="h", port=5432,
                                   username="u", password="pw", is_default=True)
        serverdb.create_server(conn, label="b", host="h", port=5432,
                               username="u", password="pw", is_default=True)
        assert serverdb.get_server(conn, a["id"])["is_default"] is False


def test_update_server_keeps_password_when_none(common_data_url):
    with auth_conn(common_data_url) as conn:
        s = serverdb.create_server(conn, label="s", host="h", port=5432,
                                   username="u", password="orig")
        before = serverdb.get_server(conn, s["id"])["password_enc"]
        serverdb.update_server(conn, s["id"], label="s2", host="h2", port=5433,
                               username="u2", password=None,
                               maintenance_db="postgres", sslmode="require",
                               is_default=False, notes="x")
        after = serverdb.get_server(conn, s["id"])
        assert after["password_enc"] == before          # unchanged
        assert after["host"] == "h2" and after["port"] == 5433


def test_delete_server(common_data_url):
    with auth_conn(common_data_url) as conn:
        s = serverdb.create_server(conn, label="gone", host="h", port=5432,
                                   username="u", password="pw")
        assert serverdb.delete_server(conn, s["id"]) is True
        assert serverdb.get_server(conn, s["id"]) is None


def test_conninfo_for_decrypts_password(common_data_url):
    with auth_conn(common_data_url) as conn:
        s = serverdb.create_server(conn, label="c", host="h.example", port=6000,
                                   username="bob", password="topsecret",
                                   sslmode="require")
        full = serverdb.get_server(conn, s["id"])
    info = serverdb.conninfo_for(full, dbname="mydb")
    assert "password=topsecret" in info
    assert "host=h.example" in info and "dbname=mydb" in info
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_serverdb.py -v`
Expected: FAIL — no module `dbmanager.serverdb`.

- [ ] **Step 4: Write `src/dbmanager/serverdb.py`**

```python
"""Server registry — schema and data access for the `servers` table in the
common_data database, plus connection-string assembly."""
from __future__ import annotations
from psycopg.conninfo import make_conninfo
from dbmanager.authdb import auth_conn
from dbmanager.crypto import decrypt, encrypt

SERVERS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS servers (
    id              serial PRIMARY KEY,
    label           text UNIQUE NOT NULL,
    host            text NOT NULL,
    port            integer NOT NULL DEFAULT 5432,
    username        text NOT NULL,
    password_enc    text NOT NULL,
    maintenance_db  text NOT NULL DEFAULT 'postgres',
    sslmode         text NOT NULL DEFAULT 'prefer',
    is_default      boolean NOT NULL DEFAULT false,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
"""

_SAFE_COLUMNS = ("id, label, host, port, username, maintenance_db, sslmode, "
                 "is_default, notes, created_at, updated_at")


def apply_schema(common_data_url: str) -> None:
    """Create the servers table if it does not already exist."""
    with auth_conn(common_data_url) as conn:
        conn.execute(SERVERS_SCHEMA_SQL)


def public(server: dict) -> dict:
    """A server row without the encrypted password."""
    return {k: v for k, v in server.items() if k != "password_enc"}


def list_servers(conn) -> list[dict]:
    return conn.execute(
        f"SELECT {_SAFE_COLUMNS} FROM servers ORDER BY label").fetchall()


def get_server(conn, server_id) -> dict | None:
    return conn.execute(
        "SELECT * FROM servers WHERE id = %s", (server_id,)).fetchone()


def default_server(conn) -> dict | None:
    """The is_default server, else the lowest-id server, else None."""
    row = conn.execute(
        "SELECT * FROM servers WHERE is_default = true ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM servers ORDER BY id LIMIT 1").fetchone()
    return row


def _clear_default(conn) -> None:
    conn.execute("UPDATE servers SET is_default = false "
                 "WHERE is_default = true")


def create_server(conn, *, label, host, port, username, password,
                   maintenance_db="postgres", sslmode="prefer",
                   is_default=False, notes=None) -> dict:
    if is_default:
        _clear_default(conn)
    return conn.execute("""
        INSERT INTO servers (label, host, port, username, password_enc,
            maintenance_db, sslmode, is_default, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
    """, (label, host, port, username, encrypt(password), maintenance_db,
          sslmode, is_default, notes)).fetchone()


def update_server(conn, server_id, *, label, host, port, username, password,
                   maintenance_db, sslmode, is_default, notes) -> dict | None:
    """Update a server. `password=None` leaves the stored password unchanged."""
    if is_default:
        _clear_default(conn)
    if password is None:
        conn.execute("""
            UPDATE servers SET label=%s, host=%s, port=%s, username=%s,
                maintenance_db=%s, sslmode=%s, is_default=%s, notes=%s,
                updated_at=now()
            WHERE id=%s
        """, (label, host, port, username, maintenance_db, sslmode,
              is_default, notes, server_id))
    else:
        conn.execute("""
            UPDATE servers SET label=%s, host=%s, port=%s, username=%s,
                password_enc=%s, maintenance_db=%s, sslmode=%s, is_default=%s,
                notes=%s, updated_at=now()
            WHERE id=%s
        """, (label, host, port, username, encrypt(password), maintenance_db,
              sslmode, is_default, notes, server_id))
    return get_server(conn, server_id)


def delete_server(conn, server_id) -> bool:
    row = conn.execute("DELETE FROM servers WHERE id = %s RETURNING id",
                        (server_id,)).fetchone()
    return row is not None


def conninfo_for(server: dict, dbname: str | None = None) -> str:
    """Build a libpq conninfo string for a server record. `dbname` overrides
    the server's maintenance database."""
    return make_conninfo(
        "",
        host=server["host"],
        port=str(server["port"]),
        user=server["username"],
        password=decrypt(server["password_enc"]),
        dbname=dbname or server["maintenance_db"],
        sslmode=server["sslmode"],
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_serverdb.py -v` (expected: 7 pass). Then `pytest -q` — full suite still passes.

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/serverdb.py tests/test_serverdb.py tests/conftest.py
git commit -m "feat: server registry data layer"
```

---

## Task 3: Setup migration — `init-auth` creates servers + seeds from `DATABASE_URL`

**Files:** Modify `src/dbmanager/cli.py`; create `tests/test_init_servers.py`.

- [ ] **Step 1: Write `tests/test_init_servers.py`**

```python
import psycopg
from click.testing import CliRunner
from dbmanager.cli import cli


def test_init_auth_creates_servers_table_and_seeds(common_data_url, server_url,
                                                   monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    monkeypatch.setenv("DATABASE_URL", server_url)
    result = CliRunner().invoke(cli, ["init-auth", "--email", "a@example.com",
                                      "--password", "TempPass123"])
    assert result.exit_code == 0, result.output
    with psycopg.connect(common_data_url) as conn:
        servers = conn.execute(
            "SELECT label, is_default FROM servers").fetchall()
    assert len(servers) == 1
    assert servers[0][1] is True          # seeded server is the default


def test_init_auth_does_not_duplicate_seed(common_data_url, server_url,
                                           monkeypatch):
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    monkeypatch.setenv("DATABASE_URL", server_url)
    runner = CliRunner()
    runner.invoke(cli, ["init-auth", "--email", "a@example.com",
                        "--password", "TempPass123"])
    runner.invoke(cli, ["init-auth", "--email", "a@example.com",
                        "--password", "TempPass123"])
    with psycopg.connect(common_data_url) as conn:
        count = conn.execute("SELECT count(*) FROM servers").fetchone()[0]
    assert count == 1                     # second run does not re-seed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_init_servers.py -v`
Expected: FAIL — `init-auth` does not create the `servers` table, so the
`SELECT ... FROM servers` raises `UndefinedTable`.

- [ ] **Step 3: Replace the `init_auth` command in `src/dbmanager/cli.py`**

Replace the entire `init_auth` function (the `@cli.command("init-auth")`
block) with:

```python
@cli.command("init-auth")
@click.option("--email", required=True, help="Email of the first user.")
@click.option("--password", required=True, help="Temporary password.")
def init_auth(email: str, password: str) -> None:
    """Create the auth + servers tables in common_data, seed the first user,
    and register the DATABASE_URL server if the registry is empty."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_init_servers.py -v` (expected: 2 pass). Then
`pytest tests/test_init_auth.py -v` — the existing init-auth tests still pass.
Then `pytest -q` — full suite passes.

- [ ] **Step 5: Commit**

```bash
git add src/dbmanager/cli.py tests/test_init_servers.py
git commit -m "feat: init-auth provisions the server registry"
```

---

## Task 4: Active-server cutover — dependency, deps refactor, route updates

This atomic task switches every database operation from the single
`DATABASE_URL` to the session's active server. It changes `config.py`,
`deps.py`, all four resource routers, `webapp.py`'s `server-info`, and the
`client` test fixture together, so the suite stays green.

**Files:** Modify `src/dbmanager/config.py`, `src/dbmanager/deps.py`,
`src/dbmanager/routes/databases.py`, `src/dbmanager/routes/tables.py`,
`src/dbmanager/routes/rows.py`, `src/dbmanager/routes/query.py`,
`src/dbmanager/webapp.py`, `tests/conftest.py`, `tests/test_config.py`.

- [ ] **Step 1: Make `database_url` optional in `src/dbmanager/config.py`**

Replace the file entirely:

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
    database_url: str | None
    common_data_url: str
    app_secret: str

    @classmethod
    def from_env(cls) -> "Settings":
        common = os.environ.get("DATABASE_COMMON_DATA_URL")
        if not common:
            raise RuntimeError(
                "DATABASE_COMMON_DATA_URL is required in environment or .env")
        secret = os.environ.get("APP_SECRET")
        if not secret:
            raise RuntimeError("APP_SECRET is required in environment or .env")
        # DATABASE_URL is optional — only used to seed the first server.
        return cls(database_url=os.environ.get("DATABASE_URL") or None,
                   common_data_url=common, app_secret=secret)
```

- [ ] **Step 2: Add an optional-`database_url` test to `tests/test_config.py`**

Append:

```python
def test_from_env_allows_missing_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", "postgresql://localhost/common_data")
    monkeypatch.setenv("APP_SECRET", "x" * 32)
    assert Settings.from_env().database_url is None
```

- [ ] **Step 3: Replace `src/dbmanager/deps.py` entirely**

```python
"""Request-scoped database access for the route layer.

`active_server` resolves the session's chosen server (decrypting its stored
password) into a libpq conninfo string. `server_db`/`target_db` open
connections to that server."""
from __future__ import annotations
from contextlib import contextmanager
from fastapi import HTTPException, Request
from dbmanager import authdb, serverdb
from dbmanager.config import Settings
from dbmanager.db import db_conn, server_conn


def active_server(request: Request) -> str:
    """FastAPI dependency: the maintenance conninfo for the session's active
    server. Falls back to the default server; raises 503 if none registered."""
    settings = Settings.from_env()
    with authdb.auth_conn(settings.common_data_url) as conn:
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
    """Autocommit connection to the active server's maintenance database."""
    try:
        with server_conn(server) as conn:
            yield conn
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503,
                            detail=f"database error: {exc}") from exc


@contextmanager
def target_db(server: str, dbname: str):
    """Transactional connection to `dbname` on the active server."""
    try:
        with db_conn(server, dbname) as conn:
            yield conn
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503,
                            detail=f"database error: {exc}") from exc
```

- [ ] **Step 4: Replace `src/dbmanager/routes/databases.py` entirely**

```python
"""Database list / create / drop."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager import sqlbuild
from dbmanager.deps import active_server, server_db
from dbmanager.inspect import list_databases

router = APIRouter(prefix="/api/databases", tags=["databases"])


class CreateDatabaseBody(BaseModel):
    name: str
    owner: str | None = None
    encoding: str | None = None


@router.get("")
def get_databases(server: str = Depends(active_server)) -> list[dict]:
    """Every non-template database with owner, encoding, and size."""
    with server_db(server) as conn:
        return list_databases(conn)


@router.post("", status_code=201)
def create_database(body: CreateDatabaseBody,
                    server: str = Depends(active_server)) -> dict:
    """Create a database."""
    name = sqlbuild.validate_identifier(body.name, "database name")
    owner = body.owner.strip() if body.owner and body.owner.strip() else None
    encoding = body.encoding.strip() if body.encoding and body.encoding.strip() else None
    stmt = sqlbuild.create_database(name, owner, encoding)
    with server_db(server) as conn:
        try:
            conn.execute(stmt)
        except pgerrors.DuplicateDatabase as exc:
            raise HTTPException(409, f"database '{name}' already exists") from exc
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"created": name}


@router.delete("/{name}")
def drop_database(name: str, force: bool = False,
                  server: str = Depends(active_server)) -> dict:
    """Drop a database. `force` terminates active connections first."""
    name = sqlbuild.validate_identifier(name, "database name")
    stmt = sqlbuild.drop_database(name, force)
    with server_db(server) as conn:
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

- [ ] **Step 5: Replace `src/dbmanager/routes/query.py` entirely**

```python
"""SQL console — runs arbitrary SQL against a chosen database."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager.deps import active_server, target_db

router = APIRouter(prefix="/api/databases/{db}/query", tags=["query"])


class QueryBody(BaseModel):
    sql: str


@router.post("")
def run_query(db: str, body: QueryBody,
              server: str = Depends(active_server)) -> dict:
    """Execute `body.sql`. Result sets return columns+rows; other statements
    return an affected-row count. The transaction commits on success."""
    statement = body.sql.strip()
    if not statement:
        raise HTTPException(400, "no SQL provided")
    with target_db(server, db) as conn:
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

- [ ] **Step 6: Replace `src/dbmanager/routes/tables.py` entirely**

```python
"""Table list/inspect/create/rename/drop and column/constraint/index DDL."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager import sqlbuild
from dbmanager.deps import active_server, target_db
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


def _run(server: str, db: str, stmts):
    """Execute one statement or a list of them in a single transaction,
    mapping Postgres errors to HTTP status codes."""
    if not isinstance(stmts, (list, tuple)):
        stmts = [stmts]
    with target_db(server, db) as conn:
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
def get_tables(db: str, server: str = Depends(active_server)) -> list[dict]:
    with target_db(server, db) as conn:
        return list_tables(conn)


@router.get("/{table}")
def get_table(db: str, table: str,
              server: str = Depends(active_server)) -> dict:
    with target_db(server, db) as conn:
        struct = table_structure(conn, table)
    if not struct:
        raise HTTPException(404, f"no table '{table}' in database '{db}'")
    return struct


@router.post("", status_code=201)
def create_table(db: str, body: CreateTableBody,
                 server: str = Depends(active_server)) -> dict:
    name = sqlbuild.validate_identifier(body.name, "table name")
    _run(server, db,
         sqlbuild.create_table(name, [c.model_dump() for c in body.columns]))
    return {"created": name}


@router.patch("/{table}")
def rename_table(db: str, table: str, body: RenameTableBody,
                 server: str = Depends(active_server)) -> dict:
    new_name = sqlbuild.validate_identifier(body.new_name, "new table name")
    _run(server, db, sqlbuild.rename_table(table, new_name))
    return {"renamed": new_name}


@router.delete("/{table}")
def drop_table(db: str, table: str,
               server: str = Depends(active_server)) -> dict:
    _run(server, db, sqlbuild.drop_table(table))
    return {"dropped": table}


@router.post("/{table}/columns", status_code=201)
def add_column(db: str, table: str, body: ColumnDef,
               server: str = Depends(active_server)) -> dict:
    sqlbuild.validate_identifier(body.name, "column name")
    _run(server, db, sqlbuild.add_column(table, body.model_dump()))
    return {"added": body.name}


@router.patch("/{table}/columns/{column}")
def alter_column(db: str, table: str, column: str, body: AlterColumnBody,
                 server: str = Depends(active_server)) -> dict:
    stmts = sqlbuild.alter_column(table, column, body.model_dump())
    if not stmts:
        raise HTTPException(400, "no changes requested")
    _run(server, db, stmts)
    return {"altered": column}


@router.delete("/{table}/columns/{column}")
def drop_column(db: str, table: str, column: str,
                server: str = Depends(active_server)) -> dict:
    _run(server, db, sqlbuild.drop_column(table, column))
    return {"dropped": column}


@router.post("/{table}/constraints", status_code=201)
def add_constraint(db: str, table: str, body: ConstraintBody,
                   server: str = Depends(active_server)) -> dict:
    _run(server, db, sqlbuild.add_constraint(table, body.model_dump()))
    return {"added": body.name or body.type}


@router.delete("/{table}/constraints/{name}")
def drop_constraint(db: str, table: str, name: str,
                    server: str = Depends(active_server)) -> dict:
    _run(server, db, sqlbuild.drop_constraint(table, name))
    return {"dropped": name}


@router.post("/{table}/indexes", status_code=201)
def create_index(db: str, table: str, body: IndexBody,
                 server: str = Depends(active_server)) -> dict:
    sqlbuild.validate_identifier(body.name, "index name")
    _run(server, db,
         sqlbuild.create_index(table, body.name, body.columns, body.unique))
    return {"created": body.name}


@router.delete("/{table}/indexes/{name}")
def drop_index(db: str, table: str, name: str,
               server: str = Depends(active_server)) -> dict:
    _run(server, db, sqlbuild.drop_index(name))
    return {"dropped": name}
```

- [ ] **Step 7: Replace `src/dbmanager/routes/rows.py` entirely**

```python
"""Paginated row browsing and row insert/update/delete.

Rows are identified for update/delete by their primary-key columns. A table
with no primary key is returned as a read-only grid (editable=false).
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from psycopg import errors as pgerrors, sql as pgsql
from pydantic import BaseModel

from dbmanager.deps import active_server, target_db
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
              filter_value: str | None = None,
              server: str = Depends(active_server)) -> dict:
    """A page of rows, plus total count and primary-key metadata."""
    page = max(page, 1)
    page_size = min(max(page_size, 1), 500)
    with target_db(server, db) as conn:
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
def insert_row(db: str, table: str, body: InsertBody,
               server: str = Depends(active_server)) -> dict:
    if not body.values:
        raise HTTPException(400, "no values supplied")
    cols = list(body.values)
    stmt = pgsql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
        qualified(table),
        pgsql.SQL(", ").join(pgsql.Identifier(c) for c in cols),
        pgsql.SQL(", ").join(pgsql.Placeholder() for _ in cols))
    with target_db(server, db) as conn:
        try:
            row = conn.execute(stmt, [body.values[c] for c in cols]).fetchone()
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"inserted": row}


@router.patch("")
def update_row(db: str, table: str, body: UpdateBody,
               server: str = Depends(active_server)) -> dict:
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
    with target_db(server, db) as conn:
        try:
            row = conn.execute(stmt, params).fetchone()
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    if row is None:
        raise HTTPException(404, "no row matched the supplied primary key")
    return {"updated": row}


@router.delete("")
def delete_row(db: str, table: str, body: DeleteBody,
               server: str = Depends(active_server)) -> dict:
    if not body.pk:
        raise HTTPException(400, "primary-key values are required to delete a row")
    pcols = list(body.pk)
    stmt = pgsql.SQL("DELETE FROM {} WHERE {} RETURNING *").format(
        qualified(table),
        pgsql.SQL(" AND ").join(
            pgsql.SQL("{} = {}").format(pgsql.Identifier(c), pgsql.Placeholder())
            for c in pcols))
    with target_db(server, db) as conn:
        try:
            row = conn.execute(stmt, [body.pk[c] for c in pcols]).fetchone()
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    if row is None:
        raise HTTPException(404, "no row matched the supplied primary key")
    return {"deleted": row}
```

- [ ] **Step 8: Update `server-info` in `src/dbmanager/webapp.py`**

Change the import line `from dbmanager.auth import require_session` to also
import `active_server`:

```python
from dbmanager.auth import require_session
from dbmanager.deps import active_server
```

Replace the `server_info` function with:

```python
@app.get("/api/server-info", dependencies=[Depends(require_session)])
def server_info(server: str = Depends(active_server)) -> dict:
    """Host and port of the active Postgres server — no credentials."""
    info = conninfo_to_dict(server)
    return {"host": info.get("host") or "", "port": info.get("port") or ""}
```

- [ ] **Step 9: Seed a default test server in the `client` fixture (`tests/conftest.py`)**

Replace the `client` fixture with:

```python
@pytest.fixture
def client(server_url, common_data_url, monkeypatch):
    """A TestClient logged in as the seeded test user, with a default server
    (the throwaway Postgres) registered."""
    from fastapi.testclient import TestClient
    from psycopg.conninfo import conninfo_to_dict
    from dbmanager import authdb, serverdb
    monkeypatch.setenv("DATABASE_URL", server_url)
    monkeypatch.setenv("DATABASE_COMMON_DATA_URL", common_data_url)
    p = conninfo_to_dict(server_url)
    with authdb.auth_conn(common_data_url) as conn:
        if not serverdb.list_servers(conn):
            serverdb.create_server(
                conn, label="test-server", host=p.get("host"),
                port=int(p.get("port") or 5432), username=p.get("user"),
                password=p.get("password") or "", maintenance_db="postgres",
                is_default=True)
    from dbmanager.webapp import app
    c = TestClient(app)
    resp = c.post("/api/login", json={"email": "test@example.com",
                                      "password": "test-password"})
    assert resp.status_code == 200, resp.text
    return c
```

- [ ] **Step 10: Run the full suite**

Run: `pytest -q`
Expected: PASS — every test. The route tests (`test_databases`, `test_tables`,
`test_rows`, `test_query`) now resolve the active server from the seeded
default test server. If any route test fails with a 503 "no Postgres server
is registered", the `client` fixture's server seed (Step 9) is wrong.

- [ ] **Step 11: Commit**

```bash
git add src/dbmanager/config.py src/dbmanager/deps.py src/dbmanager/webapp.py src/dbmanager/routes/ tests/
git commit -m "feat: route layer targets the session's active server"
```

---

## Task 5: Server registry routes (`routes/servers.py`)

**Files:** Create `src/dbmanager/routes/servers.py`, `tests/test_servers.py`;
modify `src/dbmanager/webapp.py`.

- [ ] **Step 1: Write `tests/test_servers.py`**

```python
def test_list_servers_includes_seed(client):
    resp = client.get("/api/servers")
    assert resp.status_code == 200
    labels = [s["label"] for s in resp.json()]
    assert "test-server" in labels
    assert all("password_enc" not in s for s in resp.json())


def test_create_server(client):
    resp = client.post("/api/servers", json={
        "label": "staging", "host": "stg.example.com", "port": 5432,
        "username": "admin", "password": "pw"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["label"] == "staging"
    assert "password_enc" not in body


def test_create_duplicate_label_conflicts(client):
    client.post("/api/servers", json={"label": "dup", "host": "h",
                                      "username": "u", "password": "pw"})
    resp = client.post("/api/servers", json={"label": "dup", "host": "h",
                                             "username": "u", "password": "pw"})
    assert resp.status_code == 409


def test_create_server_requires_password(client):
    resp = client.post("/api/servers", json={"label": "nopw", "host": "h",
                                             "username": "u"})
    assert resp.status_code == 400


def test_update_server(client):
    created = client.post("/api/servers", json={
        "label": "edit-me", "host": "h", "username": "u",
        "password": "pw"}).json()
    resp = client.patch(f"/api/servers/{created['id']}", json={
        "label": "edited", "host": "h2", "port": 5433, "username": "u",
        "sslmode": "require"})
    assert resp.status_code == 200
    assert resp.json()["host"] == "h2" and resp.json()["label"] == "edited"


def test_delete_server(client):
    created = client.post("/api/servers", json={
        "label": "temp", "host": "h", "username": "u",
        "password": "pw"}).json()
    assert client.delete(f"/api/servers/{created['id']}").status_code == 200
    assert client.delete(f"/api/servers/{created['id']}").status_code == 404


def test_set_and_get_active_server(client):
    created = client.post("/api/servers", json={
        "label": "pick-me", "host": "h", "username": "u",
        "password": "pw"}).json()
    set_resp = client.post("/api/active-server",
                           json={"server_id": created["id"]})
    assert set_resp.status_code == 200
    assert client.get("/api/active-server").json()["id"] == created["id"]


def test_test_endpoint_reports_failure(client):
    created = client.post("/api/servers", json={
        "label": "unreachable", "host": "203.0.113.9", "port": 5432,
        "username": "u", "password": "pw"}).json()
    resp = client.post(f"/api/servers/{created['id']}/test")
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_servers.py -v`
Expected: FAIL — 404 on `/api/servers` (router not registered).

- [ ] **Step 3: Write `src/dbmanager/routes/servers.py`**

```python
"""Server registry — CRUD, connection test, and active-server selection."""
from __future__ import annotations
import psycopg
from fastapi import APIRouter, HTTPException, Request
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager import authdb, serverdb
from dbmanager.config import Settings

router = APIRouter(prefix="/api", tags=["servers"])


class ServerBody(BaseModel):
    label: str
    host: str
    port: int = 5432
    username: str
    password: str | None = None
    maintenance_db: str = "postgres"
    sslmode: str = "prefer"
    is_default: bool = False
    notes: str | None = None


class ActiveServerBody(BaseModel):
    server_id: int


def _conn():
    return authdb.auth_conn(Settings.from_env().common_data_url)


@router.get("/servers")
def get_servers() -> list[dict]:
    """Every registered server (no passwords)."""
    with _conn() as conn:
        return serverdb.list_servers(conn)


@router.post("/servers", status_code=201)
def create_server(body: ServerBody) -> dict:
    if not (body.label.strip() and body.host.strip() and body.username.strip()):
        raise HTTPException(400, "label, host and username are required")
    if not body.password:
        raise HTTPException(400, "a password is required for a new server")
    with _conn() as conn:
        try:
            row = serverdb.create_server(
                conn, label=body.label.strip(), host=body.host.strip(),
                port=body.port, username=body.username.strip(),
                password=body.password,
                maintenance_db=body.maintenance_db.strip() or "postgres",
                sslmode=body.sslmode, is_default=body.is_default,
                notes=body.notes)
        except pgerrors.UniqueViolation as exc:
            raise HTTPException(
                409, f"a server labeled '{body.label}' already exists") from exc
    return serverdb.public(row)


@router.patch("/servers/{server_id}")
def update_server(server_id: int, body: ServerBody) -> dict:
    with _conn() as conn:
        if serverdb.get_server(conn, server_id) is None:
            raise HTTPException(404, f"no server with id {server_id}")
        try:
            row = serverdb.update_server(
                conn, server_id, label=body.label.strip(),
                host=body.host.strip(), port=body.port,
                username=body.username.strip(), password=body.password or None,
                maintenance_db=body.maintenance_db.strip() or "postgres",
                sslmode=body.sslmode, is_default=body.is_default,
                notes=body.notes)
        except pgerrors.UniqueViolation as exc:
            raise HTTPException(
                409, f"a server labeled '{body.label}' already exists") from exc
    return serverdb.public(row)


@router.delete("/servers/{server_id}")
def delete_server(server_id: int) -> dict:
    with _conn() as conn:
        if not serverdb.delete_server(conn, server_id):
            raise HTTPException(404, f"no server with id {server_id}")
    return {"deleted": server_id}


@router.post("/servers/{server_id}/test")
def test_server(server_id: int) -> dict:
    """Try to connect to a server; report success or the error message."""
    with _conn() as conn:
        server = serverdb.get_server(conn, server_id)
    if server is None:
        raise HTTPException(404, f"no server with id {server_id}")
    try:
        with psycopg.connect(serverdb.conninfo_for(server),
                             connect_timeout=8) as probe:
            probe.execute("SELECT 1")
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/active-server")
def get_active_server(request: Request) -> dict:
    """The session's active server (falls back to the default)."""
    with _conn() as conn:
        sid = request.session.get("server_id")
        server = serverdb.get_server(conn, sid) if sid else None
        if server is None:
            server = serverdb.default_server(conn)
    if server is None:
        return {"id": None, "label": None}
    return {"id": server["id"], "label": server["label"]}


@router.post("/active-server")
def set_active_server(body: ActiveServerBody, request: Request) -> dict:
    with _conn() as conn:
        server = serverdb.get_server(conn, body.server_id)
    if server is None:
        raise HTTPException(404, f"no server with id {body.server_id}")
    request.session["server_id"] = server["id"]
    return {"id": server["id"], "label": server["label"]}
```

- [ ] **Step 4: Register the router in `src/dbmanager/webapp.py`**

Add `servers` to the routes import so it reads:

```python
from dbmanager.routes import databases, query, rows, servers, session, tables, users
```

Add this line immediately after `app.include_router(users.router, ...)`:

```python
app.include_router(servers.router, dependencies=[Depends(require_session)])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_servers.py -v` (expected: 8 pass). Then `pytest -q` —
full suite passes.

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/routes/servers.py src/dbmanager/webapp.py tests/test_servers.py
git commit -m "feat: server registry routes"
```

---

## Task 6: Servers management page (frontend)

**Files:** Create `src/dbmanager/web/servers.js`; modify `src/dbmanager/web/app.js`.

No automated frontend test — verify the files are served and the backend
suite still passes.

- [ ] **Step 1: Create `src/dbmanager/web/servers.js`**

```js
import { get, post, patch, del } from "./api.js";
import { confirmModal, formModal, showError } from "./app.js";

const SSLMODES = ["prefer", "require", "disable", "allow",
                  "verify-ca", "verify-full"];

// Render the Servers management panel.
export async function renderServers() {
  const panel = document.getElementById("panel");
  panel.innerHTML = "";

  const h = document.createElement("h2");
  h.textContent = "Servers";
  panel.append(h);

  const toolbar = document.createElement("div");
  toolbar.className = "toolbar";
  toolbar.append(mkBtn("+ Server", () => serverDialog(null), ""));
  panel.append(toolbar);

  const servers = await get("/api/servers");
  const table = document.createElement("table");
  table.className = "grid";
  table.innerHTML =
    "<thead><tr><th>Label</th><th>Host</th><th>Port</th><th>User</th>" +
    "<th>SSL</th><th>Default</th><th></th></tr></thead>";
  const body = document.createElement("tbody");
  for (const s of servers) {
    const tr = document.createElement("tr");
    for (const text of [s.label, s.host, s.port, s.username, s.sslmode,
                        s.is_default ? "yes" : "no"]) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.append(td);
    }
    const actions = document.createElement("td");
    actions.append(
      mkBtn("Test", () => testServer(s.id), "ghost"),
      mkBtn("Edit", () => serverDialog(s), "ghost"),
      mkBtn("Delete", () => deleteServer(s), "ghost"));
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

// Add (server=null) or edit a server.
async function serverDialog(server) {
  const editing = server !== null;
  const v = await formModal(editing ? `Edit "${server.label}"` : "Add server", [
    { name: "label", label: "Label", type: "text",
      value: editing ? server.label : "" },
    { name: "host", label: "Host", type: "text",
      value: editing ? server.host : "" },
    { name: "port", label: "Port", type: "number",
      value: editing ? String(server.port) : "5432" },
    { name: "username", label: "Username", type: "text",
      value: editing ? server.username : "" },
    { name: "password", label: editing ? "Password (blank = keep)" : "Password",
      type: "password" },
    { name: "maintenance_db", label: "Maint. DB", type: "text",
      value: editing ? server.maintenance_db : "postgres" },
    { name: "sslmode", label: "SSL mode", type: "select", options: SSLMODES },
    { name: "is_default", label: "Default", type: "checkbox",
      value: editing ? server.is_default : false },
    { name: "notes", label: "Notes", type: "text",
      value: editing ? (server.notes || "") : "" },
  ]);
  if (!v) return;
  const payload = {
    label: v.label, host: v.host, port: Number(v.port) || 5432,
    username: v.username, maintenance_db: v.maintenance_db,
    sslmode: v.sslmode, is_default: v.is_default, notes: v.notes || null,
    password: v.password || null,
  };
  try {
    if (editing) await patch(`/api/servers/${server.id}`, payload);
    else await post("/api/servers", payload);
    await renderServers();
  } catch (e) { showError(e.message); }
}

async function testServer(id) {
  try {
    const r = await post(`/api/servers/${id}/test`);
    showError(r.ok ? "Connection succeeded." : `Connection failed: ${r.error}`);
  } catch (e) { showError(e.message); }
}

async function deleteServer(server) {
  const ok = await confirmModal(`Delete server "${server.label}"`,
    "This removes the server from the registry. Type the label to confirm.",
    server.label);
  if (!ok) return;
  try {
    await del(`/api/servers/${server.id}`);
    await renderServers();
  } catch (e) { showError(e.message); }
}
```

- [ ] **Step 2: Wire the Servers page into `src/dbmanager/web/app.js`**

Edit A — add the import. After the existing line
`import { renderUsers } from "./users.js";` add:

```js
import { renderServers } from "./servers.js";
```

Edit B — add a sidebar entry. In `loadSidebar`, the Users item is built by:

```js
  const usersBtn = document.createElement("div");
  usersBtn.className = "tree-item";
  usersBtn.textContent = "▸ Users";
  usersBtn.onclick = () => renderUsers();
  sidebar.append(usersBtn);
```

Immediately after `sidebar.append(usersBtn);`, add:

```js

  const serversBtn = document.createElement("div");
  serversBtn.className = "tree-item";
  serversBtn.textContent = "▸ Servers";
  serversBtn.onclick = () => renderServers();
  sidebar.append(serversBtn);
```

- [ ] **Step 3: Verify**

Confirm `GET /static/servers.js` returns 200 and contains `renderServers`,
and `GET /static/app.js` contains `import { renderServers }` and `▸ Servers`.
Run `pytest -q` — backend suite passes.

- [ ] **Step 4: Commit**

```bash
git add src/dbmanager/web/servers.js src/dbmanager/web/app.js
git commit -m "feat: servers management page"
```

---

## Task 7: Top-bar server picker (frontend)

**Files:** Modify `src/dbmanager/web/app.js`.

- [ ] **Step 1: Replace the server-label fill in `showApp` with a picker**

In `src/dbmanager/web/app.js`, the `showApp` function currently ends with a
`try` block that fetches `/api/server-info` and sets `#server-label`'s text:

```js
  await loadSidebar();
  try {
    const info = await get("/api/server-info");
    document.getElementById("server-label").textContent =
      info.host ? `${info.host}:${info.port}` : "";
  } catch { /* label is cosmetic — ignore failures */ }
}
```

Replace that `try`/`catch` block (keep the `await loadSidebar();` line) with a
call to `renderServerPicker()`:

```js
  await loadSidebar();
  await renderServerPicker();
}

// Build the top-bar server picker from the registry.
async function renderServerPicker() {
  const label = document.getElementById("server-label");
  label.innerHTML = "";
  let servers, active;
  try {
    servers = await get("/api/servers");
    active = await get("/api/active-server");
  } catch { return; }
  if (!servers.length) {
    label.textContent = "no servers";
    return;
  }
  const select = document.createElement("select");
  for (const s of servers) {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = s.label;
    select.append(opt);
  }
  if (active.id != null) select.value = String(active.id);
  select.onchange = async () => {
    try {
      await post("/api/active-server", { server_id: Number(select.value) });
      await loadSidebar();
    } catch (e) { showError(e.message); }
  };
  label.append(select);
}
```

- [ ] **Step 2: Verify**

Confirm `GET /static/app.js` returns 200 and contains `renderServerPicker`
and `/api/active-server`. Run `pytest -q` — backend suite passes.

Then a manual check (a dev server is typically running): log in, confirm the
top bar shows a server dropdown; switching it reloads the database tree.

- [ ] **Step 3: Commit**

```bash
git add src/dbmanager/web/app.js
git commit -m "feat: top-bar server picker"
```

---

# Self-Review Notes

- **Spec coverage:** `servers` table (Task 2); Fernet encryption with an
  `APP_SECRET`-derived key (Task 1); `serverdb` data layer incl. `conninfo_for`
  and one-default invariant (Task 2); active-server dependency + route refactor
  (Task 4); registry CRUD + test + active-server endpoints (Task 5); setup
  migration that seeds from `DATABASE_URL` (Task 3); Servers management page
  (Task 6); top-bar picker (Task 7); `DATABASE_URL` made optional (Task 4).
- **Green between tasks:** Tasks 1–3 are additive. Task 4 is the atomic
  cutover — `config.py`, `deps.py`, all four routers, `server-info`, and the
  `client` fixture change together. Tasks 5–7 are additive.
- **Type consistency:** `active_server` returns a maintenance conninfo
  `str`; `server_db(server)` and `target_db(server, dbname)` take it;
  `db_conn` already overrides `dbname` via `make_conninfo`. `serverdb`
  functions take a `conn`; `create_server`/`update_server` use keyword-only
  args; `public()` strips `password_enc`; `conninfo_for(server, dbname=None)`.
  Route request bodies (`ServerBody`, `ActiveServerBody`) match the `serverdb`
  signatures. The session key is `server_id`.
- **Login is unchanged:** a new session has no `server_id`; `active_server`
  falls back to the default server, so login need not set it. The picker sets
  it via `POST /api/active-server`.
