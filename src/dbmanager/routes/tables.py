"""Table list/inspect/create/rename/drop and column/constraint/index DDL."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager import sqlbuild
from dbmanager.deps import target_db
from dbmanager.inspect import list_tables, table_structure

router = APIRouter(prefix="/api/databases/{db}/tables", tags=["tables"])


class ColumnDef(BaseModel):
    name: str
    type: str
    nullable: bool = True
    default: str | None = None
    primary_key: bool = False


class CreateTableBody(BaseModel):
    name: str
    columns: list[ColumnDef]


class RenameTableBody(BaseModel):
    new_name: str


class AlterColumnBody(BaseModel):
    new_name: str | None = None
    type: str | None = None
    nullable: bool | None = None
    default: str | None = None
    drop_default: bool = False


class ConstraintBody(BaseModel):
    type: str
    columns: list[str]
    name: str | None = None
    ref_table: str | None = None
    ref_columns: list[str] | None = None


class IndexBody(BaseModel):
    name: str
    columns: list[str]
    unique: bool = False


def _run(db: str, stmts):
    """Execute one statement or a list of them in a single transaction,
    mapping Postgres errors to HTTP status codes."""
    if not isinstance(stmts, (list, tuple)):
        stmts = [stmts]
    with target_db(db) as conn:
        try:
            for stmt in stmts:
                conn.execute(stmt)
        except pgerrors.DuplicateTable as exc:
            raise HTTPException(409, str(exc)) from exc
        except pgerrors.DuplicateColumn as exc:
            raise HTTPException(409, str(exc)) from exc
        except pgerrors.UndefinedTable as exc:
            raise HTTPException(404, str(exc)) from exc
        except pgerrors.UndefinedColumn as exc:
            raise HTTPException(404, str(exc)) from exc
        except pgerrors.UndefinedObject as exc:
            raise HTTPException(404, str(exc)) from exc
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("")
def get_tables(db: str) -> list[dict]:
    with target_db(db) as conn:
        return list_tables(conn)


@router.get("/{table}")
def get_table(db: str, table: str) -> dict:
    with target_db(db) as conn:
        struct = table_structure(conn, table)
    if not struct:
        raise HTTPException(404, f"no table '{table}' in database '{db}'")
    return struct


@router.post("", status_code=201)
def create_table(db: str, body: CreateTableBody) -> dict:
    name = sqlbuild.validate_identifier(body.name, "table name")
    _run(db, sqlbuild.create_table(name, [c.model_dump() for c in body.columns]))
    return {"created": name}


@router.patch("/{table}")
def rename_table(db: str, table: str, body: RenameTableBody) -> dict:
    new_name = sqlbuild.validate_identifier(body.new_name, "new table name")
    _run(db, sqlbuild.rename_table(table, new_name))
    return {"renamed": new_name}


@router.delete("/{table}")
def drop_table(db: str, table: str) -> dict:
    _run(db, sqlbuild.drop_table(table))
    return {"dropped": table}


@router.post("/{table}/columns", status_code=201)
def add_column(db: str, table: str, body: ColumnDef) -> dict:
    sqlbuild.validate_identifier(body.name, "column name")
    _run(db, sqlbuild.add_column(table, body.model_dump()))
    return {"added": body.name}


@router.patch("/{table}/columns/{column}")
def alter_column(db: str, table: str, column: str, body: AlterColumnBody) -> dict:
    stmts = sqlbuild.alter_column(table, column, body.model_dump())
    if not stmts:
        raise HTTPException(400, "no changes requested")
    _run(db, stmts)
    return {"altered": column}


@router.delete("/{table}/columns/{column}")
def drop_column(db: str, table: str, column: str) -> dict:
    _run(db, sqlbuild.drop_column(table, column))
    return {"dropped": column}


@router.post("/{table}/constraints", status_code=201)
def add_constraint(db: str, table: str, body: ConstraintBody) -> dict:
    _run(db, sqlbuild.add_constraint(table, body.model_dump()))
    return {"added": body.name or body.type}


@router.delete("/{table}/constraints/{name}")
def drop_constraint(db: str, table: str, name: str) -> dict:
    _run(db, sqlbuild.drop_constraint(table, name))
    return {"dropped": name}


@router.post("/{table}/indexes", status_code=201)
def create_index(db: str, table: str, body: IndexBody) -> dict:
    sqlbuild.validate_identifier(body.name, "index name")
    _run(db, sqlbuild.create_index(table, body.name, body.columns, body.unique))
    return {"created": body.name}


@router.delete("/{table}/indexes/{name}")
def drop_index(db: str, table: str, name: str) -> dict:
    _run(db, sqlbuild.drop_index(name))
    return {"dropped": name}
