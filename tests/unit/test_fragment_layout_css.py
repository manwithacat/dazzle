"""Regression: typed-substrate layout primitives have base CSS rules.

Cycle 141 visual-Tier 2 surfaced (#1079) that `Stack`/`Row`/`Grid` emit
classes (`dz-stack`, `dz-row`, `dz-grid` plus `--gap-*`/`--align-*`/
`--columns-*` modifiers) for which no CSS existed in the v0.67.52
typed-substrate stylesheet. Two `<a>` Links inside a Stack rendered as
inline siblings with zero spacing — visible on every 403/404/500 page
and most region empty-states. Cycle 143 added the base rules.

This test pins the contract between the renderer and the stylesheet:
every class the renderer can emit must have a matching CSS rule in the
canonical sheet so future deletions don't silently regress.
"""

from __future__ import annotations

from pathlib import Path

_COMPONENTS = Path(__file__).resolve().parents[2] / "packages/hatchi-maxchi/components"


def _text() -> str:
    # L2 split the layout vocabulary across two HM files: the Layout
    # Hyperparts (layout.css) + the remaining fragment chrome
    # (fragment-primitives.css). The contract is the union.
    return (_COMPONENTS / "fragment-primitives.css").read_text() + (
        _COMPONENTS / "layout.css"
    ).read_text()


def test_stack_hyperpart_contract_present() -> None:
    """L2: the stack Hyperpart (layout.css) — base rule + the shared
    data-dz-gap scale replace the retired --gap-* modifier classes."""
    css = _text()
    assert ".dz-stack {" in css
    assert ".dz-stack--gap-" not in css, "the legacy modifier scale is retired"
    for gap in ("none", "xs", "sm", "md", "lg", "xl"):
        assert f'.dz-stack[data-dz-gap="{gap}"]' in css


def test_cluster_hyperpart_replaces_row() -> None:
    """L2: Row emits the cluster Hyperpart — the dz-row rule family is
    retired with it."""
    css = _text()
    assert ".dz-cluster {" in css
    assert ".dz-row {" not in css
    assert ".dz-row--" not in css
    for align in ("start", "end", "baseline", "stretch"):
        assert f'.dz-cluster[data-dz-align="{align}"]' in css


def test_grid_base_and_all_column_modifiers_present() -> None:
    css = _text()
    assert ".dz-grid {" in css
    for cols in range(1, 13):
        assert f".dz-grid--columns-{cols}" in css, f"missing .dz-grid--columns-{cols}"


def test_bare_page_chrome_rule_present_for_error_views() -> None:
    """Regression: error views (build_app_403_view etc.) render as Page →
    Stack with no AppShell wrapper. Cycle 144 visual-Tier 2 (#1081) flagged
    the resulting page as chromeless plain text. Cycle 145 added a
    :only-child rule that gives the bare-Page shape reasonable padding,
    max-width, and centering without affecting Page → AppShell renders."""
    css = _text()
    assert ".dz-page > .dz-stack:only-child" in css, (
        "bare-Page error-view chrome rule missing — see #1081"
    )
