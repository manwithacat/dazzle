"""
Regression test for workspace grid row sizing (#844).

CSS Grid's default is ``align-items: stretch``, which sizes every cell
in a row to the tallest one. The workspace card grid (.dz-dashboard-grid)
must opt into ``align-items: start`` so shorter cards collapse to their
intrinsic height and don't leave dead whitespace underneath.

v0.62 CSS refactor: behaviour now lives in components/dashboard.css
(.dz-dashboard-grid), not inline Tailwind on the grid div.
"""

from __future__ import annotations

from pathlib import Path

CONTENT_TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "templates"
    / "workspace"
    / "_content.html"
)

DASHBOARD_CSS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "runtime"
    / "static"
    / "css"
    / "components"
    / "dashboard.css"
)


class TestWorkspaceGridAlignment:
    def test_grid_container_uses_items_start(self) -> None:
        """The dashboard grid must declare `align-items: start` (#844).

        Without it, the default `align-items: stretch` makes shorter
        cards fill their cell to the tallest card in the row.
        """
        # Template carries the semantic class …
        content = CONTENT_TEMPLATE.read_text()
        assert "dz-dashboard-grid" in content
        assert "data-grid-container" in content

        # … and the CSS rule sets align-items: start.
        css = DASHBOARD_CSS.read_text()
        assert "align-items: start" in css, (
            "Workspace grid (.dz-dashboard-grid) is missing `align-items: start` — "
            "#844 regression. Cards in the same row will stretch to the tallest one."
        )

    def test_grid_still_uses_12_columns_at_md(self) -> None:
        """Sanity check: the 12-col grid structure is preserved at md+."""
        css = DASHBOARD_CSS.read_text()
        assert "@media (min-width: 48rem)" in css
        assert "repeat(12, minmax(0, 1fr))" in css
