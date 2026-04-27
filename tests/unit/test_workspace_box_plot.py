"""Tests for the v0.61.29 box plot display mode (#881).

Three layers:
  1. Parser: ``display: box_plot`` + ``value:`` + ``show_outliers:``.
  2. Runtime: ``_compute_box_plot_stats`` per-group quartile statistics
     using NumPy-default linear-interpolation (R "type 7") quartiles +
     Tukey 1.5×IQR fences for whiskers/outliers.
  3. Template: SVG box per group with whiskers, median line, outlier
     dots, and the empty-state fallback.
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
  ao: enum[ao1,ao2,ao3]
  scaled_mark: int
workspace dash "Dash":
  ao_spread:
    source: Mark
    display: box_plot
    group_by: ao
    value: scaled_mark
"""


# ───────────────────────────── parser ──────────────────────────────


class TestBoxPlotParser:
    def test_minimal_box_plot(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.display == DisplayMode.BOX_PLOT
        assert region.heatmap_value == "scaled_mark"
        assert region.show_outliers is True  # default

    def test_show_outliers_false(self) -> None:
        src = _BASE_DSL + "    show_outliers: false\n"
        region = _parse(src).workspaces[0].regions[0]
        assert region.show_outliers is False

    def test_show_outliers_invalid_raises(self) -> None:
        src = _BASE_DSL + "    show_outliers: maybe\n"
        with pytest.raises(Exception, match="show_outliers must be true or false"):
            _parse(src)


# ───────────────────────────── runtime ──────────────────────────────


class TestComputeBoxPlotStats:
    def setup_method(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _compute_box_plot_stats

        self.bp = _compute_box_plot_stats

    def test_single_group_quartile_math(self) -> None:
        """Standard Q1/median/Q3 for 1..10 (NumPy default / R type 7).

        Q1 = (10-1)*0.25 = 2.25 → between idx 2 (val 3) and idx 3 (val 4)
            → 3 + 0.25*(4-3) = 3.25
        Median = (10-1)*0.5 = 4.5 → between idx 4 (5) and idx 5 (6)
            → 5 + 0.5*(6-5) = 5.5
        Q3 = (10-1)*0.75 = 6.75 → between idx 6 (7) and idx 7 (8)
            → 7 + 0.75*(8-7) = 7.75
        """
        items = [{"v": float(i), "g": "A"} for i in range(1, 11)]
        stats = self.bp(items, "v", "g", show_outliers=True)
        assert len(stats) == 1
        s = stats[0]
        assert s["q1"] == pytest.approx(3.25)
        assert s["median"] == pytest.approx(5.5)
        assert s["q3"] == pytest.approx(7.75)
        assert s["min"] == 1.0 and s["max"] == 10.0
        assert s["n"] == 10
        assert s["outliers"] == []  # all points within fences

    def test_outlier_detection_via_tukey_fences(self) -> None:
        """A clear outlier (100) must land in `outliers`, not in
        whisker_high."""
        items = [{"v": v, "g": "X"} for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 100]]
        s = self.bp(items, "v", "g", show_outliers=True)[0]
        assert 100.0 in s["outliers"]
        assert s["whisker_high"] != 100.0  # whisker stops at last in-fence point

    def test_show_outliers_false_returns_empty_list(self) -> None:
        items = [{"v": v, "g": "X"} for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 100]]
        s = self.bp(items, "v", "g", show_outliers=False)[0]
        assert s["outliers"] == []

    def test_groups_preserve_first_seen_order(self) -> None:
        items = [
            {"v": 1, "g": "C"},
            {"v": 2, "g": "A"},
            {"v": 3, "g": "B"},
            {"v": 4, "g": "A"},
        ]
        stats = self.bp(items, "v", "g", show_outliers=True)
        assert [s["label"] for s in stats] == ["C", "A", "B"]

    def test_single_value_group_returns_degenerate_box(self) -> None:
        """n=1 returns Q1 = median = Q3 = the single value, IQR = 0,
        no outliers — so the template can render a flat marker without
        a divide-by-zero."""
        items = [{"v": 7.0, "g": "Solo"}]
        s = self.bp(items, "v", "g", show_outliers=True)[0]
        assert s["q1"] == s["median"] == s["q3"] == 7.0
        assert s["iqr"] == 0.0
        assert s["outliers"] == []
        assert s["n"] == 1

    def test_no_group_by_returns_one_global_bucket(self) -> None:
        items = [{"v": float(i)} for i in range(1, 11)]
        stats = self.bp(items, "v", group_by=None, show_outliers=True)
        assert len(stats) == 1
        assert stats[0]["label"] == ""
        assert stats[0]["n"] == 10

    def test_skips_non_numeric_values(self) -> None:
        items = [
            {"v": 1.0, "g": "A"},
            {"v": None, "g": "A"},
            {"v": "bad", "g": "A"},
            {"v": 9.0, "g": "A"},
        ]
        s = self.bp(items, "v", "g", show_outliers=True)[0]
        assert s["n"] == 2  # only 1.0 and 9.0

    def test_empty_input_returns_empty(self) -> None:
        assert self.bp([], "v", "g", show_outliers=True) == []

    # ─────────── FK display resolution (#889) ────────────

    def test_fk_dict_uses_display_sibling_for_bucket_label(self) -> None:
        """Pre-fix: `group_by: <fk_column>` produced ONE bucket whose
        label was the dict repr (e.g. ``"{'id': 'uuid…', '__display__':
        'AO1'}"``). Fix: `_compute_box_plot_stats` now reads the
        ``{group_by}_display`` sibling injected by
        `_inject_display_names()` first — same pattern as heatmap."""
        items = [
            {
                "v": 50.0,
                "ao": {"id": "u-1", "__display__": "AO1"},
                "ao_display": "AO1",
            },
            {
                "v": 70.0,
                "ao": {"id": "u-1", "__display__": "AO1"},
                "ao_display": "AO1",
            },
            {
                "v": 40.0,
                "ao": {"id": "u-2", "__display__": "AO2"},
                "ao_display": "AO2",
            },
        ]
        stats = self.bp(items, "v", "ao", show_outliers=True)
        assert len(stats) == 2  # NOT one bucket
        labels = sorted(s["label"] for s in stats)
        assert labels == ["AO1", "AO2"]

    def test_fk_dict_falls_back_to_resolve_display_name_without_sibling(
        self,
    ) -> None:
        """When `_inject_display_names()` hasn't run (e.g. partial item
        construction), fall back to `_resolve_display_name()` so the
        bucket label is still a string, not a dict repr."""
        items = [
            {"v": 50.0, "ao": {"id": "u-1", "__display__": "AO1"}},
            {"v": 70.0, "ao": {"id": "u-2", "__display__": "AO2"}},
        ]
        stats = self.bp(items, "v", "ao", show_outliers=True)
        labels = sorted(s["label"] for s in stats)
        assert labels == ["AO1", "AO2"]
        # Crucially: no dict repr in the labels
        assert not any("{" in label for label in labels)

    def test_scalar_group_by_still_works(self) -> None:
        """The FK fix must NOT break the existing scalar `group_by` case
        (e.g. `group_by: status` where status is an enum value)."""
        items = [
            {"v": 1.0, "status": "open"},
            {"v": 2.0, "status": "closed"},
            {"v": 3.0, "status": "open"},
        ]
        stats = self.bp(items, "v", "status", show_outliers=True)
        labels = sorted(s["label"] for s in stats)
        assert labels == ["closed", "open"]


