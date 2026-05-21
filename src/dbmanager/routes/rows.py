"""Paginated row browsing and row insert/update/delete.

Rows are identified for update/delete by their primary-key columns. A table
with no primary key is returned as a read-only grid (editable=false).
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from psycopg import errors as pgerrors, sql as pgsql
from pydantic import BaseModel

from dbmanager.deps import target_db
from dbmanager.inspect import table_structure
from dbmanager.sqlbuild import qualified

router = APIRouter(prefix="/api/databases/{db}/tables/{table}/rows", tags=["rows"])


class InsertBody(BaseModel):
    values: dict


class UpdateBody(BaseModel):
    pk: dict
    values: dict


class DeleteBody(BaseModel):
    pk: dict


def _structure_or_404(conn, db: str, table: str) -> dict:
    struct = table_structure(conn, table)
    if not struct:
        raise HTTPException(404, f"no table '{table}' in database '{db}'")
    return struct


@router.get("")
def list_rows(db: str, table: str, page: int = 1, page_size: int = 50,
              filter_column: str | None = None,
              filter_value: str | None = None) -> dict:
    """A page of rows, plus total count and primary-key metadata."""
    page = max(page, 1)
    page_size = min(max(page_size, 1), 500)
    with target_db(db) as conn:
        struct = _structure_or_404(conn, db, table)
        col_names = {c["name"] for c in struct["columns"]}
        pk = struct["primary_key"]

        where = pgsql.SQL("")
        params: list = []
        if filter_column and filter_value is not None:
            if filter_column not in col_names:
                raise HTTPException(400, f"unknown column: {filter_column}")
            where = pgsql.SQL(" WHERE CAST({} AS text) ILIKE {}").format(
                pgsql.Identifier(filter_column), pgsql.Placeholder())
            params.append(f"%{filter_value}%")

        total = conn.execute(
            pgsql.SQL("SELECT count(*) AS n FROM {}{}").format(
                qualified(table), where), params).fetchone()["n"]

        order = (pgsql.SQL(" ORDER BY {}").format(
                    pgsql.SQL(", ").join(pgsql.Identifier(c) for c in pk))
                 if pk else pgsql.SQL(""))
        rows = conn.execute(
            pgsql.SQL("SELECT * FROM {}{}{} LIMIT {} OFFSET {}").format(
                qualified(table), where, order,
                pgsql.Placeholder(), pgsql.Placeholder()),
            params + [page_size, (page - 1) * page_size]).fetchall()

    return {"columns": [c["name"] for c in struct["columns"]],
            "rows": rows, "total": total, "page": page, "page_size": page_size,
            "primary_key": pk, "editable": bool(pk)}


@router.post("", status_code=201)
def insert_row(db: str, table: str, body: InsertBody) -> dict:
    if not body.values:
        raise HTTPException(400, "no values supplied")
    cols = list(body.values)
    stmt = pgsql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
        qualified(table),
        pgsql.SQL(", ").join(pgsql.Identifier(c) for c in cols),
        pgsql.SQL(", ").join(pgsql.Placeholder() for _ in cols))
    with target_db(db) as conn:
        try:
            row = conn.execute(stmt, [body.values[c] for c in cols]).fetchone()
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"inserted": row}


@router.patch("")
def update_row(db: str, table: str, body: UpdateBody) -> dict:
    if not body.pk:
        raise HTTPException(400, "primary-key values are required to update a row")
    if not body.values:
        raise HTTPException(400, "no values supplied")
    vcols, pcols = list(body.values), list(body.pk)
    stmt = pgsql.SQL("UPDATE {} SET {} WHERE {} RETURNING *").format(
        qualified(table),
        pgsql.SQL(", ").join(
            pgsql.SQL("{} = {}").format(pgsql.Identifier(c), pgsql.Placeholder())
            for c in vcols),
        pgsql.SQL(" AND ").join(
            pgsql.SQL("{} = {}").format(pgsql.Identifier(c), pgsql.Placeholder())
            for c in pcols))
    params = [body.values[c] for c in vcols] + [body.pk[c] for c in pcols]
    with target_db(db) as conn:
        try:
            row = conn.execute(stmt, params).fetchone()
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    if row is None:
        raise HTTPException(404, "no row matched the supplied primary key")
    return {"updated": row}


@router.delete("")
def delete_row(db: str, table: str, body: DeleteBody) -> dict:
    if not body.pk:
        raise HTTPException(400, "primary-key values are required to delete a row")
    pcols = list(body.pk)
    stmt = pgsql.SQL("DELETE FROM {} WHERE {} RETURNING *").format(
        qualified(table),
        pgsql.SQL(" AND ").join(
            pgsql.SQL("{} = {}").format(pgsql.Identifier(c), pgsql.Placeholder())
            for c in pcols))
    with target_db(db) as conn:
        try:
            row = conn.execute(stmt, [body.pk[c] for c in pcols]).fetchone()
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    if row is None:
        raise HTTPException(404, "no row matched the supplied primary key")
    return {"deleted": row}
