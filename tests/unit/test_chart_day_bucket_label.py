"""Time-bucket day axes must not dump ISO storage dates (oral #150)."""

from __future__ import annotations

import datetime as dt

from dazzle.http.runtime.workspace_aggregation import _format_bucket_label
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeLine:
    name = "alerts_timeseries"
    title = "Alerts timeseries"
    display = "line_chart"
    empty_message = "No alerts in the window"


def test_day_bucket_uses_profile_not_iso() -> None:
    d = dt.datetime(2026, 5, 18, 14, 30)
    assert _format_bucket_label(d, "day") == "18 May 2026"
    assert _format_bucket_label(dt.date(2026, 5, 18), "day") == "18 May 2026"


def test_day_bucket_leftover_stays_put() -> None:
    assert _format_bucket_label("zzz", "day") == "zzz"
    assert _format_bucket_label("2026-05-18", "day") == "2026-05-18"
    assert _format_bucket_label(None, "day") == ""


def test_week_month_ticks_stay_compact() -> None:
    d = dt.datetime(2026, 5, 18, 14, 30)
    assert _format_bucket_label(d, "week") == "2026-W21"
    assert _format_bucket_label(d, "month") == "May 2026"


def test_line_chart_axis_html_is_profile_date_not_iso() -> None:
    day = _format_bucket_label(dt.datetime(2026, 5, 18, 14, 30), "day")
    leftover = _format_bucket_label("zzz", "day")
    node = WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
        _FakeLine(),
        {
            "points": [
                {"label": day, "value": 5},
                {"label": leftover, "value": 1},
            ]
        },
    )
    html = FragmentRenderer().render(node)
    assert "18 May 2026" in html
    assert ">zzz<" in html or "zzz</text>" in html
    assert "2026-05-18" not in html
