"""#1450: the `.dz-table-empty` empty-state must only show on an *empty* list.

The `tbody` is HTMX-loaded and lives INSIDE `<table class="dz-table-grid">`, which is
a preceding SIBLING of `.dz-table-empty`. The old guard
`.dz-table-empty:not(:has(~ tbody tr[data-dz-row-id]))` used the general
following-sibling combinator (`~ tbody`) — but there is no following-sibling `tbody`,
so `:has(...)` was always false and the empty state showed on every populated list.

The fix keys the guard off the grid (`.dz-table-grid ~ .dz-table-empty`) and matches any
body cell (`tbody tr td`), dropping the brittle `data-dz-row-id` dependency.
"""

from __future__ import annotations

from pathlib import Path

_TABLE_CSS = (
    Path(__file__).resolve().parents[2] / "packages" / "hatchi-maxchi" / "components" / "table.css"
)
_MIN_CSS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "page"
    / "runtime"
    / "static"
    / "dist"
    / "dazzle.min.css"
)


def test_empty_state_guard_keys_off_grid_sibling() -> None:
    css = _TABLE_CSS.read_text(encoding="utf-8")
    # The correct guard: show only when the preceding grid has no body cells.
    assert ".dz-table-grid:not(:has(tbody tr td)) ~ .dz-table-empty" in css
    # The broken following-sibling-`tbody` guard must not reappear.
    assert ":has(~ tbody tr[data-dz-row-id])" not in css


def test_built_bundle_reflects_the_fix() -> None:
    """The served bundle (`dist/dazzle.min.css`) must carry the fixed guard —
    a stale bundle would serve the broken selector even with the source fixed.
    Regenerate via `python scripts/build_dist.py` after editing component CSS."""
    minified = _MIN_CSS.read_text(encoding="utf-8")
    assert ".dz-table-grid:not(:has(tbody tr td)) ~ .dz-table-empty" in minified
    assert ":has(~ tbody tr[data-dz-row-id])" not in minified
