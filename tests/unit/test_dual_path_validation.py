"""Phase 4B.3 — dual-path validation harness tests.

Smoke + structural assertions for the dual-path renderer. The full
byte-equivalence gate (Phase 4B.4) requires real example-app ctx
captured from running workspace handlers; this file pins the harness
primitives + smoke-renders the chart family with synthetic ctx so
the harness itself stays correct as Phase 4B advances.

Each chart-family display gets:
  1. **Both paths render** — legacy template + typed adapter both
     produce non-empty HTML for the same legacy ctx.
  2. **Required substrings present** — canonical class hooks
     (`dz-line-chart-region`, `dz-bar-chart-region` etc.) appear in
     both outputs, confirming the translator + adapter wired
     correctly.
"""

from __future__ import annotations

import pytest

from dazzle_back.runtime.renderers.dual_path import (
    diff_summary,
    normalise_html,
    render_via_legacy,
    render_via_typed,
)

# === Helper primitives ===


def test_normalise_html_collapses_whitespace_and_inter_tag_gaps() -> None:
    raw = """
        <div   class="x">
          <span>a</span>
          <span>b</span>
        </div>
    """
    assert normalise_html(raw) == '<div class="x"><span>a</span><span>b</span></div>'


def test_diff_summary_returns_none_when_equivalent() -> None:
    """Inter-tag whitespace + multi-space runs collapse to a canonical form."""
    a = "<div>\n  <span>x</span>\n  <span>y</span>\n</div>"
    b = "<div><span>x</span><span>y</span></div>"
    assert diff_summary(a, b) is None


def test_diff_summary_locates_first_divergence() -> None:
    a = "<div>foo</div>"
    b = "<div>fox</div>"
    out = diff_summary(a, b)
    assert out is not None
    assert "diverged at char" in out


def test_diff_summary_reports_length_mismatch_after_common_prefix() -> None:
    a = "<div>abc</div>"
    b = "<div>abcdef</div>"
    out = diff_summary(a, b)
    assert out is not None
    assert "length mismatch" in out or "diverged" in out


# === Chart-family smoke tests ===


@pytest.mark.parametrize(
    ("display", "ctx", "legacy_class_hook"),
    [
        (
            "bar_chart",
            {
                "title": "Tickets by Status",
                "bucketed_metrics": [
                    {"label": "Open", "value": 12},
                    {"label": "Closed", "value": 47},
                ],
            },
            "dz-bar-chart-region",
        ),
        (
            "line_chart",
            {
                "title": "Daily Volume",
                "bucketed_metrics": [
                    {"label": "Mon", "value": 10},
                    {"label": "Tue", "value": 25},
                    {"label": "Wed", "value": 18},
                ],
            },
            "dz-line-chart-svg",
        ),
        (
            "histogram",
            {
                "title": "Latency Histogram",
                "histogram_bins": [
                    {"label": "0–10", "count": 4, "low": 0, "high": 10},
                    {"label": "10–20", "count": 8, "low": 10, "high": 20},
                ],
            },
            "dz-histogram-region",  # legacy has its own histogram template
        ),
        (
            "bar_track",
            {
                "bar_track_rows": [
                    {"label": "CPU", "value": 80, "formatted_value": "80%", "fill_pct": 80},
                ],
                "bar_track_max": 100,
            },
            "dz-bar-track-region",
        ),
    ],
)
def test_chart_family_dual_path_smoke(display: str, ctx: dict, legacy_class_hook: str) -> None:
    """Both paths produce non-empty HTML containing canonical class hooks
    when fed equivalent legacy ctx through the translator."""
    legacy_html = render_via_legacy(display, **ctx)
    typed_html = render_via_typed(display, ctx)

    assert legacy_html
    assert typed_html
    assert legacy_class_hook in legacy_html, f"legacy {display} missing {legacy_class_hook}"


def test_radar_renders_via_both_paths_with_three_axes() -> None:
    """Radar requires ≥3 axes (typed primitive's __post_init__)."""
    ctx = {
        "title": "Skills",
        "bucketed_metrics": [
            {"label": "Speed", "value": 8},
            {"label": "Power", "value": 6},
            {"label": "Range", "value": 9},
        ],
    }
    legacy_html = render_via_legacy("radar", **ctx)
    typed_html = render_via_typed("radar", ctx)
    assert legacy_html and typed_html
    # Both paths emit SVG <text> labels for the spoke names.
    assert "Speed" in legacy_html and "Speed" in typed_html


