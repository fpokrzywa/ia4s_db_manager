"""Symmetric encryption for stored secrets (server passwords).

Uses Fernet with a key derived from APP_SECRET, so no extra environment
variable is required. Rotating APP_SECRET makes existing tokens undecryptable
(stored server passwords would need to be re-entered)."""
from __future__ import annotations
import base64
import hashlib
from cryptography.fernet import Fernet
from dbmanager.config import Settings


def _fernet() -> Fernet:
    secret = Settings.from_env().app_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt(plain: str) -> str:
    """Return a Fernet token for the plaintext."""
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    """Return the plaintext for a Fernet token produced by `encrypt`."""
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
