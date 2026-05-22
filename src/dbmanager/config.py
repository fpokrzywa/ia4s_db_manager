"""Loads .env and exposes typed settings."""
from __future__ import annotations
from dataclasses import dataclass
import os
from dotenv import load_dotenv

# Load .env once at import; env vars already set win.
load_dotenv(override=False)


@dataclass(frozen=True)
class Settings:
    database_url: str
    common_data_url: str
    app_secret: str

    @classmethod
    def from_env(cls) -> "Settings":
        db = os.environ.get("DATABASE_URL")
        if not db:
            raise RuntimeError("DATABASE_URL is required in environment or .env")
        common = os.environ.get("DATABASE_COMMON_DATA_URL")
        if not common:
            raise RuntimeError(
                "DATABASE_COMMON_DATA_URL is required in environment or .env")
        secret = os.environ.get("APP_SECRET")
        if not secret:
            raise RuntimeError("APP_SECRET is required in environment or .env")
        return cls(database_url=db, common_data_url=common, app_secret=secret)
