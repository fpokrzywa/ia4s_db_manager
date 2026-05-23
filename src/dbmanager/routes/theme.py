"""Theme API — public GET (so the login screen is themed) and admin-only
PATCH/list."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dbmanager import auth, pools, settings_store, themes

router = APIRouter(prefix="/api", tags=["theme"])

_THEME_KEY = "theme"


class ThemeBody(BaseModel):
    preset: str
    overrides: dict[str, str] = {}


def _load_theme() -> dict:
    with pools.common_data_pool().connection() as conn:
        saved = settings_store.get_setting(conn, _THEME_KEY)
    return saved if saved is not None else themes.default_theme()


@router.get("/theme")
def get_theme() -> dict:
    """Return the saved theme + its effective color map. Public — needed by
    the login screen before any session exists."""
    theme = _load_theme()
    return {"preset": theme["preset"],
            "overrides": theme.get("overrides", {}),
            "effective": themes.effective(theme)}


@router.get("/themes", dependencies=[Depends(auth.require_admin)])
def list_presets() -> dict:
    """Return every built-in preset's full color map. Admin-only."""
    return {"presets": themes.PRESETS,
            "curated_vars": list(themes.CURATED_VARS),
            "default_preset": themes.DEFAULT_PRESET}


@router.patch("/theme", dependencies=[Depends(auth.require_admin)])
def update_theme(body: ThemeBody) -> dict:
    """Save the theme. Admin-only."""
    theme = {"preset": body.preset, "overrides": body.overrides or {}}
    try:
        themes.validate(theme)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with pools.common_data_pool().connection() as conn:
        settings_store.set_setting(conn, _THEME_KEY, theme)
    return {"preset": theme["preset"], "overrides": theme["overrides"],
            "effective": themes.effective(theme)}
