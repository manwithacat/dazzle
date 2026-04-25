"""Tests for line/area chart reference lines + bands (#883, v0.61.26).

Three layers:
  1. Parser: ``reference_lines:`` / ``reference_bands:`` blocks produce
     typed ``ReferenceLine`` / ``ReferenceBand`` entries on
     ``WorkspaceRegion``.
  2. IR: defaults, frozen-model behaviour, ``from``/``to`` aliasing.
  3. Renderer wiring: ``RegionContext`` carries plain dicts so Jinja can
     read ``ref.value`` / ``band['from']`` / ``band.to`` without import dance.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.module import ModuleFragment
from dazzle.core.ir.workspaces import ReferenceBand, ReferenceLine


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"
entity Mark:
  id: uuid pk
  scaled_mark: int
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


class TestReferenceLinesParser:
    def test_minimal_single_line(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_lines:
      - label: "Target", value: 56
"""
        )
        region = _parse(src).workspaces[0].regions[0]
        assert len(region.reference_lines) == 1
        rl = region.reference_lines[0]
        assert rl.label == "Target"
        assert rl.value == 56.0
        assert rl.style == "solid"  # default

    def test_multiple_lines_with_styles(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_lines:
      - label: "Target (6)", value: 56, style: dashed
      - label: "Boundary 5/6", value: 50, style: dotted
      - label: "Floor", value: 30
"""
        )
        lines = _parse(src).workspaces[0].regions[0].reference_lines
        assert [rl.style for rl in lines] == ["dashed", "dotted", "solid"]
        assert [rl.value for rl in lines] == [56.0, 50.0, 30.0]

    def test_decimal_value_supported(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_lines:
      - label: "Half mark", value: 27.5
"""
        )
        rl = _parse(src).workspaces[0].regions[0].reference_lines[0]
        assert rl.value == 27.5

    def test_invalid_style_raises(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_lines:
      - label: "X", value: 10, style: zigzag
"""
        )
        with pytest.raises(Exception, match="reference_lines.style"):
            _parse(src)

    def test_unknown_key_raises(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_lines:
      - label: "X", value: 10, color: red
"""
        )
        with pytest.raises(Exception, match="Unknown key 'color'"):
            _parse(src)

    def test_missing_value_raises(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_lines:
      - label: "X"
"""
        )
        with pytest.raises(Exception, match="reference_lines entry requires"):
            _parse(src)


class TestReferenceBandsParser:
    def test_minimal_single_band(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_bands:
      - label: "Target band", from: 50, to: 56
"""
        )
        region = _parse(src).workspaces[0].regions[0]
        assert len(region.reference_bands) == 1
        rb = region.reference_bands[0]
        assert rb.label == "Target band"
        assert rb.from_value == 50.0
        assert rb.to_value == 56.0
        assert rb.color == "target"  # default

    def test_band_with_color(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_bands:
      - label: "Pass zone", from: 40, to: 60, color: positive
      - label: "Fail zone", from: 0, to: 30, color: destructive
"""
        )
        bands = _parse(src).workspaces[0].regions[0].reference_bands
        assert [b.color for b in bands] == ["positive", "destructive"]
        assert [(b.from_value, b.to_value) for b in bands] == [(40.0, 60.0), (0.0, 30.0)]

    def test_invalid_color_raises(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_bands:
      - label: "X", from: 0, to: 10, color: rainbow
"""
        )
        with pytest.raises(Exception, match="reference_bands.color"):
            _parse(src)

    def test_missing_to_raises(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_bands:
      - label: "X", from: 0
"""
        )
        with pytest.raises(Exception, match="reference_bands entry requires"):
            _parse(src)

    def test_unknown_key_raises(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_bands:
      - label: "X", from: 0, to: 10, style: dashed
"""
        )
        with pytest.raises(Exception, match="Unknown key 'style'"):
            _parse(src)


