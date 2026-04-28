"""Tests for radar widget polar-cartesian geometry (#929).

The previous radar template used `<g transform="rotate">` chains
because Jinja can't call cos/sin directly. That approach silently
broke the data-vertex distribution — every dot ended up on the north
spoke regardless of which bucket it belonged to. The fix exposes a
`radar_polar_xy(index, count, ratio, cx, cy, r_max)` Jinja global
that does the polar→cartesian conversion in Python; the template
emits explicit (x, y) coords for every vertex / line / polygon.

These tests pin:
1. The polar-xy helper itself (4-spoke and 6-spoke shapes).
2. The rendered radar SVG distributes data circles across all spokes
   (regression test for the original bug — every circle had cx=160
   pre-fix).
"""

from __future__ import annotations

import math
import re

import pytest

pytest.importorskip("dazzle_ui.runtime.template_renderer")

from dazzle_ui.runtime.template_renderer import create_jinja_env  # noqa: E402


@pytest.fixture
def jinja_env():
    return create_jinja_env()


class TestRadarPolarXY:
    """The Jinja global `radar_polar_xy` is the single source of
    truth for radar spoke geometry. Pin every position so a future
    refactor can't silently shift the chart."""

    def test_helper_registered_on_env(self, jinja_env) -> None:
        assert "radar_polar_xy" in jinja_env.globals
        assert callable(jinja_env.globals["radar_polar_xy"])

    def test_four_spoke_compass_positions(self, jinja_env) -> None:
        """Four spokes at full radius land at N/E/S/W (12 / 3 / 6 / 9
        o'clock)."""
        polar = jinja_env.globals["radar_polar_xy"]
        # cx=160, cy=160, r_max=100 → spoke endpoint at 100px from centre.
        assert polar(0, 4, 1.0, 160, 160, 100) == pytest.approx({"x": 160.0, "y": 60.0}, abs=1e-6)
        assert polar(1, 4, 1.0, 160, 160, 100) == pytest.approx({"x": 260.0, "y": 160.0}, abs=1e-6)
        assert polar(2, 4, 1.0, 160, 160, 100) == pytest.approx({"x": 160.0, "y": 260.0}, abs=1e-6)
        assert polar(3, 4, 1.0, 160, 160, 100) == pytest.approx({"x": 60.0, "y": 160.0}, abs=1e-6)

    def test_ratio_scales_radius_linearly(self, jinja_env) -> None:
        """A ratio of 0.5 puts the vertex halfway between centre and
        outer ring; 0 puts it at centre; 1.0 at outer ring."""
        polar = jinja_env.globals["radar_polar_xy"]
        # Spoke 0 (north) at three different radii.
        assert polar(0, 4, 0.0, 160, 160, 100)["y"] == pytest.approx(160.0)
        assert polar(0, 4, 0.5, 160, 160, 100)["y"] == pytest.approx(110.0)
        assert polar(0, 4, 1.0, 160, 160, 100)["y"] == pytest.approx(60.0)

    def test_six_spokes_evenly_distributed(self, jinja_env) -> None:
        """Six spokes at 60° intervals — verify all six land on the
        outer circle (distance from centre == r_max)."""
        polar = jinja_env.globals["radar_polar_xy"]
        cx, cy, r = 160.0, 160.0, 100.0
        for i in range(6):
            p = polar(i, 6, 1.0, cx, cy, r)
            distance = math.hypot(p["x"] - cx, p["y"] - cy)
            assert distance == pytest.approx(r, abs=1e-6), f"spoke {i} off-circle"


