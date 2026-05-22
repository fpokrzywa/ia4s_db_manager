"""User management routes."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from psycopg import errors as pgerrors
from pydantic import BaseModel

from dbmanager import authdb
from dbmanager.config import Settings
from dbmanager.passwords import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])

MIN_PASSWORD_LENGTH = 8


class CreateUserBody(BaseModel):
    email: str
    password: str


class UpdateUserBody(BaseModel):
    is_active: bool | None = None
    password: str | None = None
    unlock: bool = False


def _public(user: dict) -> dict:
    """A user row with the password hash stripped out."""
    return {k: v for k, v in user.items() if k != "password_hash"}


@router.get("")
def get_users() -> list[dict]:
    settings = Settings.from_env()
    with authdb.auth_conn(settings.common_data_url) as conn:
        return authdb.list_users(conn)


@router.post("", status_code=201)
def create_user(body: CreateUserBody) -> dict:
    email = body.email.strip().lower()
    if not email:
        raise HTTPException(400, "email is required")
    if len(body.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            400, f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    settings = Settings.from_env()
    with authdb.auth_conn(settings.common_data_url) as conn:
        try:
            user = authdb.create_user(conn, email, hash_password(body.password),
                                      must_change=True)
        except pgerrors.UniqueViolation as exc:
            raise HTTPException(
                409, f"a user with email '{email}' already exists") from exc
    return _public(user)


@router.patch("/{user_id}")
def update_user(user_id: int, body: UpdateUserBody) -> dict:
    settings = Settings.from_env()
    with authdb.auth_conn(settings.common_data_url) as conn:
        if authdb.get_user_by_id(conn, user_id) is None:
            raise HTTPException(404, f"no user with id {user_id}")
        if body.password is not None:
            if len(body.password) < MIN_PASSWORD_LENGTH:
                raise HTTPException(
                    400,
                    f"password must be at least {MIN_PASSWORD_LENGTH} characters")
            authdb.set_password(conn, user_id, hash_password(body.password),
                                must_change=True)
        if body.is_active is not None or body.unlock:
            authdb.update_user(conn, user_id, is_active=body.is_active,
                               unlock=body.unlock)
        user = authdb.get_user_by_id(conn, user_id)
    return _public(user)
