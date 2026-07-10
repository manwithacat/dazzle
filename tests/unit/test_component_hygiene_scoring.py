"""#1567 — behaviour of the deterministic component token-discipline rubric."""

import pytest

from dazzle.core.component_hygiene import (
    COMPONENT_HYGIENE_DIMENSIONS,
    PAGE_CHROME_EXEMPT,
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


def test_var_fallback_counts_as_token_driven() -> None:
    # `var(--dz-x, #fallback)` is legitimate token usage — the hex fallback must not
    # count against colour discipline.
    css = ".dz-x{color:var(--dz-color-text, #111827);background:var(--dz-surface, #fff)}"
    result = score_component_css(css)
    breakdown = result["breakdown"]  # type: ignore[index]
    assert breakdown["colour_tokens"]["sub_score"] == 1.0


def test_comments_are_ignored() -> None:
    # A raw hex / non-dz class inside a comment must not register as a declaration.
    css = "/* migrated from dz.css; old .widget used #ff0000 */ .dz-x{color:var(--dz-ink)}"
    result = score_component_css(css)
    breakdown = result["breakdown"]  # type: ignore[index]
    assert breakdown["colour_tokens"]["sub_score"] == 1.0
    assert breakdown["namespace"]["sub_score"] == 1.0


def test_page_chrome_exempt_lists_transitions() -> None:
    # transitions.css is page-level chrome, not a card Hyperpart — documented exemption.
    assert "transitions.css" in PAGE_CHROME_EXEMPT
    names = {p.name for p in hm_component_paths()}
    assert PAGE_CHROME_EXEMPT <= names, "an exempt file must actually exist (no rename rot)"


def test_hm_component_paths_finds_the_corpus() -> None:
    paths = hm_component_paths()
    assert len(paths) >= 50
    assert all(p.suffix == ".css" for p in paths)
    assert any(p.name == "button.css" for p in paths)
