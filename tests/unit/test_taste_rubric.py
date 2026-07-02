"""Taste rubric — single source of truth for judged aesthetic dimensions."""

from dazzle.core.taste_rubric import (
    TASTE_DIMENSIONS,
    TasteDimension,
    build_judge_prompt,
    dimensions_for_theme,
)

EXPECTED_KEYS = [
    "typographic_hierarchy",
    "spatial_rhythm",
    "color_discipline",
    "state_completeness",
    "dark_mode_integrity",
    "perceived_craft",
]


def test_dimension_keys_are_the_spec_six() -> None:
    assert [d.key for d in TASTE_DIMENSIONS] == EXPECTED_KEYS


def test_dimensions_are_frozen_and_complete() -> None:
    for d in TASTE_DIMENSIONS:
        assert isinstance(d, TasteDimension)
        assert d.title and d.question
        # Anchors at 2, 5, 8 give judges a calibrated 1-10 scale.
        assert [score for score, _ in d.anchors] == [2, 5, 8]
        assert all(text for _, text in d.anchors)
        assert d.applies_to in ("light", "dark", "both")


def test_dark_mode_integrity_only_applies_to_dark() -> None:
    (dark_dim,) = [d for d in TASTE_DIMENSIONS if d.key == "dark_mode_integrity"]
    assert dark_dim.applies_to == "dark"


def test_dimensions_for_theme_filters() -> None:
    light = dimensions_for_theme("light")
    dark = dimensions_for_theme("dark")
    assert "dark_mode_integrity" not in [d.key for d in light]
    assert "dark_mode_integrity" in [d.key for d in dark]
    assert len(light) == 5
    assert len(dark) == 6


def test_judge_prompt_contains_every_dimension_and_no_dialect_names() -> None:
    prompt = build_judge_prompt(TASTE_DIMENSIONS)
    for d in TASTE_DIMENSIONS:
        assert d.key in prompt
        assert d.question in prompt
    # Goodhart guard: the rubric never names the dialect it competes with.
    for banned in ("shadcn", "Tailwind", "Vercel", "React"):
        assert banned.lower() not in prompt.lower()
    assert "JSON" in prompt  # response-format instruction present
