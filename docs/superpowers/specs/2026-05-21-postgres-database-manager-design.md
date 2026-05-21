# Postgres Database Manager — Design

**Date:** 2026-05-21
**Status:** Approved for planning

## 1. Purpose

A self-hosted web application that gives a single operator full CRUD control
over a Postgres server: create and drop databases, manage table structure
(columns, primary keys, foreign keys, unique constraints, indexes), edit row
data, and run arbitrary SQL. It is intended to run on the same VPS as the
Postgres server and be reached over the web behind a login.

The codebase deliberately mirrors the `news_agent` / FORGE project: a FastAPI
backend, a single static vanilla-JavaScript page, `psycopg` 3 for Postgres, a
`click` CLI, and `python-dotenv` configuration.

## 2. Scope

In scope:

- Server-level: list databases, create database, drop database.
- Table-level: list tables, inspect structure, create/rename/drop tables,
  add/alter/drop columns, manage primary keys, foreign keys, unique
  constraints, and indexes.
- Data-level: paginated/filtered row browsing, insert, update, delete.
- A raw SQL console scoped to a chosen database.
- Single-password login protecting the whole app.
- Docker + docker-compose packaging for VPS deployment.

Out of scope (YAGNI):

- Multi-user accounts and role-based UI permissions.
- Managing Postgres roles/users, extensions, tablespaces, or replication.
- Schema-qualified browsing beyond the `public` schema (see Open Decisions).
- Data import/export (CSV, dumps), query history, or saved queries.

## 3. Connection Model

Postgres has no `USE database` statement — each database requires its own
connection. The app therefore maintains two kinds of connections:

- **Server connection** — connects to the `postgres` maintenance database.
  Used to list databases and to run `CREATE DATABASE` / `DROP DATABASE`.
  Because those statements cannot run inside a transaction block, this
  connection uses `autocommit = True`.
- **Per-database connection** — connects to a specific target database. Used
  for all table introspection, DDL, row CRUD, and the SQL console. This
  connection is transactional (commit on success, rollback on error), matching
  FORGE's `connect()` helper.

`DATABASE_URL` in `.env` supplies host, port, user, and password and points at
the `postgres` database. Per-database connections are derived by substituting
the database name into that connection info (via `psycopg.conninfo`).

## 4. Architecture

### 4.1 Backend — package `dbmanager`

| Module | Responsibility |
|---|---|
| `config.py` | `Settings` dataclass loaded from `.env`: `database_url`, `app_password`, `app_secret`. Fails fast if any is missing. |
| `db.py` | `server_conn()` — autocommit connection to `postgres`. `db_conn(dbname)` — transactional connection to a named database. Both yield `dict_row` connections. |
| `sql.py` | Identifier-quoting helpers built on `psycopg.sql.Identifier`/`SQL`. Composes DDL safely; object names are never string-interpolated. |
| `inspect.py` | Introspection queries against `pg_catalog` / `information_schema`: databases (name, owner, encoding, size), tables, columns, constraints, indexes. |
| `auth.py` | Verifies the login password; provides a FastAPI dependency that rejects requests without a valid signed session cookie. |
| `webapp.py` | Builds the FastAPI app, mounts static files, includes routers, serves the SPA shell. |
| `routes/databases.py` | List / create / drop databases. |
| `routes/tables.py` | List tables, inspect structure, create/rename/drop tables, and column/constraint/index DDL. |
| `routes/rows.py` | Paginated row browsing, insert, update, delete. |
| `routes/query.py` | SQL console execution. |
| `cli.py` | `click` CLI with a `web` subcommand wrapping `uvicorn`. |

Each request opens one connection of the appropriate kind and closes it when
the request finishes, matching FORGE's per-request connection pattern.

### 4.2 Frontend — `dbmanager/web/`

A single static page: `index.html`, `app.js`, `app.css`, vanilla JavaScript,
no framework or build step. Three-pane layout:

- **Top bar** — app title, the connected server host, a logout button.
- **Left sidebar** — a tree: databases, each expandable to its tables.
  Selecting a node drives the main panel.
- **Main panel** — context-dependent:
  - Database selected → overview (size, table count, table list).
  - Table selected → **Data** tab (grid) and **Structure** tab (columns,
    constraints, indexes, with DDL controls).
  - SQL Console → a query editor plus a results area, scoped to the database
    chosen in the sidebar.

### 4.3 Authentication

- `POST /api/login` accepts a password, compares it (constant-time) to
  `APP_PASSWORD`, and on success sets a signed session cookie.
- Sessions use Starlette's `SessionMiddleware` signed with `APP_SECRET`; the
  cookie is `HttpOnly`.
- A FastAPI dependency guards every `/api/*` route except `/api/login`,
  returning `401` when the session is missing or invalid.
- `POST /api/logout` clears the session.
- The SPA shows a login screen until authenticated.

## 5. API

All routes require a valid session except `POST /api/login`.