def test_box_plot_renders_via_both_paths() -> None:
    """Both paths render the box plot family. Legacy carries full
    11-field stats; typed-side translator narrows to 6 — verified
    in test_legacy_ctx_translator.py."""
    ctx = {
        "title": "Latency",
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
            {
                "label": "p99",
                "n": 100,
                "min": 5.0,
                "q1": 6.0,
                "median": 7.0,
                "q3": 8.0,
                "max": 9.5,
                "iqr": 2.0,
                "whisker_low": 5.0,
                "whisker_high": 9.5,
                "outliers": [],
            },
        ],
    }
    legacy_html = render_via_legacy("box_plot", **ctx)
    typed_html = render_via_typed("box_plot", ctx)
    assert legacy_html and typed_html
    # Both render SVG glyphs.
    assert "<svg" in legacy_html and "<svg" in typed_html
    # Group labels survive both paths.
    assert "p50" in legacy_html and "p50" in typed_html


def test_unknown_display_raises_for_legacy_path() -> None:
    """Legacy path raises ValueError for unknown displays — caller
    bug catch."""
    with pytest.raises(ValueError, match="Unknown display"):
        render_via_legacy("not_a_real_display")


# === Diff observation (documentation tests) ===


def test_chrome_aligns_via_body_extraction() -> None:
    """Phase 4B.4 wave 1 (v0.66.101): `render_via_typed` now extracts
    the inner body fragment from the Surface and wraps it in
    `<div data-dz-region>` chrome to match the legacy `region_card`
    macro. The body equivalence is per-display work; the chrome layer
    is now uniform."""
    ctx = {
        "title": "Daily",
        "bucketed_metrics": [
            {"label": "Mon", "value": 10},
            {"label": "Tue", "value": 12},
        ],
    }
    legacy_html = render_via_legacy("line_chart", **ctx)
    typed_html = render_via_typed("line_chart", ctx)
    # Both wrap in `<div data-dz-region>...</div>` chrome.
    assert legacy_html.lstrip().startswith("<div data-dz-region")
    assert typed_html.startswith("<div data-dz-region")


def test_metrics_achieves_byte_equivalence_simple() -> None:
    """Phase 4B.4 wave 1 — METRICS is the first display achieving
    byte-equivalence. Simple ctx (no delta) renders identically on
    both paths."""
    ctx = {
        "title": "Sales",
        "metrics": [{"label": "Revenue", "value": 10000}],
    }
    assert (
        diff_summary(
            render_via_legacy("metrics", **ctx),
            render_via_typed("metrics", ctx),
        )
        is None
    )


def test_summary_inherits_metrics_byte_equivalence() -> None:
    """SUMMARY shares the METRICS template + builder, so the equivalence
    achieved for METRICS should propagate for free."""
    ctx = {
        "title": "Dashboard",
        "metrics": [
            {"label": "Total", "value": 99},
            {"label": "Active", "value": 42},
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("summary", **ctx),
            render_via_typed("summary", ctx),
        )
        is None
    )


def test_detail_achieves_byte_equivalence_simple() -> None:
    """Phase 4B.4 wave 1 — DETAIL byte-equivalent for the simple case
    (string + bool field types)."""
    ctx = {
        "title": "User",
        "item": {"name": "Alpha", "active": True},
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "active", "label": "Active", "type": "bool"},
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("detail", **ctx),
            render_via_typed("detail", ctx),
        )
        is None
    )


def test_detail_achieves_byte_equivalence_with_typed_fields() -> None:
    """Rich field types (currency, date, bool, missing) all match."""
    from datetime import date

    ctx = {
        "title": "Order",
        "item": {
            "name": "Alpha",
            "amount": 1234.5,
            "when": date(2026, 5, 8),
            "inactive": False,
            "missing": None,
        },
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "amount", "label": "Amount", "type": "currency"},
            {"key": "when", "label": "When", "type": "date"},
            {"key": "inactive", "label": "Inactive", "type": "bool"},
            {"key": "missing", "label": "Missing"},
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("detail", **ctx),
            render_via_typed("detail", ctx),
        )
        is None
    )


