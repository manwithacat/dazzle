"""Radar / box-plot / heatmap axes must emit Api/Critical, not schema tokens (oral #188)."""

from __future__ import annotations

from pathlib import Path

from dazzle.render.filters import clerk_chart_axis_label, clerk_stage_label
from dazzle.render.fragment import BoxPlot, FragmentRenderer, Heatmap, HeatmapRow, Radar
from dazzle.render.fragment.region._builders_charts import _BuildersChartsMixin

OPS = Path("examples/ops_dashboard/dsl")


class _A(_BuildersChartsMixin):
    pass


def _radar_html(axes: list[object]) -> str:
    region = type(
        "R",
        (),
        {"name": "service_type_profile", "title": "Service types", "empty_message": None},
    )()
    ctx = {"axes": axes, "chart_label": "Service types"}
    return FragmentRenderer().render(_A()._build_radar(region, ctx))


def _box_html(groups: list[object]) -> str:
    region = type(
        "R",
        (),
        {"name": "response_time_spread", "title": "Spread", "empty_message": None},
    )()
    ctx = {"groups": groups, "chart_label": "Spread"}
    return FragmentRenderer().render(_A()._build_box_plot(region, ctx))


def _heat_html(columns: list[str], row: str = "Count") -> str:
    region = type("R", (), {"name": "alert_heatmap", "title": "Alerts", "empty_message": None})()
    cells = [{"column": c, "value": 1.0} for c in columns]
    ctx = {
        "heatmap_matrix": [{"row": row, "cells": cells}],
        "heatmap_col_values": columns,
    }
    return FragmentRenderer().render(_A()._build_heatmap(region, ctx))


def test_ops_dashboard_radar_service_type_is_live() -> None:
    block = (OPS / "app.dsl").read_text()
    region = block.split("  service_type_profile:", 1)[1].split("\n\n", 1)[0]
    assert "display: radar" in region
    assert "group_by: service_type" in region
    system = block.split("entity System", 1)[1].split("entity ", 1)[0]
    assert "service_type: enum[web,api,database,cache,queue]=web" in system


def test_ops_dashboard_box_plot_service_type_is_live() -> None:
    block = (OPS / "app.dsl").read_text()
    region = block.split("  response_time_spread:", 1)[1].split("\n\n", 1)[0]
    assert "display: box_plot" in region
    assert "group_by: service_type" in region


def test_ops_dashboard_heatmap_severity_is_live() -> None:
    block = (OPS / "app.dsl").read_text()
    region = block.split("  alert_heatmap:", 1)[1].split("\n\n", 1)[0]
    assert "display: heatmap" in region
    assert "group_by: severity" in region
    alert = block.split("entity Alert", 1)[1].split("entity ", 1)[0]
    assert "severity: enum[low,medium,high,critical]=low" in alert


def test_clerk_chart_axis_label_schema_not_raw() -> None:
    assert clerk_chart_axis_label("api") == "Api"
    assert clerk_chart_axis_label("critical") == "Critical"
    assert clerk_chart_axis_label("in_progress") == "In Progress"
    assert clerk_chart_axis_label("Auth timeout") == "Auth timeout"
    assert clerk_chart_axis_label("API") == "API"
    assert clerk_chart_axis_label("Count") == "Count"
    assert clerk_chart_axis_label(True) == "Yes"
    assert clerk_chart_axis_label("zzz") == "zzz"
    assert clerk_chart_axis_label("ghost") == "ghost"
    assert clerk_chart_axis_label("mon") == "Mon"
    assert clerk_chart_axis_label("g1") == "G1"
    assert clerk_chart_axis_label("p50") == "P50"
    assert clerk_stage_label("api") == "Api"


def test_radar_builder_api_is_api_title_not_schema() -> None:
    html = _radar_html([("api", 3), ("web", 2), ("database", 1)])
    assert ">Api<" in html
    assert ">Web<" in html
    assert ">Database<" in html
    assert ">api<" not in html
    leftover = _radar_html([("zzz", 1), ("ghost", 2), ("web", 3)])
    assert ">zzz<" in leftover
    assert ">ghost<" in leftover
    assert ">Zzz<" not in leftover


def test_radar_direct_emit_api_is_api_title() -> None:
    html = FragmentRenderer().render(
        Radar(label="Types", axes=(("api", 3.0), ("web", 2.0), ("database", 1.0)))
    )
    assert ">Api<" in html
    assert ">api<" not in html
    leftover = FragmentRenderer().render(
        Radar(label="Types", axes=(("zzz", 1.0), ("ghost", 2.0), ("web", 3.0)))
    )
    assert ">zzz<" in leftover
    assert ">ghost<" in leftover
    assert ">Zzz<" not in leftover


def test_box_plot_builder_api_is_api_title_not_schema() -> None:
    html = _box_html(
        [
            ("api", 0, 1, 2, 3, 4),
            ("web", 0, 1, 2, 3, 4),
        ]
    )
    assert ">Api<" in html
    assert ">Web<" in html
    assert ">api<" not in html
    leftover = _box_html([("zzz", 0, 1, 2, 3, 4)])
    assert ">zzz<" in leftover
    assert ">Zzz<" not in leftover


def test_box_plot_direct_emit_api_is_api_title() -> None:
    html = FragmentRenderer().render(
        BoxPlot(label="Spread", groups=(("api", 0.0, 1.0, 2.0, 3.0, 4.0),))
    )
    assert ">Api<" in html
    assert ">api<" not in html


def test_heatmap_builder_critical_is_title_not_schema() -> None:
    html = _heat_html(["low", "critical", "zzz"])
    assert ">Critical<" in html
    assert ">Low<" in html
    assert ">critical<" not in html
    assert ">zzz<" in html
    assert ">Zzz<" not in html
    count_row = _heat_html(["critical"], row="Count")
    assert ">Count<" in count_row


def test_heatmap_direct_emit_critical_is_title() -> None:
    html = FragmentRenderer().render(
        Heatmap(
            columns=("critical", "zzz"),
            rows=(HeatmapRow(label="Count", cells=(4.0, 1.0)),),
        )
    )
    assert ">Critical<" in html
    assert ">critical<" not in html
    assert ">zzz<" in html
    assert ">Count<" in html
