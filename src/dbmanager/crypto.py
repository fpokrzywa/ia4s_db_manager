"""Symmetric encryption for stored secrets (server passwords).

Uses Fernet with a key derived from APP_SECRET via PBKDF2-HMAC-SHA256
(600 000 iterations, fixed application salt), so no extra environment
variable is required. Rotating APP_SECRET makes existing tokens undecryptable
(stored server passwords would need to be re-entered)."""
from __future__ import annotations
import base64
from functools import lru_cache
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dbmanager.config import Settings

# Fixed application salt — not secret, just domain-separates this derivation.
_SALT = b"dbmanager-fernet-v1"


@lru_cache
def _fernet(secret: str) -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=600_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode("utf-8")))
    return Fernet(key)


def encrypt(plain: str) -> str:
    """Return a Fernet token for the plaintext."""
    return _fernet(Settings.from_env().app_secret).encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    """Return the plaintext for a Fernet token produced by `encrypt`."""
    return _fernet(Settings.from_env().app_secret).decrypt(token.encode("utf-8")).decode("utf-8")
