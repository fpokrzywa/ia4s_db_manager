"""Introspection queries against pg_catalog / information_schema."""
from __future__ import annotations

_DATABASES = """
    SELECT d.datname AS name,
           pg_get_userbyid(d.datdba) AS owner,
           pg_encoding_to_char(d.encoding) AS encoding,
           pg_database_size(d.datname) AS size_bytes
    FROM pg_database d
    WHERE d.datistemplate = false
    ORDER BY d.datname
"""

_TABLES = """
    SELECT t.table_name AS name,
           c.reltuples::bigint AS approx_rows,
           pg_total_relation_size(c.oid) AS size_bytes
    FROM information_schema.tables t
    JOIN pg_class c ON c.relname = t.table_name
    JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = t.table_schema
    WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
    ORDER BY t.table_name
"""

_COLUMNS = """
    SELECT column_name AS name, data_type, is_nullable,
           column_default, ordinal_position
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = %s
    ORDER BY ordinal_position
"""

_PRIMARY_KEY = """
    SELECT kcu.column_name AS name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON kcu.constraint_name = tc.constraint_name
     AND kcu.table_schema = tc.table_schema
    WHERE tc.table_schema = 'public' AND tc.table_name = %s
      AND tc.constraint_type = 'PRIMARY KEY'
    ORDER BY kcu.ordinal_position
"""

_CONSTRAINTS = """
    SELECT conname AS name,
           CASE contype WHEN 'p' THEN 'PRIMARY KEY'
                        WHEN 'f' THEN 'FOREIGN KEY'
                        WHEN 'u' THEN 'UNIQUE'
                        WHEN 'c' THEN 'CHECK' END AS type,
           pg_get_constraintdef(oid) AS definition
    FROM pg_constraint
    WHERE conrelid = ('public.' || quote_ident(%s))::regclass
    ORDER BY conname
"""

_INDEXES = """
    SELECT indexname AS name, indexdef AS definition
    FROM pg_indexes
    WHERE schemaname = 'public' AND tablename = %s
    ORDER BY indexname
"""


def list_databases(conn) -> list[dict]:
    return conn.execute(_DATABASES).fetchall()


def list_tables(conn) -> list[dict]:
    return conn.execute(_TABLES).fetchall()


def table_structure(conn, table: str) -> dict:
    """Columns, primary-key column names, constraints, and indexes."""
    columns = conn.execute(_COLUMNS, (table,)).fetchall()
    if not columns:
        return {}
    pk = [r["name"] for r in conn.execute(_PRIMARY_KEY, (table,)).fetchall()]
    constraints = conn.execute(_CONSTRAINTS, (table,)).fetchall()
    indexes = conn.execute(_INDEXES, (table,)).fetchall()
    return {"name": table, "columns": columns, "primary_key": pk,
            "constraints": constraints, "indexes": indexes}
