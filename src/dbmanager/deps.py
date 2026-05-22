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
