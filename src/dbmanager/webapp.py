"""Database Manager — FastAPI app: static files and routers."""
from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.conninfo import conninfo_to_dict
from starlette.middleware.sessions import SessionMiddleware

from dbmanager import pools
from dbmanager.auth import require_session
from dbmanager.deps import active_server
from dbmanager.config import Settings
from dbmanager.routes import databases, query, rows, servers, session, tables, theme, users

WEB_DIR = Path(__file__).resolve().parent / "web"
_settings = Settings.from_env()


@asynccontextmanager
async def lifespan(_app):
    """Warm the common_data pool at startup; close all pools at shutdown."""
    pools.common_data_pool()
    yield
    pools.close_all()


app = FastAPI(title="Database Manager", docs_url="/api/docs", redoc_url=None,
              lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=_settings.app_secret,
                   https_only=False)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the single-page app shell."""
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/server-info", dependencies=[Depends(require_session)])
def server_info(server: str = Depends(active_server)) -> dict:
    """Host and port of the active Postgres server — no credentials."""
    info = conninfo_to_dict(server)
    return {"host": info.get("host") or "", "port": info.get("port") or ""}


# session router self-guards /me and /change-password; login/logout are open.
app.include_router(session.router)
app.include_router(theme.router)
app.include_router(users.router, dependencies=[Depends(require_session)])
app.include_router(servers.router, dependencies=[Depends(require_session)])
app.include_router(databases.router, dependencies=[Depends(require_session)])
app.include_router(tables.router, dependencies=[Depends(require_session)])
app.include_router(rows.router, dependencies=[Depends(require_session)])
app.include_router(query.router, dependencies=[Depends(require_session)])
