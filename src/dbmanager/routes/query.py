"""SQL console — runs arbitrary SQL against a chosen database."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager.deps import active_server, target_db

router = APIRouter(prefix="/api/databases/{db}/query", tags=["query"])


class QueryBody(BaseModel):
    sql: str


@router.post("")
def run_query(db: str, body: QueryBody,
              server: str = Depends(active_server)) -> dict:
    """Execute `body.sql`. Result sets return columns+rows; other statements
    return an affected-row count. The transaction commits on success."""
    statement = body.sql.strip()
    if not statement:
        raise HTTPException(400, "no SQL provided")
    with target_db(server, db) as conn:
        try:
            cur = conn.execute(statement)
        except pgerrors.Error as exc:
            raise HTTPException(400, str(exc)) from exc
        if cur.description is None:
            return {"columns": [], "rows": [], "rowcount": cur.rowcount,
                    "message": f"{cur.rowcount} row(s) affected"}
        rows = cur.fetchall()
        columns = [d.name for d in cur.description]
    return {"columns": columns, "rows": rows, "rowcount": len(rows),
            "message": f"{len(rows)} row(s)"}
