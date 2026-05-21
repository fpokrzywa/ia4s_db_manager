"""Identifier-safe SQL builders and input validation.

Every object name reaches Postgres through psycopg.sql.Identifier — never a
formatted string. Column types and default expressions cannot be parameters,
so they are validated before being placed into SQL.
"""
from __future__ import annotations
import re
from fastapi import HTTPException
from psycopg import sql as pgsql

_TYPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]*(\([0-9, ]+\))?(\[\])?$")


def validate_identifier(name: str, label: str) -> str:
    """Return a stripped identifier or raise HTTP 400. Quoting handles safety;
    this is a sanity/UX check for empty and over-long names."""
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, f"{label} is required")
    if len(name.encode("utf-8")) > 63:
        raise HTTPException(400, f"{label} must be 63 bytes or fewer")
    return name


def validate_type(type_str: str) -> str:
    """Return a validated column type or raise HTTP 400."""
    type_str = (type_str or "").strip()
    if not _TYPE_RE.match(type_str):
        raise HTTPException(400, f"invalid column type: {type_str!r}")
    return type_str


def validate_default(expr: str) -> str:
    """Return a default expression or raise HTTP 400 (blocks statement breakout)."""
    expr = (expr or "").strip()
    if ";" in expr:
        raise HTTPException(400, "default expression may not contain ';'")
    return expr


def qualified(table: str, schema: str = "public") -> pgsql.Composable:
    """A schema-qualified table identifier."""
    return pgsql.Identifier(schema, table)


def create_database(name: str, owner: str | None,
                    encoding: str | None) -> pgsql.Composable:
    parts = [pgsql.SQL("CREATE DATABASE {}").format(pgsql.Identifier(name))]
    if owner:
        parts.append(pgsql.SQL("OWNER {}").format(pgsql.Identifier(owner)))
    if encoding:
        parts.append(pgsql.SQL("ENCODING {} TEMPLATE template0")
                     .format(pgsql.Literal(encoding)))
    return pgsql.SQL(" ").join(parts)


def drop_database(name: str, force: bool) -> pgsql.Composable:
    stmt = pgsql.SQL("DROP DATABASE {}").format(pgsql.Identifier(name))
    if force:
        stmt = pgsql.SQL("{} WITH (FORCE)").format(stmt)
    return stmt