# ─────────────────────── template rendering ─────────────────────


try:
    from dazzle_ui.runtime.template_renderer import render_fragment

    _HAS_TEMPLATES = True
except ImportError:
    _HAS_TEMPLATES = False


_THREE_GROUPS = [
    {
        "label": "AO1",
        "n": 10,
        "min": 30.0,
        "q1": 50.0,
        "median": 60.0,
        "q3": 72.0,
        "max": 85.0,
        "iqr": 22.0,
        "whisker_low": 30.0,
        "whisker_high": 85.0,
        "outliers": [],
    },
    {
        "label": "AO2",
        "n": 10,
        "min": 40.0,
        "q1": 45.0,
        "median": 58.0,
        "q3": 70.0,
        "max": 80.0,
        "iqr": 25.0,
        "whisker_low": 40.0,
        "whisker_high": 80.0,
        "outliers": [120.0],  # one explicit outlier
    },
    {
        "label": "AO3",
        "n": 10,
        "min": 30.0,
        "q1": 50.0,
        "median": 60.0,
        "q3": 70.0,
        "max": 85.0,
        "iqr": 20.0,
        "whisker_low": 30.0,
        "whisker_high": 85.0,
        "outliers": [],
    },
]


@pytest.mark.skipif(not _HAS_TEMPLATES, reason="dazzle_ui not installed")
class TestBoxPlotTemplate:
    def test_renders_box_per_group(self) -> None:
        html = render_fragment(
            "workspace/regions/box_plot.html",
            title="AO Spread",
            box_plot_stats=_THREE_GROUPS,
            reference_lines=[],
            empty_message="No marks.",
        )
        # 3 box rects (one per group)
        assert html.count("<rect") == 3
        # Group labels are emitted
        for g in _THREE_GROUPS:
            assert f">{g['label']}<" in html

    def test_outlier_renders_as_circle_with_tooltip(self) -> None:
        html = render_fragment(
            "workspace/regions/box_plot.html",
            title="X",
            box_plot_stats=_THREE_GROUPS,
            reference_lines=[],
            empty_message="",
        )
        # AO2 has one outlier value 120 → one <circle> + tooltip
        assert "AO2 outlier: 120" in html

    def test_horizontal_reference_line_renders(self) -> None:
        html = render_fragment(
            "workspace/regions/box_plot.html",
            title="X",
            box_plot_stats=_THREE_GROUPS,
            reference_lines=[{"label": "Pass", "value": 50, "style": "dashed"}],
            empty_message="",
        )
        assert "Pass: 50" in html
        assert 'stroke-dasharray="4,3"' in html

    def test_empty_stats_shows_empty_message(self) -> None:
        html = render_fragment(
            "workspace/regions/box_plot.html",
            title="X",
            box_plot_stats=[],
            reference_lines=[],
            empty_message="No data yet.",
        )
        assert "No data yet." in html
        assert "<svg" not in html

    def test_template_routing(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP["BOX_PLOT"] == "workspace/regions/box_plot.html"
