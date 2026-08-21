"""Heatmap with group_by must not dump an empty/zero matrix (oral #151)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_region_computes import (
    compute_heatmap,
    heatmap_from_bucketed_metrics,
)
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeHeat:
    name = "alert_heatmap"
    title = "Alert heatmap"
    display = "heatmap"
    empty_message = "No alerts"


def test_ops_dashboard_alert_heatmap_is_group_by_only() -> None:
    spec = load_project(Path("examples/ops_dashboard"))
    region = None
    for ws in spec.workspaces:
        for r in ws.regions:
            if r.name == "alert_heatmap":
                region = r
                break
    assert region is not None
    assert (getattr(region, "heatmap_rows", None) or "") == ""
    assert (getattr(region, "heatmap_columns", None) or "") == ""
    gb = getattr(region, "group_by", None)
    assert gb == "severity" or getattr(gb, "field", None) == "severity"


def test_empty_axes_without_group_by_do_not_invent_display_matrix() -> None:
    items = [
        {"id": "a1", "_display": "Auth timeout", "severity": "critical"},
        {"id": "a2", "_display": "Disk full", "severity": "high"},
    ]
    matrix, cols = compute_heatmap(items, "", "", "")
    assert matrix == []
    assert cols == []


def test_group_by_counts_severity_not_zero_cells() -> None:
    items = [
        {"id": "a1", "severity": "critical", "_display": "Auth timeout"},
        {"id": "a2", "severity": "critical", "_display": "Disk full"},
        {"id": "a3", "severity": "low", "_display": "Info ping"},
        {"id": "a4", "severity": "zzz", "_display": "leftover"},
    ]
    matrix, cols = compute_heatmap(
        items,
        "",
        "",
        "",
        group_by="severity",
        bucket_values=["low", "medium", "high", "critical"],
    )
    assert cols == ["low", "medium", "high", "critical", "zzz"]
    assert matrix[0]["row"] == "Count"
    by_col = {c["column"]: c["value"] for c in matrix[0]["cells"]}
    assert by_col["critical"] == 2.0
    assert by_col["low"] == 1.0
    assert by_col["medium"] == 0.0
    assert by_col["zzz"] == 1.0


def test_bucketed_metrics_strip_preserves_leftover() -> None:
    buckets = [
        {"label": "low", "value": 3},
        {"label": "critical", "value": 8},
        {"label": "zzz", "value": 1},
    ]
    matrix, cols = heatmap_from_bucketed_metrics(
        buckets,
        bucket_values=["low", "medium", "high", "critical"],
    )
    assert cols == ["low", "medium", "high", "critical", "zzz"]
    by_col = {c["column"]: c["value"] for c in matrix[0]["cells"]}
    assert by_col["critical"] == 8.0
    assert by_col["medium"] == 0.0
    assert by_col["zzz"] == 1.0


def test_two_dim_heatmap_unchanged() -> None:
    items = [
        {"id": "1", "team": "platform", "status": "healthy", "latency_ms": 12},
        {"id": "2", "team": "payments", "status": "critical", "latency_ms": 40},
    ]
    matrix, cols = compute_heatmap(items, "team", "status", "latency_ms")
    assert cols == ["critical", "healthy"]
    rows = {row["row"]: {c["column"]: c["value"] for c in row["cells"]} for row in matrix}
    assert rows["platform"]["healthy"] == 12.0
    assert rows["payments"]["critical"] == 40.0


def test_heatmap_html_shows_counts_not_empty_state() -> None:
    matrix, cols = heatmap_from_bucketed_metrics(
        [{"label": "critical", "value": 4}, {"label": "zzz", "value": 1}],
        bucket_values=["low", "critical"],
    )
    node = WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
        _FakeHeat(),
        {
            "heatmap_matrix": matrix,
            "heatmap_col_values": cols,
            "empty_message": "No alerts",
        },
    )
    html = FragmentRenderer().render(node)
    assert "dz-heatmap-region" in html
    assert ">critical<" in html
    assert ">zzz<" in html
    assert "4" in html
    assert "No alerts" not in html
