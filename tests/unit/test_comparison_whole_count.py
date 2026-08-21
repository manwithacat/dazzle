"""Comparison league must not dump integer counts as 12.00 (oral #153)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.region._builders_charts import _fmt_num
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeLeague:
    name = "system_alert_league"
    title = "System league"
    display = "comparison"
    empty_message = "No alerts to rank"


def test_ops_dashboard_system_alert_league_ranks_count() -> None:
    spec = load_project(Path("examples/ops_dashboard"))
    region = None
    for ws in spec.workspaces:
        for r in ws.regions:
            if r.name == "system_alert_league":
                region = r
                break
    assert region is not None
    assert str(getattr(region.display, "value", region.display)) == "comparison"
    assert getattr(region, "rank_by", None) == "count"
    aggs = getattr(region, "aggregates", None) or {}
    assert "count" in aggs


def test_fmt_num_whole_count_is_bare() -> None:
    assert _fmt_num(12.0) == "12"
    assert _fmt_num(12) == "12"
    assert _fmt_num(0.0) == "0"
    assert _fmt_num(12.5) == "12.50"


def test_fmt_num_leftover_stays_put() -> None:
    assert _fmt_num("zzz") == "zzz"
    assert _fmt_num("2abc") == "2abc"


def test_comparison_html_shows_bare_count_not_two_decimal() -> None:
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeLeague(),
            {
                "comparison_rows": [
                    {
                        "rank": 1,
                        "label": "Auth",
                        "value": 12.0,
                        "bar_fraction": 1.0,
                        "outlier": None,
                    },
                    {
                        "rank": 2,
                        "label": "Billing",
                        "value": 4.0,
                        "bar_fraction": 0.333,
                        "outlier": "low",
                    },
                    {
                        "rank": 3,
                        "label": "zzz",
                        "value": 1.0,
                        "bar_fraction": 0.083,
                        "outlier": None,
                    },
                    {
                        "rank": 4,
                        "label": "Latency",
                        "value": 12.5,
                        "bar_fraction": 1.0,
                        "outlier": "high",
                    },
                ],
                "comparison_max": 12.5,
            },
        )
    )
    assert 'aria-label="1. Auth: 12"' in html
    assert ">12</span>" in html
    assert "12.00" not in html
    assert "4.00" not in html
    assert "1.00" not in html
    assert "12.50" in html
    assert "zzz" in html
    assert "⚠ low" in html
    assert "No alerts to rank" not in html
