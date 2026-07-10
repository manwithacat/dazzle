"""#1567 slice 2 — WCAG contrast math + pair-table behaviour."""

import pytest

from dazzle.core.contrast import (
    FAMILY_PAIRS,
    THEMESPEC_PAIRS,
    check_pairs,
    contrast_ratio,
    parse_css_color,
    parse_family_modes,
    relative_luminance,
)

pytestmark = pytest.mark.gate


def test_parse_hsl_triplet() -> None:
    assert parse_css_color("0 0% 100%") == (1.0, 1.0, 1.0)
    r, g, b = parse_css_color("0 0% 0%")
    assert (r, g, b) == (0.0, 0.0, 0.0)


def test_parse_oklch_white_black() -> None:
    r, g, b = parse_css_color("oklch(1.000 0.0000 0.0)")
    assert all(abs(c - 1.0) < 0.01 for c in (r, g, b))
    r, g, b = parse_css_color("oklch(0.000 0.0000 0.0)")
    assert all(abs(c) < 0.01 for c in (r, g, b))


def test_parse_hex() -> None:
    assert parse_css_color("#ffffff") == (1.0, 1.0, 1.0)
    assert parse_css_color("#000") == (0.0, 0.0, 0.0)


def test_parse_unparseable_returns_none() -> None:
    assert parse_css_color("var(--dz-ink)") is None
    assert parse_css_color("linear-gradient(90deg, #fff, #000)") is None


def test_wcag_reference_ratios() -> None:
    # Canonical WCAG anchors: white/black = 21:1; a colour with itself = 1:1.
    white, black = (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)
    assert abs(contrast_ratio(white, black) - 21.0) < 0.01
    assert contrast_ratio(white, white) == 1.0
    # Symmetry.
    grey = parse_css_color("0 0% 46%")
    assert contrast_ratio(white, grey) == contrast_ratio(grey, white)
    # #767676 on white is the classic ~4.54:1 AA-passing grey.
    aa_grey = parse_css_color("#767676")
    assert 4.4 < contrast_ratio(aa_grey, white) < 4.7


def test_relative_luminance_anchors() -> None:
    assert abs(relative_luminance((1.0, 1.0, 1.0)) - 1.0) < 1e-9
    assert abs(relative_luminance((0.0, 0.0, 0.0))) < 1e-9


def test_check_pairs_flags_low_contrast() -> None:
    tokens = {"foreground": "0 0% 60%", "background": "0 0% 100%"}  # ~2.6:1
    failures = check_pairs(tokens, FAMILY_PAIRS)
    assert any(f.startswith("foreground/background") for f in failures)


def test_check_pairs_skips_absent_and_unparseable() -> None:
    # Only background present -> every pair skipped -> no failures.
    assert check_pairs({"background": "0 0% 100%"}, FAMILY_PAIRS) == []
    # Unparseable value -> skipped, not a failure.
    tokens = {"foreground": "var(--x)", "background": "0 0% 100%"}
    assert check_pairs(tokens, FAMILY_PAIRS) == []


def test_pair_tables_shape() -> None:
    assert all(p.minimum in (4.5, 3.0) for p in FAMILY_PAIRS + THEMESPEC_PAIRS)
    assert any(p.fg == "text-primary" for p in THEMESPEC_PAIRS)


def test_parse_family_modes_real_file() -> None:
    from pathlib import Path

    css = (
        Path(__file__).parents[2] / "packages" / "hatchi-maxchi" / "families" / "stripe.css"
    ).read_text(encoding="utf-8")
    modes = parse_family_modes(css)
    assert set(modes) == {"light", "dark"}
    assert "background" in modes["light"] and "foreground" in modes["light"]
    assert modes["light"]["background"] != modes["dark"]["background"]
