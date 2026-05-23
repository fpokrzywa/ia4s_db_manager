"""Generic key/value store backed by the app_settings table in common_data.

Values are JSONB; callers pass and receive plain Python dicts."""
from __future__ import annotations
import json


def get_setting(conn, key: str) -> dict | None:
    """Return the value for `key` as a dict, or None if not set."""
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = %s", (key,)).fetchone()
    if row is None:
        return None
    # Support both dict_row connections (keyed) and plain tuple rows.
    return row["value"] if hasattr(row, "keys") else row[0]


def set_setting(conn, key: str, value: dict) -> None:
    """Insert-or-update the value for `key`. `value` is a dict that will be
    JSON-encoded into the JSONB column."""
    conn.execute("""
        INSERT INTO app_settings (key, value)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = now()
    """, (key, json.dumps(value)))
