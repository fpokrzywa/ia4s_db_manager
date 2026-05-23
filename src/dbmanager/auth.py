"""Password check and session-cookie guard."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from fastapi import HTTPException, Request

from dbmanager import authdb
from dbmanager.passwords import hash_password, verify_password


def require_session(request: Request) -> None:
    """FastAPI dependency: reject requests without a logged-in session."""
    if not request.session.get("user_id"):
        raise HTTPException(status_code=401, detail="authentication required")


def require_admin(request: Request) -> None:
    """FastAPI dependency: reject requests where the session user is not
    flagged is_admin. Runs require_session first."""
    require_session(request)
    from dbmanager import pools
    with pools.common_data_pool().connection() as conn:
        user = authdb.get_user_by_id(conn, request.session["user_id"])
    if user is None or not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="admin access required")


MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
MIN_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class AuthResult:
    user_id: int
    email: str
    must_change_password: bool


def _is_locked(user: dict) -> bool:
    until = user.get("locked_until")
    return until is not None and until > datetime.now(timezone.utc)


def authenticate(common_data_url: str, email: str, password: str,
                 ip: str | None, user_agent: str | None) -> AuthResult:
    """Verify email + password against common_data. Raises HTTPException on
    any failure and records every attempt in the audit log."""
    email = (email or "").strip().lower()
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.get_user_by_email(conn, email)
        if user is None:
            authdb.record_event(conn, email=email, user_id=None,
                                event="login_failed", ip_address=ip,
                                user_agent=user_agent)
            raise HTTPException(401, "incorrect email or password")
        if not user["is_active"]:
            authdb.record_event(conn, email=email, user_id=user["id"],
                                event="login_failed", ip_address=ip,
                                user_agent=user_agent)
            raise HTTPException(403, "this account is deactivated")
        if _is_locked(user):
            authdb.record_event(conn, email=email, user_id=user["id"],
                                event="login_failed", ip_address=ip,
                                user_agent=user_agent)
            raise HTTPException(
                403, "account temporarily locked — try again later")
        if not verify_password(password, user["password_hash"]):
            locked = authdb.note_failed_attempt(
                conn, user["id"], MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES)
            authdb.record_event(conn, email=email, user_id=user["id"],
                                event="login_failed", ip_address=ip,
                                user_agent=user_agent)
            if locked:
                authdb.record_event(conn, email=email, user_id=user["id"],
                                    event="account_locked", ip_address=ip,
                                    user_agent=user_agent)
            raise HTTPException(401, "incorrect email or password")
        authdb.note_successful_login(conn, user["id"])
        authdb.record_event(conn, email=email, user_id=user["id"],
                            event="login_success", ip_address=ip,
                            user_agent=user_agent)
        return AuthResult(user_id=user["id"], email=user["email"],
                          must_change_password=user["must_change_password"])


def change_password(common_data_url: str, user_id: int, current: str,
                    new: str, ip: str | None, user_agent: str | None) -> None:
    """Change the logged-in user's password. Raises HTTPException on failure."""
    if len(new) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            400,
            f"new password must be at least {MIN_PASSWORD_LENGTH} characters")
    if new == current:
        raise HTTPException(400, "new password must differ from the current one")
    with authdb.auth_conn(common_data_url) as conn:
        user = authdb.get_user_by_id(conn, user_id)
        if user is None:
            raise HTTPException(404, "user not found")
        if not verify_password(current, user["password_hash"]):
            authdb.record_event(conn, email=user["email"], user_id=user_id,
                                event="password_change_failed", ip_address=ip,
                                user_agent=user_agent)
            raise HTTPException(400, "current password is incorrect")
        authdb.set_password(conn, user_id, hash_password(new),
                            must_change=False)
        authdb.record_event(conn, email=user["email"], user_id=user_id,
                            event="password_changed", ip_address=ip,
                            user_agent=user_agent)
