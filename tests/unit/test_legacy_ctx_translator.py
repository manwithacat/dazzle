"""Phase 4B.2 — `legacy_ctx_to_adapter_ctx` translator tests.

Pins the per-display ctx-shape mapping. The runtime currently passes
the legacy shape to Jinja templates; the typed-Fragment path will
consume the same legacy ctx via this translator, so byte-equivalent
output across both paths (Phase 4B.3) requires the translator
produces an adapter-shaped ctx that the adapter's `_build_*` methods
already accept.

Each test exercises one display's translator with the legacy ctx
shape extracted from the matching template, asserting the adapter's
expected key set and value coercion.
"""

from __future__ import annotations

from dazzle_back.runtime.renderers.legacy_ctx import legacy_ctx_to_adapter_ctx

# === Chart family ===


def test_bar_chart_translates_bucketed_metrics() -> None:
    legacy = {
        "title": "Tickets by Status",
        "bucketed_metrics": [
            {"label": "Open", "value": 12},
            {"label": "Closed", "value": 47},
        ],
    }
    out = legacy_ctx_to_adapter_ctx("bar_chart", legacy)
    assert out["buckets"] == [("Open", 12), ("Closed", 47)]
    assert out["chart_label"] == "Tickets by Status"


def test_bar_chart_drops_malformed_buckets() -> None:
    """Entries without a label, or with non-coercible values, drop silently."""
    legacy = {
        "bucketed_metrics": [
            {"label": "OK", "value": 5},
            {"label": "", "value": 10},  # empty label
            {"label": "NaN", "value": "not-a-number"},
            "not-a-dict",
        ],
    }
    out = legacy_ctx_to_adapter_ctx("bar_chart", legacy)
    assert out["buckets"] == [("OK", 5)]


def test_funnel_chart_counts_items_per_stage_in_order() -> None:
    legacy = {
        "kanban_columns": ["lead", "qualified", "won"],
        "group_by": "status",
        "items": [
            {"status": "lead"},
            {"status": "lead"},
            {"status": "qualified"},
            {"status": "won"},
            {"status": "ignored"},  # outside the kanban_columns set — drops
        ],
    }
    out = legacy_ctx_to_adapter_ctx("funnel_chart", legacy)
    # Order matches kanban_columns; counts are per-stage.
    assert out["buckets"] == [("lead", 2), ("qualified", 1), ("won", 1)]


def test_histogram_translates_histogram_bins_to_buckets() -> None:
    legacy = {
        "histogram_bins": [
            {"label": "0–10", "count": 4, "low": 0, "high": 10},
            {"label": "10–20", "count": 8, "low": 10, "high": 20},
        ],
    }
    out = legacy_ctx_to_adapter_ctx("histogram", legacy)
    assert out["buckets"] == [("0–10", 4), ("10–20", 8)]


def test_line_chart_translates_bucketed_metrics_to_points() -> None:
    legacy = {
        "title": "Daily Volume",
        "bucketed_metrics": [
            {"label": "Mon", "value": 10},
            {"label": "Tue", "value": 25},
        ],
        "reference_lines": [{"value": 20, "label": "Target", "style": "dashed"}],
    }
    out = legacy_ctx_to_adapter_ctx("line_chart", legacy)
    assert out["points"] == [("Mon", 10.0), ("Tue", 25.0)]
    assert out["chart_label"] == "Daily Volume"
    assert out["reference_lines"] == legacy["reference_lines"]


def test_area_chart_and_sparkline_share_line_chart_translator() -> None:
    """All three time-series displays share `_translate_line_chart`."""
    legacy = {"bucketed_metrics": [{"label": "Q1", "value": 100}]}
    for display in ("line_chart", "area_chart", "sparkline"):
        out = legacy_ctx_to_adapter_ctx(display, legacy)
        assert out["points"] == [("Q1", 100.0)]


def test_radar_translates_bucketed_metrics_to_axes() -> None:
    legacy = {
        "bucketed_metrics": [
            {"label": "Speed", "value": 8},
            {"label": "Power", "value": 6},
            {"label": "Range", "value": 9},
        ],
    }
    out = legacy_ctx_to_adapter_ctx("radar", legacy)
    assert out["axes"] == [("Speed", 8.0), ("Power", 6.0), ("Range", 9.0)]


def test_box_plot_translates_box_plot_stats_to_groups() -> None:
    """The 6-field subset (label, min, q1, median, q3, max) carries
    forward; n/iqr/whisker_low/whisker_high/outliers drop."""
    legacy = {
        "box_plot_stats": [
            {
                "label": "p50",
                "n": 100,
                "min": 0.5,
                "q1": 1.0,
                "median": 2.0,
                "q3": 3.0,
                "max": 4.5,
                "iqr": 2.0,
                "whisker_low": 0.5,
                "whisker_high": 4.5,
                "outliers": [],
            },
        ],
    }
    out = legacy_ctx_to_adapter_ctx("box_plot", legacy)
    assert len(out["groups"]) == 1
    g = out["groups"][0]
    assert g["label"] == "p50"
    assert g["min"] == 0.5 and g["q1"] == 1.0 and g["median"] == 2.0
    assert g["q3"] == 3.0 and g["max"] == 4.5
    # Extended fields not exposed.
    assert "n" not in g and "outliers" not in g


