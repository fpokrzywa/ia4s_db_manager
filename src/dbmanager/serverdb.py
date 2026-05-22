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
