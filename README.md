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
