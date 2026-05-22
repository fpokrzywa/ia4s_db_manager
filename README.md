# Postgres Database Manager

A self-hosted web app for full CRUD over a Postgres server: create/drop
databases, manage table structure, edit rows, run SQL, and manage the people
who can log in.

## Configuration

Copy `.env.example` to `.env` and set:

- `DATABASE_URL` — connection string pointing at the **`postgres`** maintenance
  database. The app substitutes the database name per request.
- `DATABASE_COMMON_DATA_URL` — connection string for the **`common_data`**
  database, which holds the `users` and `user_sessions` (auth-audit) tables.
- `APP_SECRET` — a random 32+ character string for signing session cookies.
  Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Authentication

The app uses per-user accounts: each person logs in with their **email and
password**. Passwords are stored bcrypt-hashed in the `users` table; every
login, logout, failed attempt, lockout, and password change is recorded in the
`user_sessions` audit log. An account locks for 15 minutes after 5 consecutive
failed attempts.

### First-time setup — create the tables and the first user

Run once (the password is supplied at the command line and never stored in the
repo):

```
dbmanager init-auth --email you@example.com --password "a-temporary-password"
```

This creates the `users` and `user_sessions` tables in `common_data` and seeds
the first user, who is required to change their password on first login.

### Managing users

Any logged-in user can open the **Users** page (in the sidebar) to add users,
deactivate/reactivate them, reset a password, or unlock a locked account.

## Run locally

```
pip install -e ".[dev]"
dbmanager init-auth --email you@example.com --password "a-temporary-password"
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
cp .env.example .env       # then edit .env
dbmanager init-auth --email you@example.com --password "a-temporary-password"
docker compose up -d --build
```

The app listens on port 8000.

### HTTPS

Login credentials cross the network, so put a TLS-terminating reverse proxy in
front. Example Caddyfile:

```
db.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Caddy obtains and renews a certificate automatically. Do not expose port 8000
directly to the internet.

## Security notes

- Per-user email/password accounts gate the app; the connected Postgres role's
  privileges set the ceiling on what the app can do.
- Passwords are bcrypt-hashed; failed logins lock the account after 5 attempts.
- All authentication events are written to the `user_sessions` audit log.
- The SQL Console runs arbitrary SQL by design — that is the point of the
  tool. The login is the security boundary.
- Destructive actions (drop database/table/column, delete rows) require typed
  confirmation in the UI.