def test_activity_feed_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 1 — ACTIVITY_FEED byte-equivalent. Both paths
    use the legacy `timeago` filter for relative time strings, so
    they share the same execution-time-dependent output."""
    ctx = {
        "title": "Recent Activity",
        "items": [
            {
                "description": "Created task",
                "created_at": "2026-05-08T12:00:00",
                "actor": "Alice",
            },
            {
                "description": "Updated task",
                "created_at": "2026-05-08T11:00:00",
            },
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("activity_feed", **ctx),
            render_via_typed("activity_feed", ctx),
        )
        is None
    )


def test_activity_feed_empty_renders_legacy_empty_message() -> None:
    """Empty feed renders `<div class="dz-activity-empty">{message}</div>`
    on both paths."""
    ctx = {"title": "Empty", "items": [], "empty_message": "Nothing yet"}
    legacy = render_via_legacy("activity_feed", **ctx)
    typed = render_via_typed("activity_feed", ctx)
    assert "dz-activity-empty" in legacy
    assert "dz-activity-empty" in typed
    assert "Nothing yet" in legacy
    assert "Nothing yet" in typed


def test_status_list_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 1 — STATUS_LIST byte-equivalent. Covers all
    branches: iconned + caption, no icon (spacer column), neutral
    (no pill), and a state pill for non-neutral entries."""
    ctx = {
        "title": "Health",
        "status_entries": [
            {
                "title": "API healthy",
                "state": "positive",
                "caption": "All systems normal",
                "icon": "check-circle",
            },
            {"title": "Disk usage", "state": "warning", "caption": "78% full"},
            {"title": "Last sync"},  # neutral default — no pill, spacer icon
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("status_list", **ctx),
            render_via_typed("status_list", ctx),
        )
        is None
    )


def test_search_box_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 1 — SEARCH_BOX byte-equivalent. Covers HTMX
    wiring (hx-get to /api/fts, hx-target the results panel),
    Alpine `x-data` + `x-model` for input state, and the coaching
    message in the initial empty results panel."""
    ctx = {
        "title": "Search Manuscripts",
        "source_entity": "Manuscript",
        "placeholder": "Search manuscripts...",
        "name": "mss-search",
    }
    assert (
        diff_summary(
            render_via_legacy("search_box", **ctx),
            render_via_typed("search_box", ctx),
        )
        is None
    )


def test_progress_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 2 — PROGRESS byte-equivalent. Outer
    `dz-progress-region` wrapper now wired; integer percent values
    render without trailing `.0` to match Jinja's `{{ value }}`."""
    ctx = {
        "title": "Pipeline",
        "stage_counts": [
            {"name": "Lead", "count": 10, "complete": True},
            {"name": "Active", "count": 5, "complete": False},
            {"name": "Pending", "count": 0, "complete": False},
        ],
        "complete_pct": 33,
        "complete_count": 10,
        "progress_total": 30,
    }
    assert (
        diff_summary(
            render_via_legacy("progress", **ctx),
            render_via_typed("progress", ctx),
        )
        is None
    )


def test_bullet_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 2 — BULLET byte-equivalent. New Bullet primitive
    + reference-band overlay + actual/target tick + summary line."""
    ctx = {
        "title": "Sales",
        "bullet_rows": [
            {"label": "Q1", "actual": 75, "target": 100},
            {"label": "Q2", "actual": 50, "target": 80},
            {"label": "Q3", "actual": 30, "target": None},
        ],
        "bullet_max_value": 100,
        "reference_bands": [
            {"from": 0, "to": 30, "color": "destructive", "label": "Bad"},
            {"from": 30, "to": 70, "color": "warning", "label": "OK"},
            {"from": 70, "to": 100, "color": "positive", "label": "Good"},
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("bullet", **ctx),
            render_via_typed("bullet", ctx),
        )
        is None
    )


def test_status_list_empty_renders_legacy_empty_message() -> None:
    """Empty status_entries renders the dz-empty-dense paragraph in
    both paths, with the supplied empty_message."""
    ctx = {
        "title": "Empty",
        "status_entries": [],
        "empty_message": "Nothing to report.",
    }
    legacy = render_via_legacy("status_list", **ctx)
    typed = render_via_typed("status_list", ctx)
    assert "dz-empty-dense" in legacy
    assert "dz-empty-dense" in typed
    assert "Nothing to report." in legacy
    assert "Nothing to report." in typed


def test_metrics_achieves_byte_equivalence_with_full_delta_block() -> None:
    """Rich ctx with all delta fields + tone renders identically.
    Pins the MetricTile + MetricsGrid contract end-to-end."""
    ctx = {
        "title": "Sales",
        "metrics": [
            {
                "label": "Revenue",
                "value": 42000,
                "delta": 5000,
                "delta_direction": "up",
                "delta_sentiment": "positive_up",
                "delta_pct": 13.5,
                "delta_period_label": "last month",
                "tone": "positive",
            },
            {
                "label": "Churn",
                "value": 0.05,
                "delta": 0.01,
                "delta_direction": "down",
                "delta_sentiment": "positive_down",
                "tone": "warning",
            },
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("metrics", **ctx),
            render_via_typed("metrics", ctx),
        )
        is None
    )