class TestRadarTemplateRendering:
    """Render the radar template and verify the bug-class
    'every-dot-on-north-spoke' (#929) is gone — circles must have
    distinct cx values across spokes."""

    def _render(self, jinja_env, buckets: list[dict]) -> str:
        # Use the actual radar template via env.get_template — it sits
        # in workspace/regions/radar.html and is rendered by
        # `region_card`, but the inner SVG layer is what we want to
        # validate. Render it via from_string with an `include` so the
        # template's own dependency graph (region_card) resolves
        # naturally.
        tmpl = jinja_env.from_string("{% include 'workspace/regions/radar.html' %}")
        return tmpl.render(
            title="Test Radar",
            bucketed_metrics=buckets,
            empty_message="No data",
        )

    def test_four_spokes_yield_four_distinct_cx(self, jinja_env) -> None:
        """The smoking gun for #929: pre-fix every <circle> had cx=160
        (the chart centre's x). Post-fix circles distribute across
        roughly four distinct cx values matching N/E/S/W."""
        html = self._render(
            jinja_env,
            [
                {"label": "AO1", "value": 10.0, "metrics": {"avg_score": 10.0}},
                {"label": "AO2", "value": 8.0, "metrics": {"avg_score": 8.0}},
                {"label": "AO3", "value": 6.0, "metrics": {"avg_score": 6.0}},
                {"label": "AO4", "value": 4.0, "metrics": {"avg_score": 4.0}},
            ],
        )
        # Pull every <circle cx="..."> from the SVG output.
        cxs = sorted({float(m) for m in re.findall(r'<circle\s+cx="([\d.]+)"', html)})
        # Expect roughly 3 distinct cx values for a 4-spoke chart at
        # different ratios: north + south share cx=160 (vertical),
        # east at cx > 160, west at cx < 160. Pre-fix the only value
        # was 160.
        assert len(cxs) >= 3, f"expected ≥3 distinct cx values, got {cxs!r}"
        # And at least one cx must be left of centre, at least one right.
        assert any(c < 160 for c in cxs), f"no west-of-centre vertex in {cxs!r}"
        assert any(c > 160 for c in cxs), f"no east-of-centre vertex in {cxs!r}"

    def test_polygon_outline_uses_explicit_points(self, jinja_env) -> None:
        """Pre-fix the data outline was N rotated <line> segments with
        nonsensical endpoints. Post-fix it's a single <polygon> with
        explicit `points=...`. This is what gives radar its
        characteristic shaded shape."""
        html = self._render(
            jinja_env,
            [
                {"label": "A", "value": 3.0, "metrics": {"score": 3.0}},
                {"label": "B", "value": 5.0, "metrics": {"score": 5.0}},
                {"label": "C", "value": 7.0, "metrics": {"score": 7.0}},
                {"label": "D", "value": 9.0, "metrics": {"score": 9.0}},
            ],
        )
        # Match a polygon with a `points` list — at least the data poly
        # plus the four ring polys = 5 polygons in the output.
        polys = re.findall(r'<polygon\s+points="([^"]+)"', html)
        assert len(polys) >= 5, f"expected ≥5 polygons (4 rings + ≥1 data), got {len(polys)}"
        # Every polygon's points must contain commas (x,y pairs) and
        # ≥3 vertices. The data polygon should have 4 vertices for 4
        # spokes.
        data_poly_candidates = [p for p in polys if len(p.split()) == 4]
        assert data_poly_candidates, "no 4-vertex polygon found among the outputs"

    def test_no_g_transform_rotate_for_circles(self, jinja_env) -> None:
        """The whole-vertex `<g transform="rotate">` wrapper is the
        broken pattern — pin its absence so the regression can't recur
        via a copy-paste from another chart that still uses rotation."""
        html = self._render(
            jinja_env,
            [
                {"label": "A", "value": 3.0, "metrics": {"v": 3.0}},
                {"label": "B", "value": 5.0, "metrics": {"v": 5.0}},
                {"label": "C", "value": 7.0, "metrics": {"v": 7.0}},
            ],
        )
        # No <circle> should be wrapped in a rotate-transformed <g>.
        # Approximate check: there must not be a `<g transform="rotate`
        # immediately followed (within ~200 chars) by a `<circle`.
        offending = re.findall(r'<g\s+transform="rotate\([^)]+\)"\s*>\s*<circle', html)
        assert not offending, "circles should not sit inside rotated <g> wrappers post-#929"
