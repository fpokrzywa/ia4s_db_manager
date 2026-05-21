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


def _column_clause(col: dict) -> pgsql.Composable:
    """Render one column definition: "name" TYPE [NOT NULL] [DEFAULT expr]."""
    parts = [pgsql.SQL("{} ").format(pgsql.Identifier(col["name"])),
             pgsql.SQL(validate_type(col["type"]))]
    if not col.get("nullable", True):
        parts.append(pgsql.SQL(" NOT NULL"))
    default = col.get("default")
    if default not in (None, ""):
        parts.append(pgsql.SQL(" DEFAULT ") + pgsql.SQL(validate_default(default)))
    return pgsql.Composed(parts)


def create_table(name: str, columns: list[dict]) -> pgsql.Composable:
    """CREATE TABLE with an inline PRIMARY KEY for any primary-key columns."""
    if not columns:
        raise HTTPException(400, "a table needs at least one column")
    defs = [_column_clause(c) for c in columns]
    pk = [c["name"] for c in columns if c.get("primary_key")]
    if pk:
        defs.append(pgsql.SQL("PRIMARY KEY ({})").format(
            pgsql.SQL(", ").join(pgsql.Identifier(c) for c in pk)))
    return pgsql.SQL("CREATE TABLE {} ({})").format(
        qualified(name), pgsql.SQL(", ").join(defs))


def drop_table(name: str) -> pgsql.Composable:
    return pgsql.SQL("DROP TABLE {}").format(qualified(name))


def rename_table(name: str, new_name: str) -> pgsql.Composable:
    return pgsql.SQL("ALTER TABLE {} RENAME TO {}").format(
        qualified(name), pgsql.Identifier(new_name))


def add_column(table: str, col: dict) -> pgsql.Composable:
    return pgsql.SQL("ALTER TABLE {} ADD COLUMN {}").format(
        qualified(table), _column_clause(col))


def drop_column(table: str, column: str) -> pgsql.Composable:
    return pgsql.SQL("ALTER TABLE {} DROP COLUMN {}").format(
        qualified(table), pgsql.Identifier(column))


def alter_column(table: str, column: str, change: dict) -> list[pgsql.Composable]:
    """One ALTER COLUMN statement per requested change (applied in one txn)."""
    stmts: list[pgsql.Composable] = []
    base = pgsql.SQL("ALTER TABLE {} ").format(qualified(table))
    col = pgsql.Identifier(column)
    if change.get("type"):
        stmts.append(base + pgsql.SQL("ALTER COLUMN {} TYPE {}").format(
            col, pgsql.SQL(validate_type(change["type"]))))
    if change.get("nullable") is True:
        stmts.append(base + pgsql.SQL("ALTER COLUMN {} DROP NOT NULL").format(col))
    if change.get("nullable") is False:
        stmts.append(base + pgsql.SQL("ALTER COLUMN {} SET NOT NULL").format(col))
    if change.get("drop_default"):
        stmts.append(base + pgsql.SQL("ALTER COLUMN {} DROP DEFAULT").format(col))
    elif change.get("default") not in (None, ""):
        stmts.append(base + pgsql.SQL("ALTER COLUMN {} SET DEFAULT ").format(col)
                     + pgsql.SQL(validate_default(change["default"])))
    if change.get("new_name"):
        stmts.append(base + pgsql.SQL("RENAME COLUMN {} TO {}").format(
            col, pgsql.Identifier(change["new_name"])))
    return stmts


def add_constraint(table: str, body: dict) -> pgsql.Composable:
    """ADD CONSTRAINT for PRIMARY KEY, UNIQUE, or FOREIGN KEY."""
    ctype = body["type"]
    cols = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in body["columns"])
    head = pgsql.SQL("ALTER TABLE {} ADD ").format(qualified(table))
    if body.get("name"):
        head = head + pgsql.SQL("CONSTRAINT {} ").format(
            pgsql.Identifier(body["name"]))
    if ctype == "PRIMARY KEY":
        return head + pgsql.SQL("PRIMARY KEY ({})").format(cols)
    if ctype == "UNIQUE":
        return head + pgsql.SQL("UNIQUE ({})").format(cols)
    if ctype == "FOREIGN KEY":
        ref_cols = pgsql.SQL(", ").join(
            pgsql.Identifier(c) for c in body["ref_columns"])
        return head + pgsql.SQL("FOREIGN KEY ({}) REFERENCES {} ({})").format(
            cols, qualified(body["ref_table"]), ref_cols)
    raise HTTPException(400, f"unsupported constraint type: {ctype}")


def drop_constraint(table: str, name: str) -> pgsql.Composable:
    return pgsql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
        qualified(table), pgsql.Identifier(name))


def create_index(table: str, name: str, columns: list[str],
                 unique: bool) -> pgsql.Composable:
    kw = pgsql.SQL("CREATE UNIQUE INDEX" if unique else "CREATE INDEX")
    cols = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in columns)
    return pgsql.SQL("{} {} ON {} ({})").format(
        kw, pgsql.Identifier(name), qualified(table), cols)


def drop_index(name: str) -> pgsql.Composable:
    return pgsql.SQL("DROP INDEX {}").format(pgsql.Identifier(name))
