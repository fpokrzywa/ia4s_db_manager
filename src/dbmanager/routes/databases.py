"""Database list / create / drop."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager import sqlbuild
from dbmanager.deps import server_db
from dbmanager.inspect import list_databases

router = APIRouter(prefix="/api/databases", tags=["databases"])


class CreateDatabaseBody(BaseModel):
    name: str
    owner: str | None = None
    encoding: str | None = None


@router.get("")
def get_databases() -> list[dict]:
    """Every non-template database with owner, encoding, and size."""
    with server_db() as conn:
        return list_databases(conn)


@router.post("", status_code=201)
def create_database(body: CreateDatabaseBody) -> dict:
    """Create a database."""
    name = sqlbuild.validate_identifier(body.name, "database name")
    owner = body.owner.strip() if body.owner and body.owner.strip() else None
    encoding = body.encoding.strip() if body.encoding and body.encoding.strip() else None
    stmt = sqlbuild.create_database(name, owner, encoding)
    with server_db() as conn:
        try:
            conn.execute(stmt)
        except pgerrors.DuplicateDatabase as exc:
            raise HTTPException(409, f"database '{name}' already exists") from exc
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"created": name}


@router.delete("/{name}")
def drop_database(name: str, force: bool = False) -> dict:
    """Drop a database. `force` terminates active connections first."""
    name = sqlbuild.validate_identifier(name, "database name")
    stmt = sqlbuild.drop_database(name, force)
    with server_db() as conn:
        try:
            conn.execute(stmt)
        except pgerrors.InvalidCatalogName as exc:
            raise HTTPException(404, f"no database named '{name}'") from exc
        except pgerrors.ObjectInUse as exc:
            raise HTTPException(
                409, f"database '{name}' has active connections — retry with force"
            ) from exc
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"dropped": name}
