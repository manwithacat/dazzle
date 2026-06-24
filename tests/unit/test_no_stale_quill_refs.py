"""Drift gate: no runtime CSS or JS may reference Quill assets.

Quill removed in #977 cycle 4 (v0.64.3). Two stale references slipped
through the cleanup and shipped silently for several cycles:

1. `dazzle.css` line 27: `@import url("../vendor/quill.snow.css")`
2. `design-system.css` lines 1097-1256: 160 lines of `.ql-*` token
   overrides for the Quill snow theme.

Both produced visible 404s on every rich_text page, but only at
runtime (browser fetch). The static `/fuzz` slash command never
catches it because boot-stderr doesn't see browser fetches; the
runtime fuzz at `dazzle.testing.fuzz_runtime` caught it on the wide
sweep.

This gate pins the cleanup so a future cycle can't accidentally
re-introduce Quill (e.g. by reverting a CSS file or adding a
similar third-party editor under the same `.ql-*` class names).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

ROOT = Path(__file__).resolve().parents[2]
CSS_DIR = ROOT / "src" / "dazzle" / "page" / "runtime" / "static" / "css"


def _live_lines(text: str) -> list[str]:
    """Strip CSS comment blocks (/* ... */) so the gate doesn't trip
    on documentation comments mentioning Quill (e.g. 'removed in #977
    cycle 4'). Crude but fine — the runtime CSS doesn't have nested
    comments."""
    out: list[str] = []
    in_comment = False
    for line in text.split("\n"):
        i = 0
        kept: list[str] = []
        while i < len(line):
            if not in_comment and line[i : i + 2] == "/*":
                in_comment = True
                i += 2
            elif in_comment and line[i : i + 2] == "*/":
                in_comment = False
                i += 2
            elif not in_comment:
                kept.append(line[i])
                i += 1
            else:
                i += 1
        out.append("".join(kept))
    return out


def test_no_quill_import_in_dazzle_css() -> None:
    css = (CSS_DIR / "dazzle.css").read_text()
    live = "\n".join(_live_lines(css))
    assert "quill" not in live.lower(), (
        "dazzle.css references Quill outside a comment. "
        "Quill was removed in #977 cycle 4 — see #1001."
    )


def test_no_ql_class_rules_in_design_system_css() -> None:
    css = (CSS_DIR / "design-system.css").read_text()
    live = "\n".join(_live_lines(css))
    # `.ql-something {` is the Quill class-rule shape.
    forbidden_starts = (
        ".ql-toolbar",
        ".ql-container",
        ".ql-editor",
        ".ql-snow",
        ".ql-stroke",
        ".ql-fill",
        ".ql-picker",
    )
    for line in live.split("\n"):
        stripped = line.strip()
        for prefix in forbidden_starts:
            assert not stripped.startswith(prefix), (
                f"design-system.css contains Quill rule '{stripped[:80]}'. "
                "Quill removed in #977 cycle 4. See #1001 / .dz-richtext-* "
                "rules in components/richtext.css are the replacement."
            )


def test_no_ql_classes_in_widget_overrides_css() -> None:
    """dz-widgets.css already had Quill rules cleaned in cycle 4 —
    this gate prevents reintroduction."""
    css = (CSS_DIR / "dz-widgets.css").read_text()
    live = "\n".join(_live_lines(css))
    assert ".ql-" not in live, "dz-widgets.css contains a Quill class rule (#1001)"