def test_bar_track_passthrough_preserves_pre_computed_rows() -> None:
    """Adapter consumes the legacy shape directly — translator is identity-shaped."""
    rows = [
        {"label": "CPU", "value": 80, "formatted_value": "80%", "fill_pct": 80},
        {"label": "RAM", "value": 45, "formatted_value": "45%", "fill_pct": 45},
    ]
    legacy = {"bar_track_rows": rows, "bar_track_max": 100}
    out = legacy_ctx_to_adapter_ctx("bar_track", legacy)
    assert out["bar_track_rows"] == rows
    assert out["bar_track_max"] == 100


# === Detail / metric ===


def test_metrics_passes_through_full_legacy_field_set() -> None:
    """Phase 4B.4 wave 1 (v0.66.101): the metrics translator widened
    from a 4-field KPI shape to passthrough so the adapter's
    MetricTile primitive receives the full legacy ctx (delta_direction,
    delta_sentiment, delta_pct, delta_period_label, tone). Earlier
    versions narrowed `delta_direction` → `trend`; the typed-Fragment
    adapter now reads `delta_direction` natively, so no rename."""
    legacy = {
        "metrics": [
            {
                "label": "Revenue",
                "value": "$42k",
                "delta": "+$5k",
                "delta_direction": "up",
                "delta_sentiment": "positive_up",
                "delta_pct": 13.5,
                "delta_period_label": "last month",
                "tone": "positive",
            },
        ],
    }
    out = legacy_ctx_to_adapter_ctx("metrics", legacy)
    tile = out["metrics"][0]
    assert tile["label"] == "Revenue"
    assert tile["value"] == "$42k"
    assert tile["delta"] == "+$5k"
    assert tile["delta_direction"] == "up"
    assert tile["delta_sentiment"] == "positive_up"
    assert tile["delta_pct"] == 13.5
    assert tile["delta_period_label"] == "last month"
    assert tile["tone"] == "positive"


def test_summary_uses_same_translator_as_metrics() -> None:
    legacy = {"metrics": [{"label": "Total", "value": 99}]}
    summary_out = legacy_ctx_to_adapter_ctx("summary", legacy)
    metrics_out = legacy_ctx_to_adapter_ctx("metrics", legacy)
    assert summary_out == metrics_out


def test_detail_renames_columns_to_fields() -> None:
    legacy = {
        "item": {"id": 1, "name": "Alpha"},
        "columns": [
            {"key": "name", "label": "Name", "type": "str"},
        ],
    }
    out = legacy_ctx_to_adapter_ctx("detail", legacy)
    assert out["item"] == legacy["item"]
    assert out["fields"] == legacy["columns"]


def test_activity_feed_picks_activity_shaped_fields() -> None:
    legacy = {
        "items": [{"description": "X", "created_at": "2026-05-08"}],
        "action_url": "/something",  # legacy-only — drops
    }
    out = legacy_ctx_to_adapter_ctx("activity_feed", legacy)
    assert out["items"] == legacy["items"]
    assert out["label_field"] == "description"
    assert out["date_field"] == "created_at"


# === Fallback ===


def test_unknown_display_falls_back_to_passthrough() -> None:
    """Untranslated displays return a copy of the legacy ctx."""
    legacy = {"foo": 1, "bar": [1, 2, 3]}
    out = legacy_ctx_to_adapter_ctx("not_a_real_display", legacy)
    assert out == legacy
    # Returns a copy — mutating output doesn't affect input.
    out["foo"] = 99
    assert legacy["foo"] == 1


def test_translator_does_not_mutate_input() -> None:
    legacy = {
        "bucketed_metrics": [{"label": "X", "value": 1}],
        "title": "T",
    }
    snapshot = {
        "bucketed_metrics": list(legacy["bucketed_metrics"]),
        "title": legacy["title"],
    }
    legacy_ctx_to_adapter_ctx("bar_chart", legacy)
    assert legacy == snapshot


# === Integration smoke test — translator output flows through the adapter ===


def test_translator_output_consumed_by_adapter_for_chart_family() -> None:
    """End-to-end smoke: legacy ctx → translator → adapter → rendered HTML.

    Phase 4B.3's full validation gate compares this against the legacy
    Jinja path; this test just asserts no shape errors on the way
    through for the chart-family translators.
    """
    from dataclasses import dataclass

    from dazzle.render.fragment import FragmentRenderer
    from dazzle_back.runtime.renderers.region_adapter import (
        WorkspaceRegionAdapter,
    )

    @dataclass
    class _Region:
        name: str = "r"
        display: str = "bar_chart"
        empty_message: str = "No data."

    adapter = WorkspaceRegionAdapter()
    renderer = FragmentRenderer()

    cases = [
        ("bar_chart", {"bucketed_metrics": [{"label": "A", "value": 5}]}),
        (
            "line_chart",
            {"bucketed_metrics": [{"label": "Mon", "value": 10}]},
        ),
        (
            "radar",
            {
                "bucketed_metrics": [
                    {"label": "x", "value": 1},
                    {"label": "y", "value": 2},
                    {"label": "z", "value": 3},
                ],
            },
        ),
        ("metrics", {"metrics": [{"label": "Revenue", "value": "$10"}]}),
    ]
    for display, legacy in cases:
        adapter_ctx = legacy_ctx_to_adapter_ctx(display, legacy)
        fragment = adapter.build(_Region(name="r", display=display), adapter_ctx)
        # The adapter returns a Surface; rendering it should not raise.
        html = renderer.render(fragment)
        assert isinstance(html, str)
        assert html  # non-empty