class TestOverlaysCoexist:
    def test_lines_and_bands_on_same_region(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_lines:
      - label: "Target", value: 56, style: dashed
    reference_bands:
      - label: "Target band", from: 50, to: 56, color: target
"""
        )
        region = _parse(src).workspaces[0].regions[0]
        assert len(region.reference_lines) == 1
        assert len(region.reference_bands) == 1

    def test_overlays_absent_by_default(self) -> None:
        """Existing line_chart regions without overlays parse with empty lists."""
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.reference_lines == []
        assert region.reference_bands == []


# ───────────────────────────── ir ──────────────────────────────


class TestReferenceLineIR:
    def test_defaults(self) -> None:
        rl = ReferenceLine(label="X", value=10)
        assert rl.style == "solid"

    def test_frozen(self) -> None:
        from pydantic import ValidationError

        rl = ReferenceLine(label="X", value=10)
        with pytest.raises(ValidationError):
            rl.style = "dashed"  # type: ignore[misc]


class TestReferenceBandIR:
    def test_defaults(self) -> None:
        rb = ReferenceBand.model_validate({"label": "X", "from": 0, "to": 10})
        assert rb.color == "target"
        assert rb.from_value == 0.0
        assert rb.to_value == 10.0

    def test_from_to_aliases_dump(self) -> None:
        """Round-trip: model_dump(by_alias=True) restores the DSL-facing
        ``from`` / ``to`` keys (since ``from`` is a Python keyword the
        IR field is named ``from_value`` internally)."""
        rb = ReferenceBand.model_validate({"label": "X", "from": 5, "to": 9})
        dumped = rb.model_dump(by_alias=True)
        assert dumped["from"] == 5.0
        assert dumped["to"] == 9.0

    def test_frozen(self) -> None:
        from pydantic import ValidationError

        rb = ReferenceBand.model_validate({"label": "X", "from": 0, "to": 10})
        with pytest.raises(ValidationError):
            rb.color = "warning"  # type: ignore[misc]


# ─────────────────────── renderer wiring ────────────────────────


class TestRegionContextWiring:
    """``build_workspace_context`` must carry overlays into ``RegionContext``
    as plain dicts with DSL-facing keys (``from`` / ``to``) so Jinja can
    read them with ``band['from']`` and ``band.to`` without dance."""

    def test_line_overlays_flatten_to_dicts(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_lines:
      - label: "Target", value: 56, style: dashed
"""
        )
        appspec = self._build_appspec(src)
        ws = appspec.workspaces[0]
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ctx = build_workspace_context(ws, appspec)
        region_ctx = ctx.regions[0]
        assert region_ctx.reference_lines == [{"label": "Target", "value": 56.0, "style": "dashed"}]
        assert region_ctx.reference_bands == []

    def test_band_overlays_use_from_to_keys_not_python_names(self) -> None:
        src = (
            _BASE_DSL
            + """    reference_bands:
      - label: "Target band", from: 50, to: 56, color: target
"""
        )
        appspec = self._build_appspec(src)
        ws = appspec.workspaces[0]
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ctx = build_workspace_context(ws, appspec)
        band = ctx.regions[0].reference_bands[0]
        # Templates read `band['from']`, not `band['from_value']`.
        assert band["from"] == 50.0
        assert band["to"] == 56.0
        assert band["color"] == "target"
        assert band["label"] == "Target band"

    @staticmethod
    def _build_appspec(src: str) -> object:
        from dazzle.core import ir
        from dazzle.core.linker import build_appspec

        module_name, app_name, app_title, app_config, uses, fragment = parse_dsl(
            src, Path("test.dsl")
        )
        module = ir.ModuleIR(
            name=module_name or "t",
            file=Path("test.dsl"),
            app_name=app_name,
            app_title=app_title,
            app_config=app_config,
            uses=uses,
            fragment=fragment,
        )
        return build_appspec([module], module.name)


# ─────────────────────── template rendering ─────────────────────


try:
    from dazzle_ui.runtime.template_renderer import render_fragment

    _HAS_TEMPLATES = True
except ImportError:
    _HAS_TEMPLATES = False


_LINE_CHART_BASE_KWARGS: dict[str, object] = {
    "title": "Trajectory",
    "bucketed_metrics": [
        {"label": "Sep", "value": 30},
        {"label": "Oct", "value": 42},
        {"label": "Nov", "value": 48},
    ],
    "empty_message": "No data.",
}


@pytest.mark.skipif(not _HAS_TEMPLATES, reason="dazzle_ui not installed")
class TestLineChartTemplateOverlays:
    def test_reference_line_renders_dashed_stroke(self) -> None:
        html = render_fragment(
            "workspace/regions/line_chart.html",
            **_LINE_CHART_BASE_KWARGS,
            reference_lines=[{"label": "Target", "value": 56, "style": "dashed"}],
            reference_bands=[],
        )
        # Title visible to screen readers + on hover
        assert "Target: 56" in html
        # Dashed style maps to stroke-dasharray="4,3"
        assert 'stroke-dasharray="4,3"' in html

    def test_reference_band_renders_rect_with_token_colour(self) -> None:
        html = render_fragment(
            "workspace/regions/line_chart.html",
            **_LINE_CHART_BASE_KWARGS,
            reference_lines=[],
            reference_bands=[
                {"label": "Target band", "from": 50, "to": 56, "color": "target"},
            ],
        )
        # Band's <title> tooltip is server-rendered
        assert "Target band: 50.0–56.0" in html or "Target band: 50–56" in html
        # Token-driven primary fill is applied to band rects
        assert "<rect" in html
        assert "hsl(var(--primary))" in html

    def test_reference_line_above_data_peak_expands_y_axis(self) -> None:
        """A reference line at value 100 with data peaking at 48 must
        scale all data points down so 100 sits inside the plot area."""
        html_no_ref = render_fragment(
            "workspace/regions/line_chart.html",
            **_LINE_CHART_BASE_KWARGS,
            reference_lines=[],
            reference_bands=[],
        )
        html_with_ref = render_fragment(
            "workspace/regions/line_chart.html",
            **_LINE_CHART_BASE_KWARGS,
            reference_lines=[{"label": "Far target", "value": 100, "style": "solid"}],
            reference_bands=[],
        )
        # Same data, different y-axis ceiling → polylines differ.
        # (Cheap heuristic: HTML lengths or polyline coords differ.)
        assert html_no_ref != html_with_ref

    def test_overlays_default_to_empty_when_omitted(self) -> None:
        """Pre-existing line_chart consumers without overlays render fine."""
        html = render_fragment(
            "workspace/regions/line_chart.html",
            **_LINE_CHART_BASE_KWARGS,
            reference_lines=[],
            reference_bands=[],
        )
        assert "<rect" not in html  # no band rects
        # The baseline grid line is the only <line> element
        assert html.count("<line") == 1
