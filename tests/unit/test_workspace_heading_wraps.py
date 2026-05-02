"""Drift gate: workspace heading + primary-actions row wrap (#985).

A workspace with many entities surfaces a long row of "New <Entity>"
buttons. Without `flex-wrap: wrap` on `.dz-workspace-primary-actions`
(and the parent `.dz-workspace-heading`), the row's intrinsic content
width can exceed the heading container, bleeding past `<main>`'s right
edge. Quantified case from #985: 5 buttons × ~210px = 1072px in a
968px-wide heading inside a 1024px content column → +213px overflow.

The fix is two CSS declarations:

1. `.dz-workspace-heading { flex-wrap: wrap }` — title and actions can
   stack vertically when neither fits alongside the other.
2. `.dz-workspace-primary-actions { flex-wrap: wrap;
    justify-content: flex-end }` — the actions row itself can break
   onto multiple lines, right-aligned to match the heading's
   `space-between` layout.

This test pins both declarations against the dashboard.css source so a
future refactor can't quietly drop them.
"""

from __future__ import annotations

import pathlib
import re

CSS_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "runtime"
    / "static"
    / "css"
    / "components"
    / "dashboard.css"
)


def _rule_block(css: str, selector: str) -> str:
    """Return the body (between braces) of the first rule matching *selector*.

    Raises if the selector is missing — the test should fail loudly rather
    than silently passing on an empty body.
    """
    pattern = re.compile(
        r"^" + re.escape(selector) + r"\s*\{([^}]*)\}",
        re.MULTILINE,
    )
    match = pattern.search(css)
    assert match is not None, f"selector {selector!r} not found in dashboard.css"
    return match.group(1)


def test_workspace_heading_wraps() -> None:
    """`.dz-workspace-heading` must declare `flex-wrap: wrap` (#985)."""
    css = CSS_PATH.read_text(encoding="utf-8")
    body = _rule_block(css, ".dz-workspace-heading")
    assert re.search(r"\bflex-wrap\s*:\s*wrap\b", body), (
        ".dz-workspace-heading is missing `flex-wrap: wrap` — without it, "
        "the title + primary-actions row cannot stack on narrow viewports "
        "and overflows <main>'s right edge (#985)."
    )


def test_workspace_primary_actions_wrap() -> None:
    """`.dz-workspace-primary-actions` must declare `flex-wrap: wrap` (#985)."""
    css = CSS_PATH.read_text(encoding="utf-8")
    body = _rule_block(css, ".dz-workspace-primary-actions")
    assert re.search(r"\bflex-wrap\s*:\s*wrap\b", body), (
        ".dz-workspace-primary-actions is missing `flex-wrap: wrap` — "
        "workspaces with many entities surface a long row of `New <Entity>` "
        "buttons that overflow the heading container without wrapping (#985)."
    )


def test_workspace_primary_actions_align_wrapped_rows_right() -> None:
    """Wrapped rows should stay right-aligned to match the heading's
    `space-between` layout.
    """
    css = CSS_PATH.read_text(encoding="utf-8")
    body = _rule_block(css, ".dz-workspace-primary-actions")
    assert re.search(r"\bjustify-content\s*:\s*flex-end\b", body), (
        ".dz-workspace-primary-actions is missing "
        "`justify-content: flex-end` — wrapped rows would otherwise "
        "collapse to the left and break the heading's right-aligned "
        "actions placement (#985)."
    )
