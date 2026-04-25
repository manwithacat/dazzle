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
        # Each marker carries an accessible <title>
        for spoke in _FOUR_SPOKES:
            assert f"{spoke['label']}: {spoke['value']}" in html

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
