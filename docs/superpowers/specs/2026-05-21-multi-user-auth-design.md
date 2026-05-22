# Multi-User Login & Audit Logging — Design

**Date:** 2026-05-21
**Status:** Approved for planning
**Builds on:** `2026-05-21-postgres-database-manager-design.md`

## Purpose

Replace the single shared `APP_PASSWORD` login with per-user accounts
(email + bcrypt-hashed password) stored in the `common_data` database, add an
append-only auth-event audit log, force a password change on first login, lock
accounts after repeated failures, and provide an in-app Users management page.

A dedicated auth framework (`fastapi-users`) was considered and rejected as
overkill for a small internal tool; a minimal custom layer over the app's
existing signed-cookie sessions is simpler and fits the codebase.

## Database schema

Two new tables, created in the `common_data` database (reached via
`DATABASE_COMMON_DATA_URL`). The app's database-management features are
unaffected — the auth layer always connects to `common_data` for user and
audit data, independent of whichever database the operator is browsing.

### `users`

| column | type | notes |
|---|---|---|
| `id` | `serial` PRIMARY KEY | |
| `email` | `text` UNIQUE NOT NULL | login identity; stored lowercased |
| `password_hash` | `text` NOT NULL | bcrypt |
| `must_change_password` | `boolean` NOT NULL DEFAULT true | |
| `is_active` | `boolean` NOT NULL DEFAULT true | deactivate rather than delete |
| `failed_attempts` | `integer` NOT NULL DEFAULT 0 | consecutive failures |
| `locked_until` | `timestamptz` NULL | set while locked |
| `last_login_at` | `timestamptz` NULL | |
| `created_at` | `timestamptz` NOT NULL DEFAULT now() | |
| `updated_at` | `timestamptz` NOT NULL DEFAULT now() | |

### `user_sessions`

The append-only auth-event audit log.

| column | type | notes |
|---|---|---|
| `id` | `bigserial` PRIMARY KEY | |
| `user_id` | `integer` NULL REFERENCES `users(id)` | null when the email matched no user |
| `email` | `text` NOT NULL | the email used in the attempt |
| `event` | `text` NOT NULL | one of `login_success`, `login_failed`, `logout`, `password_changed`, `account_locked` |
| `ip_address` | `text` NULL | from the request |
| `user_agent` | `text` NULL | from the request |
| `created_at` | `timestamptz` NOT NULL DEFAULT now() | |

## Backend modules

- `config.py` — add `common_data_url` from `DATABASE_COMMON_DATA_URL`; remove
  `app_password` (no longer used); keep `app_secret`.
- `passwords.py` — `hash_password(plain)` and `verify_password(plain, hash)`
  using the `bcrypt` package (new dependency `bcrypt>=4.0`).
- `authdb.py` — the auth schema DDL (a module constant), a connection helper
  to `common_data`, and the data-access functions: get user by email, create
  user, update password, list users, update user (active flag / unlock /
  password reset), record an audit event, increment failed attempts.
- `auth.py` — orchestration: `authenticate(email, password, ip, user_agent)`
  (verify hash, handle lockout, write the audit event) and
  `change_password(...)`; the existing `require_session` dependency stays. The
  session cookie stores `user_id` and `email`.
- `routes/session.py` — `POST /api/login`, `POST /api/logout`,
  `GET /api/me`, `POST /api/change-password`.
- `routes/users.py` — `GET /api/users`, `POST /api/users`,
  `PATCH /api/users/{id}`.
- `cli.py` — a new `init-auth` command that creates the two tables in
  `common_data` (idempotent) and seeds the first user.

## Behavior

- **Login** — email + password. The email is lowercased. On success: set the
  session, reset `failed_attempts` to 0, set `last_login_at`, audit
  `login_success`; the response reports whether `must_change_password` is set.
  On failure: audit `login_failed`, increment `failed_attempts`.
- **Lockout** — after 5 consecutive failed attempts, set
  `locked_until = now() + 15 minutes` and audit `account_locked`. A login
  while locked is refused with a clear message and does not reveal whether the
  password was correct.
- **Inactive accounts** — `is_active = false` users cannot log in.
- **Forced password change** — when `must_change_password` is true, the UI
  shows a change-password screen and blocks all other use until it is done.
  `POST /api/change-password` verifies the current password, requires the new
  password to be at least 8 characters and different from the current one,
  updates the hash, clears the flag, and audits `password_changed`.
- **Users page** — any logged-in user may add a user (email + temporary
  password, `must_change_password = true`), deactivate/reactivate a user,
  reset a user's password (sets a new temporary password and the flag), and
  unlock a locked account. There is no hard delete. Anyone who can log in
  already has full database power, so no separate admin role exists.

## API

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /api/login` | open | Authenticate with email + password. |
| `POST /api/logout` | open | Clear the session; audit `logout`. |
| `GET /api/me` | session | Current user `{email, must_change_password}`. |
| `POST /api/change-password` | session | Change own password. |
| `GET /api/users` | session | List users (no hashes). |
| `POST /api/users` | session | Create a user. |
| `PATCH /api/users/{id}` | session | Deactivate/reactivate, reset password, unlock. |

The four existing resource routers (databases, tables, rows, query) keep their
`require_session` guard unchanged.

## Frontend

- The login form gains an **email** field above the password field.
- A **change-password screen** appears after login whenever the server reports
  `must_change_password`.
- A **"Users"** item in the sidebar opens a Users management panel
  (`web/users.js`): a table of users with add / deactivate / reset / unlock
  actions.

## Configuration

`.env` after this change requires:

```
DATABASE_URL=postgresql://.../postgres
DATABASE_COMMON_DATA_URL=postgresql://.../common_data
APP_SECRET=<random 32+ char string>
```

`APP_PASSWORD` is no longer used and is removed from `.env.example`.

## Setup & the first user

A one-time command — `dbmanager init-auth --email <email> --password <temp>` —
creates the `users` and `user_sessions` tables in `common_data` (using
`CREATE TABLE IF NOT EXISTS`) and inserts the first user with the bcrypt hash
of the supplied temporary password and `must_change_password = true`. The
plaintext password is passed as a CLI argument and is never stored in the
repository. The first user is `freddie@3cpublish.com`.

## Testing

Auth integration tests run against a **throwaway** database (the existing
`pytest-postgresql` noproc fixture's test database), never the real
`common_data`: the test setup applies the auth schema DDL to that database and
seeds a known test user. `tests/conftest.py` and every existing route test's
`client` fixture are updated to log in with the test user's email + password
instead of the removed single password. Unit tests cover `passwords.py`
(hash/verify) and the lockout logic.

## Build phases

The implementation plan is organized as roughly nine tasks:

1. `config.py` change + `passwords.py` (bcrypt) + tests.
2. `authdb.py` — schema DDL, `common_data` connection, data-access functions.
3. `auth.py` — `authenticate` with lockout, `change_password`.
4. `init-auth` CLI command.
5. `routes/session.py` — login / logout / me / change-password.
6. `routes/users.py` — users CRUD.
7. Update `conftest.py` and all existing test fixtures for the new login.
8. Frontend — login email field + change-password screen.
9. Frontend — Users management page.

## Out of scope

Self-service signup, email verification, password-reset-by-email, and
multi-factor authentication are not included.
