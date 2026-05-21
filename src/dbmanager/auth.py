"""Password check and session-cookie guard."""
from __future__ import annotations
import hmac
from fastapi import HTTPException, Request


def password_matches(supplied: str, expected: str) -> bool:
    """Constant-time comparison of the supplied login password."""
    return hmac.compare_digest(supplied, expected)


def require_session(request: Request) -> None:
    """FastAPI dependency: reject requests without an authenticated session."""
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="authentication required")
