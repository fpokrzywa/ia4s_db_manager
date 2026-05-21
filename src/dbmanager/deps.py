"""Request-scoped database context managers for the route layer."""
from __future__ import annotations
from contextlib import contextmanager
from fastapi import HTTPException
from dbmanager.config import Settings
from dbmanager.db import server_conn, db_conn


@contextmanager
def server_db():
    """Autocommit connection to the maintenance database, or HTTP 503."""
    settings = Settings.from_env()
    try:
        with server_conn(settings.database_url) as conn:
            yield conn
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database error: {exc}") from exc


@contextmanager
def target_db(dbname: str):
    """Transactional connection to `dbname`, or HTTP 503."""
    settings = Settings.from_env()
    try:
        with db_conn(settings.database_url, dbname) as conn:
            yield conn
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database error: {exc}") from exc
