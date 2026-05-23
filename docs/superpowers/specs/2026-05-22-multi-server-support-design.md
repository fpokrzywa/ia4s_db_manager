# Multi-Server Support — Design

**Date:** 2026-05-22
**Status:** Approved for planning
**Builds on:** `2026-05-21-postgres-database-manager-design.md`,
`2026-05-21-multi-user-auth-design.md`

## Purpose

Today the app connects to one Postgres server, hardwired via `DATABASE_URL`
in `.env`. This feature makes the app reusable across many servers: a
**registry of servers** managed in-app, a **top-bar picker** to choose the
server the current session works on, and connection passwords **encrypted at
rest**. Every database/table/row/SQL-console operation targets the selected
server.

`common_data` remains the app's fixed "home" database — it holds the `users`,
`user_sessions`, and (new) `servers` tables. The registry holds the *managed*
servers, which are separate from the home database.

## The `servers` table (in `common_data`)

| column | type | notes |
|---|---|---|
| `id` | `serial` PK | |
| `label` | `text` UNIQUE NOT NULL | display name shown in the picker |
| `host` | `text` NOT NULL | |
| `port` | `integer` NOT NULL DEFAULT 5432 | |
| `username` | `text` NOT NULL | the Postgres role |
| `password_enc` | `text` NOT NULL | password encrypted at rest (Fernet) |
| `maintenance_db` | `text` NOT NULL DEFAULT 'postgres' | DB used for server-level ops |
| `sslmode` | `text` NOT NULL DEFAULT 'prefer' | libpq sslmode |
| `is_default` | `boolean` NOT NULL DEFAULT false | server new sessions start on |
| `notes` | `text` | optional free text |
| `created_at` | `timestamptz` NOT NULL DEFAULT now() | |
| `updated_at` | `timestamptz` NOT NULL DEFAULT now() | |

Only one row may have `is_default = true`; setting a new default clears the
flag on all others.

## Encryption

A new `crypto.py` module wraps the `cryptography` library's Fernet (new
dependency `cryptography>=42`). The Fernet key is **derived from the existing
`APP_SECRET`** (SHA-256 of `APP_SECRET` → 32 bytes → url-safe base64) — no new
`.env` variable. `encrypt(plain) -> token` and `decrypt(token) -> plain`.
Caveat to document: rotating `APP_SECRET` makes stored server passwords
undecryptable; they would need to be re-entered.

## Backend modules

- `crypto.py` — `encrypt` / `decrypt` (Fernet, key derived from `APP_SECRET`).
- `serverdb.py` — the `servers` schema DDL plus data-access functions
  (`list_servers`, `get_server`, `create_server`, `update_server`,
  `delete_server`, `default_server`); reuses `authdb.auth_conn` for the
  `common_data` connection.
- `servers.py` (logic) — resolve a server record into a usable connection:
  decrypt the password and build the maintenance / per-database conninfo
  (host, port, user, password, dbname, sslmode).
- `deps.py` — `server_db()` and `target_db(dbname)` are refactored to take a
  resolved server connection (from the active server) instead of reading
  `Settings.database_url`. `common_data` access is unchanged.
- `routes/servers.py` — the registry CRUD + test + active-server endpoints.
- The four existing resource routers (databases, tables, rows, query) inject
  the active server via a FastAPI dependency.

## The active server

- The session cookie carries `server_id`.
- A dependency `active_server` reads `session["server_id"]`, loads the server
  record from `common_data`, decrypts its password, and yields the connection
  info. If the session has no `server_id`, it falls back to the default
  server (or, if exactly one server exists, that one).
- On login, the session's `server_id` is set to the default server.
- If the registry is empty, the app shows a "no servers registered — add one"
  state and routes that need a server return a clear error.

## API

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /api/servers` | session | List servers (no decrypted passwords). |
| `POST /api/servers` | session | Add a server. |
| `PATCH /api/servers/{id}` | session | Edit a server (blank password = unchanged). |
| `DELETE /api/servers/{id}` | session | Remove a server. |
| `POST /api/servers/{id}/test` | session | Test the stored connection; returns ok / error. |
| `GET /api/active-server` | session | The session's current server `{id, label}`. |
| `POST /api/active-server` | session | Set the session's active server `{server_id}`. |

`GET /api/servers` never returns `password_enc` or any decrypted password. The
existing `/api/server-info` returns the active server's host/port.

## Frontend

- A **"Servers"** entry in the sidebar opens a management page (`web/servers.js`):
  a table of registered servers (label, host:port, username, default, ssl) with
  **Add**, **Edit**, **Delete**, and **Test connection** actions. The add/edit
  dialog has fields: Label, Host, Port, Username, Password, Maintenance
  database, SSL mode, Default (checkbox), Notes. On edit, a blank Password
  field leaves the stored password unchanged.
- A **server picker** in the top bar lists registered servers and shows the
  active one. Switching it calls `POST /api/active-server` and reloads the
  sidebar database tree for the newly selected server.

## Setup & migration

The setup command (`init-auth`, or an extended/renamed equivalent) also
creates the `servers` table. If the registry is empty and `DATABASE_URL` is
present in `.env`, it auto-registers that server as the first entry
(`is_default = true`, label derived from the host), so existing deployments
keep working with no manual step. After migration, `DATABASE_URL` is only a
one-time seed — the registry is the source of truth. `DATABASE_COMMON_DATA_URL`
and `APP_SECRET` remain required.

## Access control

Consistent with the rest of the app, there are no roles — any logged-in user
can manage the registry and switch servers. (Role-restricted server
management would be a separate feature.)

## Error handling

- An unreachable active server surfaces as HTTP 503, matching the existing
  `deps.py` pattern.
- `POST /api/servers/{id}/test` returns `{ok: true}` or `{ok: false, error:
  "..."}` without raising.
- Deleting the server a session is currently on falls the session back to the
  default server on the next request.

## Testing

Auth/route tests already run against a throwaway `common_data` with seeded
schema and a test user. The test fixtures additionally seed one `servers` row
pointing at the throwaway Postgres, and the `client` fixture's session is set
to it — so the refactored route layer resolves a real connection. Unit tests
cover `crypto.py` (encrypt/decrypt round-trip) and `serverdb.py`.

## Build phases

The implementation plan is organized as roughly ten tasks:

1. `crypto.py` (Fernet encryption) + `cryptography` dependency.
2. `serverdb.py` — `servers` schema + data-access.
3. `servers.py` — resolve a server record into a connection.
4. Active-server dependency + `deps.py` refactor.
5. Refactor the four resource routers to use the active server.
6. `routes/servers.py` — registry CRUD + test + active-server endpoints.
7. Setup migration — create the `servers` table, seed from `DATABASE_URL`.
8. Update test fixtures for the active-server model.
9. Frontend — the Servers management page.
10. Frontend — the top-bar server picker.

## Out of scope

Connection pooling, SSH tunnels, read-only/credential scoping per server, and
roles for server management are not included.
