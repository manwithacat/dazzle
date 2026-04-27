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

_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "src/dazzle_ui/templates/workspace/regions/metrics.html"
)


class TestMetricsTemplateHasNoItemsTable:
    """The static template body must not contain the items-table
    block. We do not need to render it through Jinja — these are
    string-level invariants on the source."""

    def _text(self) -> str:
        return _TEMPLATE_PATH.read_text()

    def test_no_table_tag(self) -> None:
        text = self._text()
        assert "<table" not in text, (
            "metrics.html must NOT render a `<table>` — items belong on "
            "display: list regions, not summary/metrics tiles (#905)"
        )

    def test_no_thead_or_tbody(self) -> None:
        text = self._text()
        assert "<thead" not in text
        assert "<tbody" not in text

    def test_no_items_iteration(self) -> None:
        """The `{% for item in items %}` loop drove the row rendering."""
        text = self._text()
        assert "for item in items" not in text, (
            "metrics.html must not iterate `items` — the dz-metrics-grid "
            "loop iterates `metrics` instead (#905)"
        )

    def test_no_columns_iteration(self) -> None:
        text = self._text()
        assert "for col in columns" not in text

    def test_no_divider_before_table(self) -> None:
        """The `<div class="h-px ... my-3"></div>` separator only
        existed to visually divide the metrics tiles from the unwanted
        rows table — should be gone with the table."""
        text = self._text()
        assert 'class="h-px' not in text, (
            "Stray rule line — should be removed alongside the items table block (#905)"
        )

    def test_no_overflow_x_auto_wrapper(self) -> None:
        """The `<div class="overflow-x-auto">` wrapper enabled
        horizontal table scrolling on narrow tiles. No table → no
        wrapper."""
        text = self._text()
        assert "overflow-x-auto" not in text


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