| Method & path | Purpose |
|---|---|
| `POST /api/login` | Authenticate; set session cookie. |
| `POST /api/logout` | Clear session. |
| `GET /api/databases` | List databases with owner, encoding, size. |
| `POST /api/databases` | Create a database (name, optional owner, encoding). |
| `DELETE /api/databases/{name}` | Drop a database; optional `force` uses `WITH FORCE`. |
| `GET /api/databases/{db}/tables` | List tables in the database's `public` schema. |
| `GET /api/databases/{db}/tables/{t}` | Table structure: columns, PK, FKs, unique constraints, indexes. |
| `POST /api/databases/{db}/tables` | Create a table with an initial column list. |
| `PATCH /api/databases/{db}/tables/{t}` | Rename a table. |
| `DELETE /api/databases/{db}/tables/{t}` | Drop a table (typed confirmation required client-side). |
| `POST /api/databases/{db}/tables/{t}/columns` | Add a column. |
| `PATCH /api/databases/{db}/tables/{t}/columns/{c}` | Alter a column (type, nullable, default, rename). |
| `DELETE /api/databases/{db}/tables/{t}/columns/{c}` | Drop a column. |
| `POST /api/databases/{db}/tables/{t}/constraints` | Add a PK, FK, or unique constraint. |
| `DELETE /api/databases/{db}/tables/{t}/constraints/{name}` | Drop a constraint. |
| `POST /api/databases/{db}/tables/{t}/indexes` | Create an index. |
| `DELETE /api/databases/{db}/tables/{t}/indexes/{name}` | Drop an index. |
| `GET /api/databases/{db}/tables/{t}/rows` | Paginated, filterable rows. |
| `POST /api/databases/{db}/tables/{t}/rows` | Insert a row. |
| `PATCH /api/databases/{db}/tables/{t}/rows` | Update a row, identified by primary key. |
| `DELETE /api/databases/{db}/tables/{t}/rows` | Delete a row, identified by primary key. |
| `POST /api/databases/{db}/query` | Run arbitrary SQL against the database. |

## 6. Key Behaviors and Safety

- **Identifier safety:** every database, table, column, constraint, and index
  name is composed with `psycopg.sql` quoting. Object names are never placed
  into SQL by string formatting. All row values are passed as query
  parameters.
- **Row editing requires a primary key:** the data grid identifies a row by
  its primary-key columns for `PATCH`/`DELETE`. Tables without a primary key
  render a read-only grid with a note directing the user to the SQL console.
- **Destructive actions** — drop database, drop table, drop column, and bulk
  row deletes — require a typed-confirmation modal in the UI that echoes the
  exact object name before the request is sent.
- **Data grid:** server-side pagination with a default page size of 50 rows,
  optional per-column filtering, ordered by the primary key when one exists.
- **SQL console:** runs any statement the connected role permits — this is an
  intentional admin capability. Each execution runs against the database
  chosen in the sidebar, shown in a banner above the editor. Result sets
  return columns and rows; non-result statements return an affected-row count.
- **Error handling:** Postgres errors are surfaced to the UI with their
  message text and an appropriate HTTP status — `400` for invalid input or
  rejected SQL, `404` for a missing object, `409` for conflicts (e.g. dropping
  a database with active connections without `force`), `503` when a connection
  cannot be established. This follows FORGE's `HTTPException` conventions.

## 7. Configuration

`.env` replaces the current two-line file (which had a duplicate
`DATABASE_URL`):

```
# Point at the 'postgres' maintenance database — the app substitutes the
# database name per request for table and row operations.
DATABASE_URL=postgresql://admin:...@127.0.0.1:5432/postgres
# Password required to log in to the web UI.
APP_PASSWORD=<your login password>
# Random 32+ character string used to sign session cookies.
APP_SECRET=<random secret>
```

`Settings.from_env()` raises a clear error if any value is missing.

## 8. Deployment

- **`Dockerfile`** — a Python slim base image; installs the `dbmanager`
  package and its `web` extra; runs `uvicorn dbmanager.webapp:app`.
- **`docker-compose.yml`** — runs the app container and passes `.env` to it.
  The container reaches the host's Postgres at `127.0.0.1:5432`; the compose
  file documents both options (host networking on Linux, or
  `host.docker.internal` mapping).
- **HTTPS:** the deployment doc recommends a reverse proxy (Caddy) in front of
  the app to terminate TLS, because the login password crosses the network.
  The app itself serves plain HTTP inside the trusted boundary.

## 9. Testing

`pytest` with `pytest-postgresql`, matching FORGE's test setup:

- Unit tests for identifier quoting and DDL-statement builders in `sql.py`.
- Unit tests for `Settings.from_env()` and the auth password/session logic.
- Integration tests against a temporary Postgres for introspection
  (`inspect.py`) and row CRUD.
- An end-to-end test exercising create-database → create-table → insert →
  update → delete → drop.

## 10. Build Phases

The implementation plan will be organized into these phases:

1. Configuration, `db.py` connection helpers, `auth.py`, the FastAPI skeleton,
   and the login page.
2. Database list / create / drop (`routes/databases.py`, sidebar tree).
3. Table introspection and full DDL (`inspect.py`, `sql.py`,
   `routes/tables.py`, the Structure tab).
4. Row CRUD data grid (`routes/rows.py`, the Data tab).
5. SQL console (`routes/query.py`, the console panel).
6. Docker packaging and deployment documentation.

## 11. Open Decisions

- **Schema scope:** the design assumes the `public` schema only. Browsing and
  managing other schemas is deferred; if it is needed it becomes a follow-up.
