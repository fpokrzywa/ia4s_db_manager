"""Theme presets, validation, and effective-color computation.

Only the seven curated CSS vars in CURATED_VARS are overridable by an admin.
A preset's full color map is applied as the base; any override in the saved
theme is layered on top to produce the effective map."""
from __future__ import annotations
import re

# The seven vars that admins can override via the Theme page.
CURATED_VARS = (
    "--soot",    # background
    "--iron",    # primary accent
    "--ember",   # warm accent
    "--bone",    # primary text
    "--ash",     # secondary text
    "--patina",  # success
    "--rust",    # error
)

# Full color map for each preset. The seven CURATED_VARS plus the eight
# non-curated vars; the latter are not editable but switch with the preset.
PRESETS: dict[str, dict[str, str]] = {
    "foundry": {
        "--soot":    "#15110c",
        "--soot-1":  "#1c1610",
        "--soot-2":  "#251d14",
        "--soot-3":  "#322619",
        "--edge":    "#3b2e1f",
        "--edge-hi": "#5c4527",
        "--bone":    "#f4ecdb",
        "--ash":     "#ab9d85",
        "--dim":     "#6f6353",
        "--iron":    "#ff5a1f",
        "--ember":   "#ffae3d",
        "--spark":   "#ffe7a8",
        "--steel":   "#84a7bd",
        "--patina":  "#5fb295",
        "--rust":    "#c2412a",
    },
    "slate": {
        "--soot":    "#0f1419",
        "--soot-1":  "#161c23",
        "--soot-2":  "#1e2530",
        "--soot-3":  "#2a323e",
        "--edge":    "#2e3845",
        "--edge-hi": "#475063",
        "--bone":    "#e6edf3",
        "--ash":     "#8b96a3",
        "--dim":     "#5a6573",
        "--iron":    "#4a8dd1",
        "--ember":   "#6fa8d6",
        "--spark":   "#b3d3e9",
        "--steel":   "#84a7bd",
        "--patina":  "#5fb295",
        "--rust":    "#c2412a",
    },
    "daylight": {
        "--soot":    "#f8f2e3",
        "--soot-1":  "#efe7d3",
        "--soot-2":  "#e4dac1",
        "--soot-3":  "#d6caab",
        "--edge":    "#c9bda0",
        "--edge-hi": "#a89977",
        "--bone":    "#2c2419",
        "--ash":     "#6d6354",
        "--dim":     "#948876",
        "--iron":    "#c64512",
        "--ember":   "#d97a1f",
        "--spark":   "#f0a73a",
        "--steel":   "#5a8aa3",
        "--patina":  "#4a8c6b",
        "--rust":    "#a83520",
    },
}

DEFAULT_PRESET = "foundry"
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def default_theme() -> dict:
    """The theme used when no `theme` row exists in app_settings."""
    return {"preset": DEFAULT_PRESET, "overrides": {}}


def validate(theme: dict) -> None:
    """Raise ValueError if the theme is malformed."""
    if not isinstance(theme, dict):
        raise ValueError("theme must be an object")
    preset = theme.get("preset")
    if preset not in PRESETS:
        raise ValueError(f"unknown preset: {preset!r}")
    overrides = theme.get("overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("overrides must be an object")
    for var, color in overrides.items():
        if var not in CURATED_VARS:
            raise ValueError(f"{var!r} is not in the curated color set")
        if not isinstance(color, str) or not _HEX_RE.match(color):
            raise ValueError(
                f"value for {var} must be a #rrggbb hex color")


def effective(theme: dict) -> dict[str, str]:
    """Resolve `theme` into the full {var: color} map applied to the UI:
    the preset's full map merged with the (curated) overrides."""
    return {**PRESETS[theme["preset"]], **theme.get("overrides", {})}
