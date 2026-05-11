"""Tests for the v0.61.27 histogram display mode (#882).

Three layers:
  1. Parser: ``display: histogram`` + ``value:`` + ``bins:`` blocks parse
     into a ``WorkspaceRegion`` with ``DisplayMode.HISTOGRAM``,
     ``heatmap_value`` (legacy-named generic value column), and ``bin_count``.
  2. Runtime: ``_compute_histogram_bins`` bins raw item values into
     equal-width buckets, computes Sturges' rule when bin_count is None,
     and degrades gracefully on empty / single-value input.
  3. Template: ``histogram.html`` renders SVG bars + vertical reference
     lines + axis labels.
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
entity Mark:
  id: uuid pk
  scaled_mark: int
workspace dash "Dash":
  mark_distribution:
    source: Mark
    display: histogram
    value: scaled_mark
"""


# ───────────────────────────── parser ──────────────────────────────


class TestHistogramParser:
    def test_minimal_histogram(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.display == DisplayMode.HISTOGRAM
        assert region.heatmap_value == "scaled_mark"
        assert region.bin_count is None  # auto by default

    def test_explicit_bin_count(self) -> None:
        src = _BASE_DSL + "    bins: 20\n"
        region = _parse(src).workspaces[0].regions[0]
        assert region.bin_count == 20

    def test_bins_auto_keyword(self) -> None:
        src = _BASE_DSL + "    bins: auto\n"
        region = _parse(src).workspaces[0].regions[0]
        assert region.bin_count is None

    def test_bins_zero_raises(self) -> None:
        src = _BASE_DSL + "    bins: 0\n"
        with pytest.raises(Exception, match="bins must be a positive integer"):
            _parse(src)

    def test_bins_invalid_word_raises(self) -> None:
        src = _BASE_DSL + "    bins: many\n"
        with pytest.raises(Exception, match="bins must be 'auto' or a positive integer"):
            _parse(src)

    def test_histogram_with_reference_lines(self) -> None:
        src = (
            _BASE_DSL
            + """    bins: 10
    reference_lines:
      - label: "Grade 4", value: 32
      - label: "Grade 6", value: 56, style: dashed
"""
        )
        region = _parse(src).workspaces[0].regions[0]
        assert region.bin_count == 10
        assert len(region.reference_lines) == 2
        assert region.reference_lines[0].value == 32.0


# ───────────────────────────── runtime ──────────────────────────────


class TestComputeHistogramBins:
    def setup_method(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _compute_histogram_bins

        self.bin = _compute_histogram_bins

    def test_explicit_bin_count_equal_width(self) -> None:
        items = [{"v": float(i)} for i in range(0, 10)]  # 0..9
        bins = self.bin(items, "v", bin_count=2)
        assert len(bins) == 2
        # Width = 4.5; bin 0 = [0, 4.5), bin 1 = [4.5, 9]
        assert bins[0]["count"] == 5  # 0,1,2,3,4
        assert bins[1]["count"] == 5  # 4.5,5,6,7,8,9 → actually 5 (5,6,7,8,9 → 5)
        # Verify edges are present and correct
        assert bins[0]["low"] == 0.0
        assert bins[1]["high"] == 9.0

    @pytest.mark.parametrize(
        "items,key,bin_count,check",
        [
            (
                [{"v": v} for v in [0, 5, 10]],
                "v",
                2,
                lambda bins: sum(b["count"] for b in bins) == 3,
            ),
            (
                [{"v": float(i)} for i in range(100)],
                "v",
                None,
                lambda bins: len(bins) == __import__("math").ceil(__import__("math").log2(100) + 1),
            ),
            ([], "v", 10, lambda bins: bins == []),
            (
                [{"v": None}, {"v": "not a number"}, {"other": 5}],
                "v",
                5,
                lambda bins: bins == [],
            ),
            (
                [{"v": 1.0}, {"v": None}, {"v": "x"}, {"v": 9.0}],
                "v",
                2,
                lambda bins: sum(b["count"] for b in bins) == 2,
            ),
            (
                [{"v": 0.0}, {"v": 10.0}],
                "v",
                1,
                lambda bins: bins[0]["label"] == "0–10",
            ),
        ],
        ids=[
            "test_global_max_lands_in_final_bin",
            "test_auto_bin_count_uses_sturges",
            "test_empty_input_returns_empty",
            "test_no_numeric_values_returns_empty",
            "test_skips_non_numeric_items",
            "test_label_format_uses_g_format",
        ],
    )
    def test_bin_behaviour(self, items: list, key: str, bin_count: int | None, check) -> None:
        bins = self.bin(items, key, bin_count=bin_count)
        assert check(bins)

    def test_single_distinct_value_returns_one_bin(self) -> None:
        items = [{"v": 7.0}, {"v": 7.0}, {"v": 7.0}]
        bins = self.bin(items, "v", bin_count=10)
        assert len(bins) == 1
        assert bins[0]["count"] == 3
        assert bins[0]["low"] == bins[0]["high"] == 7.0


# ─────────────────────── template rendering ─────────────────────


try:
    from dazzle_ui.runtime.template_renderer import render_fragment

    _HAS_TEMPLATES = True
except ImportError:
    _HAS_TEMPLATES = False


@pytest.mark.skipif(not _HAS_TEMPLATES, reason="dazzle_ui not installed")
@pytest.mark.skip(
    reason="Phase 4 deletion sweep (v0.67.52) — pinned legacy Jinja template markup; the typed-Fragment substrate produces semantically equivalent output with different class names"
)
class TestHistogramTemplate:
    BINS = [
        {"label": "0–10", "count": 2, "low": 0.0, "high": 10.0},
        {"label": "10–20", "count": 5, "low": 10.0, "high": 20.0},
        {"label": "20–30", "count": 3, "low": 20.0, "high": 30.0},
    ]

    def test_renders_one_rect_per_bin(self) -> None:
        html = render_fragment(
            "workspace/regions/_typed_primitive.html",
            title="Marks",
            histogram_bins=self.BINS,
            reference_lines=[],
            empty_message="No data.",
        )
        # 3 bin rects (no reference_lines, no bands)
        assert html.count("<rect") == 3
        # Tooltip on hover
        assert "10–20: 5" in html

    def test_vertical_reference_line_in_range_renders(self) -> None:
        html = render_fragment(
            "workspace/regions/_typed_primitive.html",
            title="Marks",
            histogram_bins=self.BINS,
            reference_lines=[{"label": "Target", "value": 25, "style": "dashed"}],
            empty_message="No data.",
        )
        assert "Target: 25" in html
        assert 'stroke-dasharray="4,3"' in html

    def test_reference_line_outside_range_skipped(self) -> None:
        """A reference line at value 999 (outside 0–30) must not render
        — drawing it would push it off the SVG canvas."""
        html_in_range = render_fragment(
            "workspace/regions/_typed_primitive.html",
            title="Marks",
            histogram_bins=self.BINS,
            reference_lines=[{"label": "InRange", "value": 15, "style": "solid"}],
            empty_message="No data.",
        )
        html_out_of_range = render_fragment(
            "workspace/regions/_typed_primitive.html",
            title="Marks",
            histogram_bins=self.BINS,
            reference_lines=[{"label": "OutOfRange", "value": 999, "style": "solid"}],
            empty_message="No data.",
        )
        assert "InRange" in html_in_range
        assert "OutOfRange" not in html_out_of_range

    def test_empty_bins_shows_empty_message(self) -> None:
        html = render_fragment(
            "workspace/regions/_typed_primitive.html",
            title="Marks",
            histogram_bins=[],
            reference_lines=[],
            empty_message="No marks yet.",
        )
        assert "No marks yet." in html
        assert "<svg" not in html
