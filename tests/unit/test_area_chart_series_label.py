"""Stacked area legend must not dump snake_case enum tokens (oral #148)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_region_render import (
    _clerk_series_dim_label,
    _pivot_to_series,
)
from dazzle.render.fragment.region._dispatcher import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeArea:
    name = "alerts_weekly_stacked"
    title = "Alerts weekly stacked"
    display = "area_chart"
    empty_message = "No alerts in the window"


_DIMS = [
    {"name": "triggered_at", "is_time_bucket": True},
    {"name": "severity", "is_time_bucket": False, "is_fk": False},
]


def test_ops_dashboard_alert_severity_includes_critical() -> None:
    spec = load_project(Path("examples/ops_dashboard"))
    alert = spec.get_entity("Alert")
    assert alert is not None
    severity = next(f for f in alert.fields if f.name == "severity")
    assert list(severity.type.enum_values or []) == ["low", "medium", "high", "critical"]


def test_clerk_series_dim_label_humanizes_snake_case() -> None:
    assert _clerk_series_dim_label({"severity": "in_progress"}, "severity") == "In Progress"
    assert _clerk_series_dim_label({"severity": "critical"}, "severity") == "Critical"
    assert _clerk_series_dim_label({"severity": "high"}, "severity") == "High"
    assert (
        _clerk_series_dim_label({"severity": "uuid-a", "severity_label": "Auth"}, "severity")
        == "Auth"
    )


def test_clerk_series_dim_label_leftover_stays_put() -> None:
    assert _clerk_series_dim_label({"severity": "zzz"}, "severity") == "zzz"
    assert _clerk_series_dim_label({"severity": None}, "severity") == "(none)"
    assert _clerk_series_dim_label({"severity": ""}, "severity") == "(none)"


def test_pivot_to_series_legend_is_in_progress_not_token() -> None:
    buckets = [
        {
            "triggered_at": "2026-06-01",
            "triggered_at_label": "W23",
            "severity": "in_progress",
            "count": 5,
        },
        {
            "triggered_at": "2026-06-01",
            "triggered_at_label": "W23",
            "severity": "open",
            "count": 2,
        },
    ]
    series = _pivot_to_series(buckets, _DIMS, "count")
    names = [s["name"] for s in series]
    assert names == ["In Progress", "Open"]
    assert "in_progress" not in names


def test_pivot_to_series_leftover_legend_stays_put() -> None:
    buckets = [
        {"triggered_at": "2026-06-01", "triggered_at_label": "W23", "severity": "zzz", "count": 1},
        {
            "triggered_at": "2026-06-01",
            "triggered_at_label": "W23",
            "severity": "critical",
            "count": 4,
        },
    ]
    series = _pivot_to_series(buckets, _DIMS, "count")
    names = [s["name"] for s in series]
    assert names == ["zzz", "Critical"]


def test_area_chart_legend_html_is_clerk_label() -> None:
    series = _pivot_to_series(
        [
            {
                "triggered_at": "2026-06-01",
                "triggered_at_label": "W23",
                "severity": "in_progress",
                "count": 5,
            },
            {
                "triggered_at": "2026-06-01",
                "triggered_at_label": "W23",
                "severity": "zzz",
                "count": 1,
            },
        ],
        _DIMS,
        "count",
    )
    node = WorkspaceRegionAdapter().build(_FakeArea(), {"series": series})  # type: ignore[arg-type]
    html = FragmentRenderer().render(node)
    assert "dz-chart-legend" in html
    assert ">In Progress<" in html
    assert ">zzz<" in html
    assert ">in_progress<" not in html
    assert ">critical<" not in html
