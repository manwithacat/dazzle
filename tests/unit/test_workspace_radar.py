"""Tests for the v0.61.28 radar/polar chart display mode (#879).

Two layers:
  1. Parser: ``display: radar`` parses into ``DisplayMode.RADAR`` and
     accepts the same single-dim ``group_by`` + ``aggregates`` shape as
     ``bar_chart``.
  2. Template: ``radar.html`` renders an SVG polar grid + vertex
     markers + outline polygon (as rotated <line> segments since pure
     Jinja can't compute cos/sin), with the degenerate ``< 3 spokes``
     fallback list and the empty-state message.

Multi-series support (target overlay polygon) is deferred — the runtime
extension to return all aggregates from ``_compute_bucketed_aggregates``
is tracked separately.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import DisplayMode
from dazzle.core.ir.module import ModuleFragment


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


# ───────────────────────────── parser ──────────────────────────────


class TestRadarParser:
    def test_minimal_radar_region(self) -> None:
        src = """module t
app t "Test"
entity Mark:
  id: uuid pk
  ao: enum[ao1,ao2,ao3,ao4]
workspace dash "Dash":
  ao_profile:
    source: Mark
    display: radar
    group_by: ao
    aggregate:
      pct: count(Mark where ao = current_bucket)
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.display == DisplayMode.RADAR
        assert region.group_by == "ao"
        # Parser tokenises and reassembles aggregate exprs with spaces.
        assert "pct" in region.aggregates
        expr = region.aggregates["pct"]
        assert "count" in expr and "Mark" in expr and "current_bucket" in expr


# ─────────────────────── template rendering ─────────────────────


try:
    from dazzle_ui.runtime.template_renderer import render_fragment

    _HAS_TEMPLATES = True
except ImportError:
    _HAS_TEMPLATES = False


_FOUR_SPOKES = [
    {"label": "AO1", "value": 75},
    {"label": "AO2", "value": 60},
    {"label": "AO3", "value": 45},
    {"label": "AO4", "value": 80},
]


@pytest.mark.skipif(not _HAS_TEMPLATES, reason="dazzle_ui not installed")
class TestRadarTemplate:
    def test_renders_one_marker_per_spoke(self) -> None:
        html = render_fragment(
            "workspace/regions/radar.html",
            title="AO Profile",
            bucketed_metrics=_FOUR_SPOKES,
            empty_message="No marks.",
        )
        # 4 spokes → 4 <circle> vertex markers
        assert html.count("<circle") == 4
        # Each marker carries an accessible <title>. v0.61.32 (#879
        # multi-series) annotates the tooltip with the series name —
        # for a single-series legacy bucket the series defaults to
        # "value", so the tooltip is `<spoke> value: <n>`.
        for spoke in _FOUR_SPOKES:
            assert f"{spoke['label']} value: {spoke['value']}" in html

    def test_renders_spoke_axis_per_bucket(self) -> None:
        html = render_fragment(
            "workspace/regions/radar.html",
            title="AO Profile",
            bucketed_metrics=_FOUR_SPOKES,
            empty_message="No marks.",
        )
        # Spoke axis lines: one <g rotate> with <line x1 y1 x2 y2> from
        # centre to r_max edge per spoke. Other rotated <line> elements
        # exist for ring segments and outline polygon — count just the
        # spoke-axis ones via the centre→edge pattern.
        # Simpler check: spoke labels are emitted once each.
        for spoke in _FOUR_SPOKES:
            assert f">{spoke['label']}<" in html

    def test_renders_3_spoke_minimum_polygon(self) -> None:
        """Exactly 3 spokes is the minimum for a real polygon — must
        render the SVG, not the degenerate fallback."""
        three = _FOUR_SPOKES[:3]
        html = render_fragment(
            "workspace/regions/radar.html",
            title="X",
            bucketed_metrics=three,
            empty_message="",
        )
        assert "<svg" in html
        assert "Radar needs" not in html  # degenerate fallback NOT shown

    def test_two_spokes_falls_back_to_value_list(self) -> None:
        """Fewer than 3 spokes is a degenerate radar; render a compact
        list instead of an empty SVG."""
        two = _FOUR_SPOKES[:2]
        html = render_fragment(
            "workspace/regions/radar.html",
            title="X",
            bucketed_metrics=two,
            empty_message="",
        )
        assert "<svg" not in html
        assert "Radar needs" in html
        assert "AO1" in html
        assert "AO2" in html

    def test_empty_data_shows_empty_message(self) -> None:
        html = render_fragment(
            "workspace/regions/radar.html",
            title="X",
            bucketed_metrics=[],
            empty_message="No marks yet.",
        )
        assert "No marks yet." in html
        assert "<svg" not in html

    def test_zero_max_value_does_not_crash(self) -> None:
        """All-zero values would cause divide-by-zero without the
        ``max_val if max_val > 0 else 1`` guard."""
        zeros = [
            {"label": "A", "value": 0},
            {"label": "B", "value": 0},
            {"label": "C", "value": 0},
        ]
        html = render_fragment(
            "workspace/regions/radar.html",
            title="X",
            bucketed_metrics=zeros,
            empty_message="",
        )
        assert "<svg" in html  # rendered, not exception

    def test_display_template_map_routes_radar(self) -> None:
        """Sanity: DISPLAY_TEMPLATE_MAP['RADAR'] points at the new template."""
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP["RADAR"] == "workspace/regions/radar.html"


