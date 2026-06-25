"""Adapter-layer shaping of multi-series time-series data (#1473).

`_pivot_to_series` turns the flat pivot_buckets cells of a stacked
area_chart into one named series per series-dimension value;
`_overlays_to_series` turns a base bucketed_metrics + overlay_series_data
into a base series plus one series per overlay.
"""

from dazzle.http.runtime.workspace_region_render import (
    _overlays_to_series,
    _pivot_to_series,
)


def test_pivot_to_series_groups_by_second_dimension() -> None:
    # group_by: [bucket(triggered_at, week), severity]
    dim_specs = [
        {"name": "triggered_at", "is_time_bucket": True},
        {"name": "severity", "is_time_bucket": False, "is_fk": False},
    ]
    buckets = [
        {"triggered_at": "2026-06-01", "triggered_at_label": "W23", "severity": "high", "count": 5},
        {"triggered_at": "2026-06-01", "triggered_at_label": "W23", "severity": "low", "count": 2},
        {"triggered_at": "2026-06-08", "triggered_at_label": "W24", "severity": "high", "count": 7},
        {"triggered_at": "2026-06-08", "triggered_at_label": "W24", "severity": "low", "count": 3},
    ]
    series = _pivot_to_series(buckets, dim_specs, "count")
    assert [s["name"] for s in series] == ["high", "low"]
    assert series[0]["points"] == [
        {"label": "W23", "value": 5.0},
        {"label": "W24", "value": 7.0},
    ]
    assert series[1]["points"] == [
        {"label": "W23", "value": 2.0},
        {"label": "W24", "value": 3.0},
    ]


def test_pivot_to_series_uses_fk_label_when_present() -> None:
    dim_specs = [
        {"name": "opened_at", "is_time_bucket": True},
        {"name": "team_id", "is_time_bucket": False, "is_fk": True},
    ]
    buckets = [
        {
            "opened_at": "2026-06-01",
            "opened_at_label": "Jun 1",
            "team_id": "uuid-a",
            "team_id_label": "Platform",
            "count": 4,
        },
    ]
    series = _pivot_to_series(buckets, dim_specs, "count")
    assert series[0]["name"] == "Platform"


def test_pivot_to_series_substitutes_sentinel_for_null_dims() -> None:
    # A NULL series-dim and NULL time-bucket must not vanish or render a
    # blank legend chip — both get a visible "(none)" sentinel so the
    # bucket survives `_coerce_series_points`' empty-label drop.
    dim_specs = [
        {"name": "triggered_at", "is_time_bucket": True},
        {"name": "severity", "is_time_bucket": False, "is_fk": False},
    ]
    buckets = [
        {"triggered_at": None, "triggered_at_label": "", "severity": None, "count": 3},
    ]
    series = _pivot_to_series(buckets, dim_specs, "count")
    assert series[0]["name"] == "(none)"
    assert series[0]["points"] == [{"label": "(none)", "value": 3.0}]


def test_pivot_to_series_needs_two_dims() -> None:
    dim_specs = [{"name": "triggered_at", "is_time_bucket": True}]
    buckets = [{"triggered_at": "2026-06-01", "triggered_at_label": "W23", "count": 5}]
    assert _pivot_to_series(buckets, dim_specs, "count") == []


def test_overlays_to_series_emits_base_plus_one_per_overlay() -> None:
    base = [{"label": "Mon", "value": 3}, {"label": "Tue", "value": 5}]
    overlays = [
        {
            "label": "Resolved",
            "buckets": [{"label": "Mon", "value": 1}, {"label": "Tue", "value": 4}],
        },
    ]
    series = _overlays_to_series("Opened", base, overlays)
    assert [s["name"] for s in series] == ["Opened", "Resolved"]
    assert series[0]["points"] == base
    assert series[1]["points"] == overlays[0]["buckets"]


def test_overlays_to_series_empty_overlays_returns_empty() -> None:
    base = [{"label": "Mon", "value": 3}]
    assert _overlays_to_series("Opened", base, []) == []
