"""Session routes — login, logout, current user, password change."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from dbmanager import auth, authdb
from dbmanager.config import Settings

router = APIRouter(prefix="/api", tags=["session"])


class LoginBody(BaseModel):
    email: str
    password: str


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


def _client(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


@router.post("/login")
def login(body: LoginBody, request: Request) -> dict:
    """Authenticate with email + password and start a session."""
    settings = Settings.from_env()
    ip, ua = _client(request)
    result = auth.authenticate(settings.common_data_url, body.email,
                               body.password, ip, ua)
    request.session["user_id"] = result.user_id
    request.session["email"] = result.email
    return {"ok": True, "must_change_password": result.must_change_password}


@router.post("/logout")
def logout(request: Request) -> dict:
    """End the session, recording a logout audit event."""
    user_id = request.session.get("user_id")
    email = request.session.get("email")
    if user_id and email:
        settings = Settings.from_env()
        ip, ua = _client(request)
        with authdb.auth_conn(settings.common_data_url) as conn:
            authdb.record_event(conn, email=email, user_id=user_id,
                                event="logout", ip_address=ip, user_agent=ua)
    request.session.clear()
    return {"ok": True}


@router.get("/me", dependencies=[Depends(auth.require_session)])
def me(request: Request) -> dict:
    """The current user, password-change flag, and admin flag."""
    settings = Settings.from_env()
    with authdb.auth_conn(settings.common_data_url) as conn:
        user = authdb.get_user_by_id(conn, request.session["user_id"])
    if user is None:
        request.session.clear()
        raise HTTPException(401, "authentication required")
    return {"email": user["email"],
            "must_change_password": user["must_change_password"],
            "is_admin": user["is_admin"]}


@router.post("/change-password",
             dependencies=[Depends(auth.require_session)])
def change_password(body: ChangePasswordBody, request: Request) -> dict:
    """Change the current user's password."""
    settings = Settings.from_env()
    ip, ua = _client(request)
    auth.change_password(settings.common_data_url, request.session["user_id"],
                         body.current_password, body.new_password, ip, ua)
    return {"ok": True}
