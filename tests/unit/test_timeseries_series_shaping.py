"""Adapter-layer shaping of multi-series time-series data (#883).

`_overlays_to_series` turns a base bucketed_metrics + overlay_series_data
into a base series plus one series per overlay.
"""

from dazzle.http.runtime.workspace_region_render import (
    _overlays_to_series,
)


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
