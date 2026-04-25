"""Tests for the v0.61.33 line/area chart overlay_series feature (#883).

Closes the second half of #883 — adds additional data series with their
own source/filter/aggregate alongside the primary line/area series.

Three layers:
  1. Parser: ``overlay_series:`` block with multi-line dash items
     parses into ``list[OverlaySeriesSpec]``.
  2. IR: ``OverlaySeriesSpec`` defaults + frozen-model behaviour.
  3. Template: line_chart.html renders one extra dashed polyline per
     overlay, expands the y-axis to fit overlay values, and shows a
     legend for multi-series.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.module import ModuleFragment
from dazzle.core.ir.workspaces import OverlaySeriesSpec


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"
entity Mark:
  id: uuid pk
  scaled_mark: int
  ao: enum[ao1,ao2,ao3]
  assessed_at: datetime auto_add
workspace dash "Dash":
  trajectory:
    source: Mark
    aggregate:
      avg: avg(scaled_mark)
    display: line_chart
    group_by: bucket(assessed_at, week)
"""


# ───────────────────────────── parser ──────────────────────────────


class TestOverlaySeriesParser:
    def test_minimal_overlay(self) -> None:
        src = (
            _BASE_DSL
            + """    overlay_series:
      - label: "Cohort"
        aggregate: avg(scaled_mark)
"""
        )
        region = _parse(src).workspaces[0].regions[0]
        assert len(region.overlay_series) == 1
        ovl = region.overlay_series[0]
        assert ovl.label == "Cohort"
        assert ovl.source is None  # defaults to parent
        assert ovl.filter is None
        # Parser tokenises and rejoins with spaces.
        assert "avg" in ovl.aggregate_expr and "scaled_mark" in ovl.aggregate_expr

    def test_overlay_with_source_filter_aggregate(self) -> None:
        src = (
            _BASE_DSL
            + """    overlay_series:
      - label: "Cohort average"
        source: Mark
        filter: ao = ao3
        aggregate: avg(scaled_mark)
"""
        )
        region = _parse(src).workspaces[0].regions[0]
        ovl = region.overlay_series[0]
        assert ovl.source == "Mark"
        assert ovl.filter is not None
        assert "avg" in ovl.aggregate_expr

    def test_multiple_overlays(self) -> None:
        src = (
            _BASE_DSL
            + """    overlay_series:
      - label: "Cohort"
        aggregate: avg(scaled_mark)
      - label: "Target"
        source: Mark
        aggregate: max(scaled_mark)
"""
        )
        region = _parse(src).workspaces[0].regions[0]
        assert [o.label for o in region.overlay_series] == ["Cohort", "Target"]
        assert region.overlay_series[1].source == "Mark"

    def test_aggregate_required(self) -> None:
        src = (
            _BASE_DSL
            + """    overlay_series:
      - label: "Bad"
        source: Mark
"""
        )
        with pytest.raises(Exception, match="overlay_series entry .* requires `aggregate:`"):
            _parse(src)

    def test_unknown_key_raises(self) -> None:
        src = (
            _BASE_DSL
            + """    overlay_series:
      - label: "Bad"
        colour: red
        aggregate: avg(scaled_mark)
"""
        )
        with pytest.raises(Exception, match="Unknown overlay_series key"):
            _parse(src)

    def test_overlay_absent_by_default(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.overlay_series == []


# ───────────────────────────── ir ──────────────────────────────


class TestOverlaySeriesIR:
    def test_defaults(self) -> None:
        ovl = OverlaySeriesSpec(label="X", aggregate_expr="avg(scaled_mark)")
        assert ovl.source is None
        assert ovl.filter is None

    def test_frozen(self) -> None:
        from pydantic import ValidationError

        ovl = OverlaySeriesSpec(label="X", aggregate_expr="avg(x)")
        with pytest.raises(ValidationError):
            ovl.label = "Y"  # type: ignore[misc]


# ─────────────────────── template rendering ─────────────────────


try:
    from dazzle_ui.runtime.template_renderer import render_fragment

    _HAS_TEMPLATES = True
except ImportError:
    _HAS_TEMPLATES = False


_PRIMARY_BUCKETS = [
    {"label": "Sep", "value": 50},
    {"label": "Oct", "value": 55},
    {"label": "Nov", "value": 60},
    {"label": "Dec", "value": 65},
]


@pytest.mark.skipif(not _HAS_TEMPLATES, reason="dazzle_ui not installed")
class TestLineChartOverlayTemplate:
    def test_overlay_renders_dashed_polyline(self) -> None:
        html = render_fragment(
            "workspace/regions/line_chart.html",
            title="Trajectory",
            bucketed_metrics=_PRIMARY_BUCKETS,
            reference_lines=[],
            reference_bands=[],
            overlay_series_data=[
                {
                    "label": "Cohort",
                    "buckets": [
                        {"label": "Sep", "value": 45},
                        {"label": "Oct", "value": 48},
                        {"label": "Nov", "value": 52},
                        {"label": "Dec", "value": 55},
                    ],
                }
            ],
            empty_message="",
        )
        # Overlay polyline uses stroke-dasharray="3,2"
        assert 'stroke-dasharray="3,2"' in html
        # Legend includes the overlay label
        assert ">Cohort<" in html

    def test_overlay_above_data_widens_y_axis(self) -> None:
        """An overlay with values above the primary peak must scale the
        whole chart down so the overlay stays inside the plot area."""
        html_no_ovl = render_fragment(
            "workspace/regions/line_chart.html",
            title="X",
            bucketed_metrics=_PRIMARY_BUCKETS,
            reference_lines=[],
            reference_bands=[],
            overlay_series_data=[],
            empty_message="",
        )
        html_with_ovl = render_fragment(
            "workspace/regions/line_chart.html",
            title="X",
            bucketed_metrics=_PRIMARY_BUCKETS,
            reference_lines=[],
            reference_bands=[],
            overlay_series_data=[
                {
                    "label": "Above",
                    "buckets": [
                        {"label": "Sep", "value": 95},
                        {"label": "Oct", "value": 100},
                        {"label": "Nov", "value": 100},
                        {"label": "Dec", "value": 100},
                    ],
                }
            ],
            empty_message="",
        )
        # Same primary data, different y-axis ceiling → primary points
        # land at different pixel coordinates → HTML differs.
        assert html_no_ovl != html_with_ovl

    def test_legend_appears_when_overlays_present(self) -> None:
        html = render_fragment(
            "workspace/regions/line_chart.html",
            title="Pupil",
            bucketed_metrics=_PRIMARY_BUCKETS,
            reference_lines=[],
            reference_bands=[],
            overlay_series_data=[
                {
                    "label": "Cohort",
                    "buckets": [{"label": "Sep", "value": 40}, {"label": "Oct", "value": 50}],
                }
            ],
            empty_message="",
        )
        # Both primary (title) and overlay label appear in the legend
        assert ">Pupil<" in html
        assert ">Cohort<" in html
        # Footer reports the series count
        assert "2 series" in html

    def test_legend_omitted_without_overlays(self) -> None:
        html = render_fragment(
            "workspace/regions/line_chart.html",
            title="X",
            bucketed_metrics=_PRIMARY_BUCKETS,
            reference_lines=[],
            reference_bands=[],
            overlay_series_data=[],
            empty_message="",
        )
        # Footer does NOT report series count when there's just one
        assert "2 series" not in html

    def test_multiple_overlays_get_distinct_colours(self) -> None:
        html = render_fragment(
            "workspace/regions/line_chart.html",
            title="X",
            bucketed_metrics=_PRIMARY_BUCKETS,
            reference_lines=[],
            reference_bands=[],
            overlay_series_data=[
                {
                    "label": "A",
                    "buckets": [{"label": "Sep", "value": 30}, {"label": "Oct", "value": 32}],
                },
                {
                    "label": "B",
                    "buckets": [{"label": "Sep", "value": 70}, {"label": "Oct", "value": 72}],
                },
            ],
            empty_message="",
        )
        # Each overlay polyline carries its colour as `stroke="hsl(...)"` —
        # two distinct hues from the palette
        assert 'stroke="hsl(145, 55%, 45%)"' in html
        assert 'stroke="hsl(40, 90%, 55%)"' in html
        # Footer reports 3 series (primary + 2 overlays)
        assert "3 series" in html
