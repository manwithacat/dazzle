"""#1567 — behaviour of the deterministic component token-discipline rubric."""

import pytest

from dazzle.core.component_hygiene import (
    COMPONENT_HYGIENE_DIMENSIONS,
    hm_component_paths,
    score_component_css,
)

pytestmark = pytest.mark.gate


def test_weights_sum_to_100() -> None:
    assert sum(d.weight for d in COMPONENT_HYGIENE_DIMENSIONS) == 100


def test_perfect_token_css_scores_high() -> None:
    css = (
        ".dz-x{color:var(--dz-ink);background:var(--dz-surface);"
        "transition:opacity var(--dz-transition-fast);border-radius:var(--dz-radius);"
        "padding:var(--dz-space-2);gap:0.5rem}"
    )
    result = score_component_css(css)
    assert result["total"] >= 95.0


def test_raw_hex_colour_drops_colour_score() -> None:
    css = ".dz-x{color:#ff0000;background:#00ff00}"
    result = score_component_css(css)
    breakdown = result["breakdown"]  # type: ignore[index]
    assert breakdown["colour_tokens"]["sub_score"] == 0.0


def test_non_dz_selectors_drop_namespace_score() -> None:
    css = ".widget{color:var(--dz-ink)} .panel{color:var(--dz-ink)}"
    result = score_component_css(css)
    breakdown = result["breakdown"]  # type: ignore[index]
    assert breakdown["namespace"]["sub_score"] == 0.0


def test_raw_px_sizing_drops_sizing_score() -> None:
    css = ".dz-x{padding:12px;border-radius:4px}"
    result = score_component_css(css)
    breakdown = result["breakdown"]  # type: ignore[index]
    assert breakdown["sizing_tokens"]["sub_score"] == 0.0


def test_absent_properties_score_na_as_one() -> None:
    # A pure-layout component with no colour/motion/sizing scores those n/a = 1.0.
    css = ".dz-x{display:flex}"
    result = score_component_css(css)
    assert result["total"] == 100.0


def test_hm_component_paths_finds_the_corpus() -> None:
    paths = hm_component_paths()
    assert len(paths) >= 50
    assert all(p.suffix == ".css" for p in paths)
    assert any(p.name == "button.css" for p in paths)
