import pytest
from dbmanager import themes


def test_default_theme_shape():
    t = themes.default_theme()
    assert t["preset"] == "foundry"
    assert t["overrides"] == {}


def test_validate_accepts_good_theme():
    themes.validate({"preset": "slate", "overrides": {"--iron": "#abcdef"}})


def test_validate_rejects_unknown_preset():
    with pytest.raises(ValueError, match="preset"):
        themes.validate({"preset": "midnight", "overrides": {}})


def test_validate_rejects_uncurated_var():
    with pytest.raises(ValueError, match="curated"):
        themes.validate({"preset": "foundry",
                         "overrides": {"--soot-1": "#000000"}})


def test_validate_rejects_bad_color_string():
    with pytest.raises(ValueError, match="hex"):
        themes.validate({"preset": "foundry",
                         "overrides": {"--iron": "not-a-color"}})


def test_effective_merges_preset_with_overrides():
    eff = themes.effective(
        {"preset": "slate", "overrides": {"--iron": "#abcdef"}})
    assert eff["--iron"] == "#abcdef"
    assert eff["--soot"] == themes.PRESETS["slate"]["--soot"]
    assert eff["--ember"] == themes.PRESETS["slate"]["--ember"]
