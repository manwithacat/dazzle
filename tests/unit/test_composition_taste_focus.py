"""Opt-in taste dimensions in the composition visual pipeline."""

from dazzle.core.composition_visual import (
    DIMENSION_PREPROCESSING,
    DIMENSION_PROMPT_BUILDERS,
    DIMENSIONS,
    TASTE_FOCUS_KEYS,
    resolve_focus_dimensions,
)
from dazzle.core.taste_rubric import TASTE_DIMENSIONS


def test_taste_keys_mirror_rubric_and_stay_out_of_defaults() -> None:
    assert TASTE_FOCUS_KEYS == [d.key for d in TASTE_DIMENSIONS]
    assert not set(TASTE_FOCUS_KEYS) & set(DIMENSIONS)


def test_taste_keys_have_prompt_builders_and_preprocessing() -> None:
    for key in TASTE_FOCUS_KEYS:
        assert key in DIMENSION_PROMPT_BUILDERS
        assert DIMENSION_PREPROCESSING[key] is None  # full-colour screenshots
        prompt = DIMENSION_PROMPT_BUILDERS[key]("hero", {})
        assert key in prompt
        assert '"findings"' in prompt  # composition findings contract, not panel scores


def test_resolve_focus_default_is_standard_dimensions() -> None:
    assert resolve_focus_dimensions(None) == list(DIMENSIONS)


def test_resolve_focus_taste_shorthand_expands_theme_agnostic_keys() -> None:
    # "taste" expands only to both-theme dimensions: composition captures
    # carry no theme info, so dark_mode_integrity would produce false
    # findings on light screenshots. It stays requestable by name.
    expanded = resolve_focus_dimensions(["taste"])
    assert expanded == [d.key for d in TASTE_DIMENSIONS if d.applies_to == "both"]
    assert "dark_mode_integrity" not in expanded
    assert resolve_focus_dimensions(["dark_mode_integrity"]) == ["dark_mode_integrity"]


def test_resolve_focus_mixed_and_invalid() -> None:
    got = resolve_focus_dimensions(["layout_overflow", "perceived_craft", "bogus"])
    assert got == ["layout_overflow", "perceived_craft"]
    assert resolve_focus_dimensions(["bogus"]) == []
