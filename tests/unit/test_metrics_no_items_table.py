"""Regression test for #905 — `display: summary` / `display: metrics`
must NEVER render the underlying items list as a table inside the hero
tile. The metrics template is for headline numbers (with optional
delta + tones); the items table belongs on `display: list` regions.

The bug shipped against v0.61.64 in AegisMark's teacher_workspace,
where the "Marked overnight" hero tile rendered correctly above a
600-row scrollable Manuscript table, and the "Class average" tile
above an 82,568-row MarkingResult table. Both crowded the
prototype-tight hero strip with ~400px of vertical waste per tile.

The fix in v0.61.67 deletes the items+columns block from
`metrics.html` entirely. This test pins the absence so a future
"hybrid metrics+table" temptation doesn't reintroduce the bloat.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "src/dazzle/page/templates/workspace/regions/metrics.html"
)


@pytest.mark.skip(
    reason="Phase 4 deletion sweep (v0.67.52) — pinned legacy Jinja template content or file existence; the typed substrate produces equivalent output via different markup"
)
class TestMetricsTemplateHasNoItemsTable:
    """The static template body must not contain the items-table
    block. We do not need to render it through Jinja — these are
    string-level invariants on the source."""

    def _text(self) -> str:
        return _TEMPLATE_PATH.read_text()

    @pytest.mark.parametrize(
        "needle",
        [
            "<table",
            "for item in items",
            "for col in columns",
            'class="h-px',
            "overflow-x-auto",
        ],
        ids=[
            "test_no_table_tag",
            "test_no_items_iteration",
            "test_no_columns_iteration",
            "test_no_divider_before_table",
            "test_no_overflow_x_auto_wrapper",
        ],
    )
    def test_template_excludes(self, needle: str) -> None:
        assert needle not in self._text()

    def test_no_thead_or_tbody(self) -> None:
        text = self._text()
        assert "<thead" not in text
        assert "<tbody" not in text


@pytest.mark.skip(
    reason="Phase 4 deletion sweep (v0.67.52) — pinned legacy Jinja template content or file existence; the typed substrate produces equivalent output via different markup"
)
class TestMetricsTemplateStillRendersTiles:
    """Defensive — make sure we didn't accidentally also delete the
    metrics tiles loop while removing the items table."""

    def _text(self) -> str:
        return _TEMPLATE_PATH.read_text()

    def test_still_iterates_metrics(self) -> None:
        text = self._text()
        assert "for metric in metrics" in text

    def test_still_emits_dz_metric_tile(self) -> None:
        text = self._text()
        assert "dz-metric-tile" in text

    def test_still_branches_on_tone(self) -> None:
        """v0.61.65 per-tile tone tints (AegisMark roadmap #2) — must
        survive the #905 cleanup."""
        text = self._text()
        assert "metric.tone" in text

    def test_still_renders_delta(self) -> None:
        """v0.61.25 (#884) period-over-period delta — must survive."""
        text = self._text()
        assert "metric.delta_direction" in text
