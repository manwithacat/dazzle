"""
Regression test for workspace grid row sizing (#844).

CSS Grid's default is ``align-items: stretch``, which sizes every cell
in a row to the tallest one. The workspace card grid container must
opt into ``items-start`` so shorter cards collapse to their intrinsic
height and don't leave dead whitespace underneath.
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


class TestWorkspaceGridAlignment:
    def test_grid_container_uses_items_start(self) -> None:
        """The dashboard grid must carry `items-start` (#844).

        Without it, the default `align-items: stretch` makes shorter
        cards fill their cell to the tallest card in the row.
        """
        content = CONTENT_TEMPLATE.read_text()
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if "data-grid-container" in line:
                # class= is on the previous line in this template
                class_line = lines[i - 1]
                assert "items-start" in class_line, (
                    "Workspace grid container is missing `items-start` — #844 "
                    "regression. Cards in the same row will stretch to the "
                    "tallest one."
                )
                return
        raise AssertionError("Could not locate data-grid-container in _content.html")

    def test_grid_still_uses_md_grid_cols_12(self) -> None:
        """Sanity check: the 12-col grid structure is preserved."""
        content = CONTENT_TEMPLATE.read_text()
        assert "md:grid-cols-12" in content
