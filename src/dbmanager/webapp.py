"""Database Manager — FastAPI app: static files and routers."""
from __future__ import annotations
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.conninfo import conninfo_to_dict
from starlette.middleware.sessions import SessionMiddleware

from dbmanager.auth import require_session
from dbmanager.config import Settings
from dbmanager.routes import databases, query, rows, session, tables

WEB_DIR = Path(__file__).resolve().parent / "web"
_settings = Settings.from_env()

app = FastAPI(title="Database Manager", docs_url="/api/docs", redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=_settings.app_secret,
                   https_only=False)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the single-page app shell."""
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/server-info", dependencies=[Depends(require_session)])
def server_info() -> dict:
    """Host and port of the configured Postgres server — no credentials."""
    info = conninfo_to_dict(Settings.from_env().database_url)
    return {"host": info.get("host") or "", "port": info.get("port") or ""}


# session router self-guards /me and /change-password; login/logout are open.
app.include_router(session.router)
app.include_router(databases.router, dependencies=[Depends(require_session)])
app.include_router(tables.router, dependencies=[Depends(require_session)])
app.include_router(rows.router, dependencies=[Depends(require_session)])
app.include_router(query.router, dependencies=[Depends(require_session)])
