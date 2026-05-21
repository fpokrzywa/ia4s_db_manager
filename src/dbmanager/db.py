"""Postgres connection helpers.

server_conn -> autocommit connection to the 'postgres' maintenance database,
used for CREATE/DROP DATABASE (which cannot run inside a transaction).
db_conn -> transactional connection to a named database, used for everything
else (table DDL, row CRUD, the SQL console).
"""
from __future__ import annotations
from contextlib import contextmanager
import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row


@contextmanager
def server_conn(database_url: str):
    """Yield an autocommit connection to the maintenance database."""
    conn = psycopg.connect(database_url, row_factory=dict_row, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def db_conn(database_url: str, dbname: str):
    """Yield a transactional connection to `dbname` on the same server."""
    conninfo = make_conninfo(database_url, dbname=dbname)
    conn = psycopg.connect(conninfo, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