@pytest.mark.skipif(not _HAS_TEMPLATES, reason="dazzle_ui not installed")
class TestRadarMultiSeries:
    """v0.61.32 (#879 multi-series): radar can render multiple polygons
    when each bucket carries a `metrics` sub-dict from the multi-measure
    aggregate pipeline."""

    MULTI_SERIES_BUCKETS = [
        {"label": "AO1", "value": 65, "metrics": {"actual": 65, "target": 70}},
        {"label": "AO2", "value": 75, "metrics": {"actual": 75, "target": 60}},
        {"label": "AO3", "value": 45, "metrics": {"actual": 45, "target": 60}},
        {"label": "AO4", "value": 60, "metrics": {"actual": 60, "target": 60}},
    ]

    def test_two_series_render_two_polygons(self) -> None:
        html = render_fragment(
            "workspace/regions/radar.html",
            title="AO Profile",
            bucketed_metrics=self.MULTI_SERIES_BUCKETS,
            empty_message="",
        )
        # Each series → 4 spoke vertices, so 2 series → 8 <circle>s
        assert html.count("<circle") == 8

    def test_per_series_tooltip_carries_series_name(self) -> None:
        html = render_fragment(
            "workspace/regions/radar.html",
            title="X",
            bucketed_metrics=self.MULTI_SERIES_BUCKETS,
            empty_message="",
        )
        assert "AO1 actual: 65" in html
        assert "AO1 target: 70" in html

    def test_legend_appears_for_multi_series(self) -> None:
        html = render_fragment(
            "workspace/regions/radar.html",
            title="X",
            bucketed_metrics=self.MULTI_SERIES_BUCKETS,
            empty_message="",
        )
        # Series names show up in the legend below the chart
        assert "actual" in html and "target" in html
        assert "2 series" in html

    def test_legend_omitted_for_single_series(self) -> None:
        single_series = [
            {"label": "AO1", "value": 65, "metrics": {"actual": 65}},
            {"label": "AO2", "value": 75, "metrics": {"actual": 75}},
            {"label": "AO3", "value": 45, "metrics": {"actual": 45}},
        ]
        html = render_fragment(
            "workspace/regions/radar.html",
            title="X",
            bucketed_metrics=single_series,
            empty_message="",
        )
        # Legend swatch <span class="inline-block w-2.5 h-2.5"> is the
        # giveaway for a rendered legend.
        assert "w-2.5 h-2.5 rounded-sm" not in html
        assert "1 series" in html

    def test_y_axis_max_spans_all_series(self) -> None:
        """If series A peaks at 50 and series B peaks at 100, the radius
        scale must use 100 so series B reaches the outer ring."""
        buckets = [
            {"label": "X", "value": 50, "metrics": {"a": 50, "b": 100}},
            {"label": "Y", "value": 30, "metrics": {"a": 30, "b": 80}},
            {"label": "Z", "value": 40, "metrics": {"a": 40, "b": 90}},
        ]
        html = render_fragment(
            "workspace/regions/radar.html",
            title="X",
            bucketed_metrics=buckets,
            empty_message="",
        )
        # Footer reports the global peak across both series
        assert "peak 100" in html
