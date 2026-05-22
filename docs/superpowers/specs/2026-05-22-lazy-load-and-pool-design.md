# Lazy-Load Sidebar Tables & Connection Pooling — Design

**Date:** 2026-05-22
**Status:** Approved for planning
**Builds on:** multi-server support (`2026-05-22-multi-server-support-design.md`), server UX improvements (`2026-05-22-server-ux-improvements-design.md` — the collapsible sidebar).

A performance pass with two independent but related changes: (A) the sidebar
fetches each database's tables only when expanded, and (B) Postgres
connections are pooled instead of opened fresh per request.

## Problem

Measured against the registered default server (3CP Host 2, remote Postgres):

- Fresh `psycopg.connect()` → ~700 ms (TCP + auth + libpq startup).
- A query once connected → tens of ms.

Every API request opens **two** fresh connections — `active_server` to
`common_data` for the server lookup, then `server_db`/`target_db` to the
active server for the actual work. **One API request ≈ ~1.4 s before any
query runs.**

Sidebar load: `GET /api/databases` (1) + `GET /api/databases/{db}/tables`
(× N databases) = 1 + N requests ≈ **~7 s** for 4 databases. The full test
suite (~11 min) is dominated by the same per-test connection overhead.

## Feature A: Lazy-load sidebar tables

`loadSidebar` is rewritten so each database's table list is fetched only
when the user needs it:

- `loadSidebar` makes ONE backend request: `GET /api/databases`.
- For each database, build the row (`dbEl`) and an empty `tablesEl`
  container. If the database is in `expandedDbs` (previously opened by the
  user this session), fetch its tables eagerly so it renders expanded.
- Toggling a collapsed database for the first time triggers
  `GET /api/databases/{db}/tables`, populates `tablesEl`, then shows it. A
  "Loading…" placeholder is shown in `tablesEl` while the request is in
  flight.
- Toggling a database whose tables are already loaded (within the same
  `loadSidebar` lifetime) just shows/hides; no re-fetch.
- After a sidebar rebuild (next `loadSidebar` call), all `tablesEl` start
  empty again. Previously-expanded databases (still in `expandedDbs`) are
  re-fetched eagerly to match today's "tables visible for open DBs"
  behavior.

No backend change. No automated frontend test (consistent with the rest of
the frontend). `node --check src/dbmanager/web/app.js` plus the unchanged
backend suite.

## Feature B: Connection pooling

### New module `src/dbmanager/pools.py`

Three pool-borrowing helpers, each backed by a
`psycopg_pool.ConnectionPool`:

| Helper | Keyed on | Used by | Connection mode |
|---|---|---|---|
| `common_data_pool()` | `Settings.from_env().common_data_url` | `active_server`, `routes/servers.py` | autocommit |
| `server_pool(server_conninfo)` | server conninfo string | `server_db` (CREATE/DROP DATABASE) | autocommit |
| `target_pool(server_conninfo, dbname)` | `(server_conninfo, dbname)` | `target_db` (tables/rows/query) | transactional |

Pool settings:

- `min_size=1, max_size=4, max_idle=300` (5 minutes idle before a
  connection closes).
- `timeout=10` on `pool.connection()` acquire (raises `PoolTimeout` if no
  connection becomes available within 10 s — surfaces as 503 via the
  existing `deps.py` error-mapping).
- Autocommit pools set `autocommit=True` via the pool's `configure` callback
  so every borrowed connection is autocommit. Transactional pools leave the
  default; psycopg_pool auto-rolls-back any open transaction on release, so
  a route that raises mid-transaction does not poison the pool.

A module-level registry tracks every created pool. `close_all()` closes them
— called by FastAPI shutdown and the test-session teardown fixture.

The `target_pool` cache is **LRU-bounded to 8 entries**. When the 9th
(server, dbname) combination is requested, the least-recently-used pool is
evicted and closed gracefully. This bounds memory use for users who browse
many databases.

### `deps.py` refactor

- `active_server`: replaces `with authdb.auth_conn(...)` with
  `with common_data_pool().connection() as conn:`. The lookup, fallback to
  `default_server`, and 503 behavior are unchanged.
- `server_db(server)`: yields a connection from `server_pool(server)`
  instead of calling `server_conn(server)`. Same outer try/except shape
  (HTTPException passthrough, generic Exception → 503).
- `target_db(server, dbname)`: yields a connection from
  `target_pool(server, dbname)` instead of calling `db_conn(server, dbname)`.
  Same outer try/except shape.

### `webapp.py` lifespan

A FastAPI `lifespan` async context manager:

- Startup: eagerly opens `common_data_pool()` so the most-used pool is warm
  before the first request.
- Shutdown: calls `pools.close_all()`.

Registered via `FastAPI(..., lifespan=lifespan)`.

### `db.py` (the existing `server_conn`, `db_conn` helpers)

UNCHANGED. They remain available for non-route callers — `cli.py`'s
`init-auth` (a one-shot CLI invocation with no FastAPI lifecycle), and any
direct tests or scripts that build conninfos.

### Tests

- Existing tests already exercise every DB path through `deps`; with
  pooling they should pass unchanged.
- New `tests/test_pools.py`: confirms `common_data_pool()` returns the same
  pool object on repeated calls for the same URL; confirms `close_all()`
  closes the registered pools and clears the registry; confirms
  `target_pool` LRU eviction closes the evicted pool.
- `tests/conftest.py`: a session-scoped autouse fixture calls
  `pools.close_all()` at teardown so accumulated pools (one per unique
  throwaway-DB URL across the test session) are released.
- Realistic projection: per-test handshake overhead falls from ~7 s of cold
  connects to ~50 ms of pool reuse. The full suite should drop from ~11
  minutes to roughly **~1 minute**, with significant variance.

### Dependency

`pyproject.toml`: add `"psycopg-pool>=3.2"` to the `[project]`
dependencies.

## Scope / non-goals

- Async psycopg is not used; the sync `psycopg_pool.ConnectionPool` is the
  right choice.
- No additional active-server-resolution caching beyond what pooling
  provides — with the common_data pool warm, the lookup is ~50 ms, fast
  enough; deeper caching adds invalidation complexity for marginal gain.
- The `_settings = Settings.from_env()` line at `webapp.py` module level
  (used for `SessionMiddleware`'s `secret_key`) is unchanged.

## Implementation order

A (lazy-load) ships first as one isolated frontend task. B (pooling)
follows as a sequence of backend tasks: pools module + tests, `deps.py`
refactor, `webapp.py` lifespan + conftest teardown.
