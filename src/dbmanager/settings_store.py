"""Generic key/value store backed by the app_settings table in common_data.

Values are JSONB; callers pass and receive plain Python dicts."""
from __future__ import annotations
import json


def get_setting(conn, key: str) -> dict | None:
    """Return the value for `key` as a dict, or None if not set.

    Callers must pass a connection with `row_factory=dict_row` — both
    `authdb.auth_conn` and the pooled `common_data_pool` connections do."""
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = %s", (key,)).fetchone()
    return row["value"] if row is not None else None


def set_setting(conn, key: str, value: dict) -> None:
    """Insert-or-update the value for `key`. `value` is a dict that will be
    JSON-encoded into the JSONB column."""
    conn.execute("""
        INSERT INTO app_settings (key, value)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = now()
    """, (key, json.dumps(value)))
