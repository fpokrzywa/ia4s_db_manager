"""Server registry — CRUD, connection test, and active-server selection."""
from __future__ import annotations
import re
import psycopg
from fastapi import APIRouter, HTTPException, Request
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager import authdb, serverdb
from dbmanager.config import Settings

router = APIRouter(prefix="/api", tags=["servers"])

# A conninfo-style password token, quoted ('...' with backslash escapes) or bare.
_PASSWORD_RE = re.compile(r"password\s*=\s*('(?:[^'\\]|\\.)*'|\S+)",
                          re.IGNORECASE)


def _scrub(message: str) -> str:
    """Redact any password=... token so a connection-error message never
    echoes a decrypted server password back to the client."""
    return _PASSWORD_RE.sub("password=***", message)


class ServerBody(BaseModel):
    label: str
    host: str
    port: int = 5432
    username: str
    password: str | None = None
    maintenance_db: str = "postgres"
    sslmode: str = "prefer"
    is_default: bool = False
    notes: str | None = None


class ActiveServerBody(BaseModel):
    server_id: int


class TestConnectionBody(BaseModel):
    host: str
    port: int = 5432
    username: str
    password: str
    maintenance_db: str = "postgres"
    sslmode: str = "prefer"


def _conn():
    return authdb.auth_conn(Settings.from_env().common_data_url)


@router.get("/servers")
def get_servers() -> list[dict]:
    """Every registered server (no passwords)."""
    with _conn() as conn:
        return serverdb.list_servers(conn)


@router.post("/servers", status_code=201)
def create_server(body: ServerBody) -> dict:
    if not (body.label.strip() and body.host.strip() and body.username.strip()):
        raise HTTPException(400, "label, host and username are required")
    if not body.password:
        raise HTTPException(400, "a password is required for a new server")
    with _conn() as conn:
        try:
            row = serverdb.create_server(
                conn, label=body.label.strip(), host=body.host.strip(),
                port=body.port, username=body.username.strip(),
                password=body.password,
                maintenance_db=body.maintenance_db.strip() or "postgres",
                sslmode=body.sslmode, is_default=body.is_default,
                notes=body.notes)
        except pgerrors.UniqueViolation as exc:
            raise HTTPException(
                409, f"a server labeled '{body.label}' already exists") from exc
    return serverdb.public(row)


@router.patch("/servers/{server_id}")
def update_server(server_id: int, body: ServerBody) -> dict:
    with _conn() as conn:
        if serverdb.get_server(conn, server_id) is None:
            raise HTTPException(404, f"no server with id {server_id}")
        try:
            row = serverdb.update_server(
                conn, server_id, label=body.label.strip(),
                host=body.host.strip(), port=body.port,
                username=body.username.strip(), password=body.password or None,
                maintenance_db=body.maintenance_db.strip() or "postgres",
                sslmode=body.sslmode, is_default=body.is_default,
                notes=body.notes)
        except pgerrors.UniqueViolation as exc:
            raise HTTPException(
                409, f"a server labeled '{body.label}' already exists") from exc
    return serverdb.public(row)


@router.delete("/servers/{server_id}")
def delete_server(server_id: int) -> dict:
    with _conn() as conn:
        if not serverdb.delete_server(conn, server_id):
            raise HTTPException(404, f"no server with id {server_id}")
    return {"deleted": server_id}


@router.post("/servers/test-connection")
def test_connection(body: TestConnectionBody) -> dict:
    """Try to connect using raw connection fields (before a server is saved);
    report success or the scrubbed error message. Never raises."""
    conninfo = serverdb.conninfo_from_fields(
        host=body.host, port=body.port, username=body.username,
        password=body.password, maintenance_db=body.maintenance_db,
        sslmode=body.sslmode)
    try:
        with psycopg.connect(conninfo, connect_timeout=8) as probe:
            probe.execute("SELECT 1")
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": _scrub(str(exc))}


@router.post("/servers/{server_id}/test")
def test_server(server_id: int) -> dict:
    """Try to connect to a server; report success or the error message."""
    with _conn() as conn:
        server = serverdb.get_server(conn, server_id)
    if server is None:
        raise HTTPException(404, f"no server with id {server_id}")
    try:
        with psycopg.connect(serverdb.conninfo_for(server),
                             connect_timeout=8) as probe:
            probe.execute("SELECT 1")
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": _scrub(str(exc))}


@router.get("/active-server")
def get_active_server(request: Request) -> dict:
    """The session's active server (falls back to the default)."""
    with _conn() as conn:
        sid = request.session.get("server_id")
        server = serverdb.get_server(conn, sid) if sid else None
        if server is None:
            server = serverdb.default_server(conn)
    if server is None:
        return {"id": None, "label": None}
    return {"id": server["id"], "label": server["label"]}


@router.post("/active-server")
def set_active_server(body: ActiveServerBody, request: Request) -> dict:
    with _conn() as conn:
        server = serverdb.get_server(conn, body.server_id)
    if server is None:
        raise HTTPException(404, f"no server with id {body.server_id}")
    request.session["server_id"] = server["id"]
    return {"id": server["id"], "label": server["label"]}
