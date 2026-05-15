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

_CSS = (
    Path(__file__).resolve().parents[2]
    / "src/dazzle/ui/runtime/static/css/components/fragment-primitives.css"
)


def _text() -> str:
    return _CSS.read_text()


def test_stack_base_and_gap_modifiers_present() -> None:
    css = _text()
    assert ".dz-stack {" in css
    for gap in ("none", "sm", "md", "lg"):
        assert f".dz-stack--gap-{gap}" in css, f"missing .dz-stack--gap-{gap}"


def test_row_base_gap_and_align_modifiers_present() -> None:
    css = _text()
    assert ".dz-row {" in css
    for gap in ("none", "sm", "md", "lg"):
        assert f".dz-row--gap-{gap}" in css, f"missing .dz-row--gap-{gap}"
    for align in ("start", "center", "end", "stretch"):
        assert f".dz-row--align-{align}" in css, f"missing .dz-row--align-{align}"


def test_grid_base_and_all_column_modifiers_present() -> None:
    css = _text()
    assert ".dz-grid {" in css
    for cols in range(1, 13):
        assert f".dz-grid--columns-{cols}" in css, f"missing .dz-grid--columns-{cols}"
