"""Database Manager — FastAPI app: login, static files, routers."""
from __future__ import annotations
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from dbmanager.auth import password_matches
from dbmanager.config import Settings
from psycopg.conninfo import conninfo_to_dict

WEB_DIR = Path(__file__).resolve().parent / "web"
_settings = Settings.from_env()

app = FastAPI(title="Database Manager", docs_url="/api/docs", redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=_settings.app_secret,
                   https_only=False)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


class LoginBody(BaseModel):
    password: str


@app.post("/api/login")
def login(body: LoginBody, request: Request) -> dict:
    """Check the password and start a session."""
    app_password = os.environ.get("APP_PASSWORD", "")
    if not password_matches(body.password, app_password):
        raise HTTPException(status_code=401, detail="incorrect password")
    request.session["authenticated"] = True
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request) -> dict:
    """End the session."""
    request.session.clear()
    return {"ok": True}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the single-page app shell."""
    return FileResponse(WEB_DIR / "index.html")


# --- routers (added in later phases) ----------------------------------------
# ROUTER REGISTRATION MARKER — do not remove
from fastapi import Depends
from dbmanager.auth import require_session
from dbmanager.routes import databases
from dbmanager.routes import tables
from dbmanager.routes import rows
from dbmanager.routes import query

app.include_router(databases.router, dependencies=[Depends(require_session)])
app.include_router(tables.router, dependencies=[Depends(require_session)])
app.include_router(rows.router, dependencies=[Depends(require_session)])
app.include_router(query.router, dependencies=[Depends(require_session)])


@app.get("/api/server-info", dependencies=[Depends(require_session)])
def server_info() -> dict:
    """Host and port of the configured Postgres server — no credentials."""
    info = conninfo_to_dict(Settings.from_env().database_url)
    return {"host": info.get("host") or "", "port": info.get("port") or ""}
