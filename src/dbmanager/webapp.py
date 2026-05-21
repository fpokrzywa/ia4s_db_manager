"""Database Manager — FastAPI app: login, static files, routers."""
from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from dbmanager.auth import password_matches
from dbmanager.config import Settings

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
    settings = Settings.from_env()
    if not password_matches(body.password, settings.app_password):
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
