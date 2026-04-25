"""Tests for the v0.61.30 bullet chart display mode (#880).

Three layers:
  1. Parser: ``display: bullet`` + ``bullet_label`` / ``bullet_actual`` /
     ``bullet_target`` column refs parse into the IR.
  2. Runtime: rendering branch reads each item's three columns, computes
     the shared ``bullet_max_value`` across actual + target + reference
     band extents.
  3. Template: ``bullet.html`` renders one row per item with the actual
     bar, optional target tick, and reference-band zones; honours the
     empty-state fallback.

Pre-computed MVP — per-group_by aggregation deferred (would need
multi-measure support in `_compute_bucketed_aggregates`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import DisplayMode
from dazzle.core.ir.module import ModuleFragment


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"
entity AOSummary:
  id: uuid pk
  name: str(50)
  actual: float
  target: float
workspace dash "Dash":
  ao_bullets:
    source: AOSummary
    display: bullet
    bullet_label: name
    bullet_actual: actual
    bullet_target: target
"""


# ───────────────────────────── parser ──────────────────────────────


class TestBulletParser:
    def test_minimal_bullet(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.display == DisplayMode.BULLET
        assert region.bullet_label == "name"
        assert region.bullet_actual == "actual"
        assert region.bullet_target == "target"

    def test_bullet_with_reference_bands(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_bands:
      - label: "On target", from: 60, to: 100, color: positive
      - label: "Below", from: 0, to: 40, color: destructive
"""
        )
        region = _parse(src).workspaces[0].regions[0]
        assert len(region.reference_bands) == 2
        assert region.reference_bands[0].color == "positive"

    def test_bullet_target_optional(self) -> None:
        src = """module t
app t "Test"
entity AOSummary:
  id: uuid pk
  name: str(50)
  actual: float
workspace dash "Dash":
  ao_bullets:
    source: AOSummary
    display: bullet
    bullet_label: name
    bullet_actual: actual
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.bullet_target is None
        assert region.bullet_actual == "actual"


# ─────────────────────── template rendering ─────────────────────


try:
    from dazzle_ui.runtime.template_renderer import render_fragment

    _HAS_TEMPLATES = True
except ImportError:
    _HAS_TEMPLATES = False


_FOUR_ROWS = [
    {"label": "AO1", "actual": 65.0, "target": 70.0},
    {"label": "AO2", "actual": 75.0, "target": 60.0},
    {"label": "AO3", "actual": 45.0, "target": 60.0},
    {"label": "AO4", "actual": 60.0, "target": 60.0},
]


@pytest.mark.skipif(not _HAS_TEMPLATES, reason="dazzle_ui not installed")
class TestBulletTemplate:
    def test_renders_one_row_per_item(self) -> None:
        html = render_fragment(
            "workspace/regions/bullet.html",
            title="AO Progress",
            bullet_rows=_FOUR_ROWS,
            bullet_max_value=100.0,
            reference_bands=[],
            empty_message="No data.",
        )
        # 4 rows → 4 actual bars + 4 target ticks
        assert html.count("dz-bullet-actual") == 4
        assert html.count("dz-bullet-target") == 4
        for row in _FOUR_ROWS:
            assert f">{row['label']}<" in html

    def test_target_omitted_when_none(self) -> None:
        rows = [{"label": "AO1", "actual": 65.0, "target": None}]
        html = render_fragment(
            "workspace/regions/bullet.html",
            title="AO Progress",
            bullet_rows=rows,
            bullet_max_value=100.0,
            reference_bands=[],
            empty_message="",
        )
        # Actual bar present, target tick suppressed
        assert "dz-bullet-actual" in html
        assert "dz-bullet-target" not in html

    def test_reference_bands_render_zones(self) -> None:
        html = render_fragment(
            "workspace/regions/bullet.html",
            title="X",
            bullet_rows=_FOUR_ROWS,
            bullet_max_value=100.0,
            reference_bands=[
                {"label": "On target", "from": 60, "to": 100, "color": "positive"},
                {"label": "Below", "from": 0, "to": 40, "color": "destructive"},
            ],
            empty_message="",
        )
        # Each row carries 2 band zones → 8 total
        assert html.count("dz-bullet-band") == 8
        assert "On target: 60–100" in html

    def test_actual_bar_width_proportional_to_max(self) -> None:
        """actual=50, max=100 → width 50.00%; actual=100, max=100 → 100%."""
        rows = [
            {"label": "Half", "actual": 50.0, "target": None},
            {"label": "Full", "actual": 100.0, "target": None},
        ]
        html = render_fragment(
            "workspace/regions/bullet.html",
            title="X",
            bullet_rows=rows,
            bullet_max_value=100.0,
            reference_bands=[],
            empty_message="",
        )
        assert "width: 50.0%" in html or "width: 50%" in html
        assert "width: 100.0%" in html or "width: 100%" in html

    def test_empty_rows_shows_empty_message(self) -> None:
        html = render_fragment(
            "workspace/regions/bullet.html",
            title="X",
            bullet_rows=[],
            bullet_max_value=0.0,
            reference_bands=[],
            empty_message="No bullets yet.",
        )
        assert "No bullets yet." in html
        assert "dz-bullet-row" not in html

    def test_zero_max_falls_back_to_empty_state(self) -> None:
        """All-zero actuals shouldn't crash — fall back to empty state."""
        html = render_fragment(
            "workspace/regions/bullet.html",
            title="X",
            bullet_rows=[{"label": "A", "actual": 0.0, "target": None}],
            bullet_max_value=0.0,
            reference_bands=[],
            empty_message="No measurable data.",
        )
        assert "No measurable data." in html

    def test_template_routing(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP["BULLET"] == "workspace/regions/bullet.html"
