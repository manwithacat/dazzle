"""
Regression tests for heatmap row click (#845).

The heatmap region used to attach `hx-get` / `cursor-pointer` only to
value cells, leaving the row-label <td> as a dead zone. The fix moves
those attributes up to the <tr> so the whole row is clickable.
"""

from __future__ import annotations

import re
from pathlib import Path

HEATMAP = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "templates"
    / "workspace"
    / "regions"
    / "heatmap.html"
)


class TestHeatmapRowClick:
    def test_hx_get_is_on_tr_not_td(self) -> None:
        """hx-get must sit on the <tr>, not the per-cell <td> (#845)."""
        content = HEATMAP.read_text()
        # <tr> open-tag blocks can wrap across multiple lines; match them
        # as-a-whole so we can check for hx-get inside.
        tr_blocks = re.findall(r"<tr\b[^>]*>", content, re.DOTALL)
        assert any("hx-get" in block for block in tr_blocks), (
            "Heatmap <tr> is missing hx-get — row labels won't navigate (#845)."
        )

    def test_td_no_longer_carries_hx_get(self) -> None:
        """Value <td>s must not duplicate the HTMX attribute — causes double swaps."""
        content = HEATMAP.read_text()
        # Walk the file: if hx-get appears in a <td ...> line, fail.
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("<td") and "hx-get" in stripped:
                raise AssertionError(
                    "Heatmap <td> still carries hx-get — will double-fire "
                    "when the <tr> also carries it (#845)."
                )

    def test_row_has_cursor_pointer_when_action_url_set(self) -> None:
        """Pointer affordance + hover on the <tr>, gated by action_url.

        v0.62 CSS refactor: the visual delta lives on the .is-clickable
        modifier toggled by the template's `{% if action_url %}` branch,
        and styled by `.dz-heatmap-grid > tbody > tr.is-clickable` in
        components/regions.css. Pin both the template gating and the
        CSS rule existence."""
        content = HEATMAP.read_text()
        # Template applies .is-clickable inside the action_url branch
        tr_match = re.search(
            r"<tr\s*\{%\s*if\s+action_url\s*%\}[^>]*is-clickable",
            content,
            re.DOTALL,
        )
        assert tr_match, "Heatmap <tr> must get .is-clickable when action_url is set (#845)."

        # CSS rule exists and sets cursor pointer + hover background
        from pathlib import Path

        css = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/runtime/static/css/components/regions.css"
        ).read_text()
        assert ".dz-heatmap-grid > tbody > tr.is-clickable" in css
        assert "cursor: pointer" in css
