"""Auth data layer — schema and queries for the users / user_sessions tables
in the common_data database. Connections are autocommit so audit-log writes
and failed-attempt counters persist even when the caller then raises."""
from __future__ import annotations
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row

AUTH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id                   serial PRIMARY KEY,
    email                text UNIQUE NOT NULL,
    password_hash        text NOT NULL,
    must_change_password boolean NOT NULL DEFAULT true,
    is_active            boolean NOT NULL DEFAULT true,
    is_admin             boolean NOT NULL DEFAULT false,
    failed_attempts      integer NOT NULL DEFAULT 0,
    locked_until         timestamptz,
    last_login_at        timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin
    boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS user_sessions (
    id          bigserial PRIMARY KEY,
    user_id     integer REFERENCES users(id),
    email       text NOT NULL,
    event       text NOT NULL,
    ip_address  text,
    user_agent  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_settings (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
"""


@contextmanager
def auth_conn(common_data_url: str):
    """Yield an autocommit connection to the common_data database."""
    conn = psycopg.connect(common_data_url, row_factory=dict_row,
                           autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def apply_schema(common_data_url: str) -> None:
    """Create the auth tables if they do not already exist."""
    with auth_conn(common_data_url) as conn:
        conn.execute(AUTH_SCHEMA_SQL)


def get_user_by_email(conn, email: str) -> dict | None:
    return conn.execute(
        "SELECT * FROM users WHERE email = %s", (email.strip().lower(),)
    ).fetchone()


def get_user_by_id(conn, user_id: int) -> dict | None:
    return conn.execute(
        "SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


def create_user(conn, email: str, password_hash: str,
                must_change: bool = True) -> dict:
    return conn.execute("""
        INSERT INTO users (email, password_hash, must_change_password)
        VALUES (%s, %s, %s) RETURNING *
    """, (email.strip().lower(), password_hash, must_change)).fetchone()


def set_password(conn, user_id: int, password_hash: str,
                 must_change: bool) -> None:
    conn.execute("""
        UPDATE users SET password_hash = %s, must_change_password = %s,
            failed_attempts = 0, locked_until = NULL, updated_at = now()
        WHERE id = %s
    """, (password_hash, must_change, user_id))


def record_event(conn, *, email: str, user_id: int | None, event: str,
                 ip_address: str | None, user_agent: str | None) -> None:
    conn.execute("""
        INSERT INTO user_sessions (user_id, email, event, ip_address, user_agent)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, email.strip().lower(), event, ip_address, user_agent))


def note_successful_login(conn, user_id: int) -> None:
    conn.execute("""
        UPDATE users SET failed_attempts = 0, locked_until = NULL,
            last_login_at = now(), updated_at = now()
        WHERE id = %s
    """, (user_id,))


def note_failed_attempt(conn, user_id: int, max_attempts: int,
                        lock_minutes: int) -> bool:
    """Increment failed attempts; lock the account when the threshold is
    reached. Returns True if the account is now locked."""
    row = conn.execute("""
        UPDATE users SET failed_attempts = failed_attempts + 1,
            updated_at = now()
        WHERE id = %s RETURNING failed_attempts
    """, (user_id,)).fetchone()
    if row["failed_attempts"] >= max_attempts:
        conn.execute("""
            UPDATE users SET locked_until = now() + make_interval(mins => %s)
            WHERE id = %s
        """, (lock_minutes, user_id))
        return True
    return False


def list_users(conn) -> list[dict]:
    return conn.execute("""
        SELECT id, email, must_change_password, is_active, is_admin,
               failed_attempts, locked_until, last_login_at, created_at
        FROM users ORDER BY email
    """).fetchall()


def update_user(conn, user_id: int, *, is_active: bool | None = None,
                unlock: bool = False) -> dict | None:
    """Set the active flag and/or clear the lock. Returns the updated row."""
    sets = []
    params: list = []
    if is_active is not None:
        sets.append("is_active = %s")
        params.append(is_active)
    if unlock:
        sets.append("failed_attempts = 0")
        sets.append("locked_until = NULL")
    if not sets:
        return get_user_by_id(conn, user_id)
    sets.append("updated_at = now()")
    params.append(user_id)
    return conn.execute(
        f"UPDATE users SET {', '.join(sets)} WHERE id = %s RETURNING *",
        params).fetchone()


def count_admins(conn) -> int:
    return conn.execute(
        "SELECT count(*) AS n FROM users WHERE is_admin").fetchone()["n"]


def set_admin(conn, user_id: int, is_admin: bool) -> dict | None:
    return conn.execute("""
        UPDATE users SET is_admin = %s, updated_at = now()
        WHERE id = %s RETURNING *
    """, (is_admin, user_id)).fetchone()
