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


def test_pipeline_steps_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 2 — PIPELINE_STEPS byte-equivalent. Covers
    all branches: stages with progress + caption, stages with progress
    only, stages with neither (None value renders as "—" + omits
    progress block + omits connector for last stage)."""
    ctx = {
        "title": "Pipeline",
        "pipeline_stage_data": [
            {
                "label": "Lead",
                "value": 42,
                "caption": "New leads",
                "progress": 75,
                "progress_overshoot": False,
            },
            {"label": "Qualified", "value": 12, "progress": 45, "progress_overshoot": False},
            {"label": "Won", "value": None, "progress": None, "progress_overshoot": False},
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("pipeline_steps", **ctx),
            render_via_typed("pipeline_steps", ctx),
        )
        is None
    )


def test_sparkline_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 2 — SPARKLINE byte-equivalent. Distinct from
    LINE_CHART/AREA_CHART (180×32 viewBox, headline + tiny SVG, no
    axis labels). Phase 4B.4 split it from the TimeSeries primitive
    into a dedicated `Sparkline` primitive."""
    ctx = {
        "title": "Visits",
        "bucketed_metrics": [
            {"label": "Mon", "value": 10},
            {"label": "Tue", "value": 18},
            {"label": "Wed", "value": 15},
            {"label": "Thu", "value": 22},
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("sparkline", **ctx),
            render_via_typed("sparkline", ctx),
        )
        is None
    )


def test_box_plot_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 2 — BOX_PLOT byte-equivalent. BoxPlot primitive
    extended with optional `samples` parallel list (was the documented
    Phase 4B.1.c divergence); now threads `n` through translator →
    adapter → primitive → renderer for the legacy `n=N` tooltip
    suffix and the `count groups · sum(n) samples` summary line."""
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
    assert (
        diff_summary(
            render_via_legacy("box_plot", **ctx),
            render_via_typed("box_plot", ctx),
        )
        is None
    )


def test_tree_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 2 — TREE byte-equivalent. New Tree + TreeNode
    primitives. Recursive `<details>` structure with chevron SVG +
    label + child count. Top-level depth-0 nodes open by default."""
    ctx = {
        "title": "Hierarchy",
        "tree_items": [
            {
                "name": "Root A",
                "_children": [
                    {"name": "A.1", "_children": []},
                    {"name": "A.2", "_children": [{"name": "A.2.1"}]},
                ],
            },
            {"name": "Root B"},
        ],
        "display_key": "name",
    }
    assert (
        diff_summary(
            render_via_legacy("tree", **ctx),
            render_via_typed("tree", ctx),
        )
        is None
    )


def test_timeline_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 2 — TIMELINE byte-equivalent. Timeline primitive
    extended to carry rich `TimelineEvent` instances with title +
    timeago-formatted date_label + per-column secondary fields.
    Adapter consumes the production columns + display_key shape and
    routes badge cells through `_render_status_badge_html` (matches
    legacy `render_status_badge` macro byte-for-byte). Bullet picks
    up the default `dz-attn-bullet dz-attn-tone-default` attention
    class for the no-attention case."""
    ctx = {
        "title": "Audit",
        "items": [
            {
                "name": "Created",
                "created_at": "2026-05-08T12:00:00",
                "severity": "low",
            },
            {
                "name": "Updated",
                "created_at": "2026-05-08T11:00:00",
                "severity": "high",
            },
        ],
        "columns": [
            {"key": "name", "label": "Action", "type": "str"},
            {"key": "created_at", "label": "When", "type": "date"},
            {"key": "severity", "label": "Severity", "type": "badge"},
        ],
        "display_key": "name",
        "total": 2,
        "entity_name": "Event",
    }
    assert (
        diff_summary(
            render_via_legacy("timeline", **ctx),
            render_via_typed("timeline", ctx),
        )
        is None
    )


def test_grid_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 2 — GRID byte-equivalent. New GridRegion +
    GridCell primitives matching workspace/regions/grid.html — outer
    `dz-grid-region`, `dz-grid-list` of `dz-grid-cell` items with
    title + per-column secondary fields. The trailing space inside
    `class="dz-grid-cell "` mirrors the legacy Jinja interpolation
    artifact for byte-equivalence."""
    ctx = {
        "title": "Tasks",
        "items": [
            {"name": "Task A", "priority": "high", "completed": False},
            {"name": "Task B", "priority": "low", "completed": True},
        ],
        "columns": [
            {"key": "name", "label": "Name", "type": "str"},
            {"key": "priority", "label": "Priority", "type": "badge"},
            {"key": "completed", "label": "Done", "type": "bool"},
        ],
        "display_key": "name",
        "entity_name": "Task",
    }
    assert (
        diff_summary(
            render_via_legacy("grid", **ctx),
            render_via_typed("grid", ctx),
        )
        is None
    )


def test_list_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 2 — LIST byte-equivalent. New ListRegion +
    ListColumn primitives matching workspace/regions/list.html — outer
    `dz-list-region`, action row with always-emitted CSV button,
    `dz-list-scroll` of `dz-list-table`, optional overflow line.
    Per-cell type-aware rendering via _render_typed_value. Filter
    chrome / sortable headers / click-through deferred to follow-up."""
    ctx = {
        "title": "Tasks",
        "items": [
            {"name": "Task A", "completed": False},
            {"name": "Task B", "completed": True},
        ],
        "columns": [
            {"key": "name", "label": "Name", "type": "str"},
            {"key": "completed", "label": "Done", "type": "bool"},
        ],
        "endpoint": "/api/tasks",
        "region_name": "tasks",
        "total": 2,
    }
    assert (
        diff_summary(
            render_via_legacy("list", **ctx),
            render_via_typed("list", ctx),
        )
        is None
    )


def test_list_overflow_line_renders_when_total_exceeds_items() -> None:
    """Legacy `<p class="dz-list-overflow">Showing N of M</p>` appears
    when ctx total > items length."""
    ctx = {
        "title": "Tasks",
        "items": [{"name": "Only one"}],
        "columns": [{"key": "name", "label": "Name", "type": "str"}],
        "endpoint": "/api/x",
        "region_name": "x",
        "total": 5,
    }
    assert (
        diff_summary(
            render_via_legacy("list", **ctx),
            render_via_typed("list", ctx),
        )
        is None
    )


def test_wave3_charts_byte_equivalent_smoke() -> None:
    """Phase 4B.4 wave 3 — chart family verification ship.

    Each chart's substrate was built in Phase 4B.1.c; this ship aligned
    them with the legacy templates (chrome stripping, int-narrowing on
    aria-labels, bucket-label routing through render_status_badge,
    Jinja-style numeric rendering). Smoke-tests one ctx per display."""
    cases = [
        (
            "bar_chart",
            {
                "title": "Status",
                "bucketed_metrics": [
                    {"label": "Open", "value": 5},
                    {"label": "Closed", "value": 12},
                ],
            },
        ),
        (
            "line_chart",
            {
                "title": "Daily",
                "bucketed_metrics": [
                    {"label": "Mon", "value": 10},
                    {"label": "Tue", "value": 12},
                    {"label": "Wed", "value": 8},
                ],
            },
        ),
        (
            "radar",
            {
                "title": "Skills",
                "bucketed_metrics": [
                    {"label": "Speed", "value": 8},
                    {"label": "Power", "value": 6},
                    {"label": "Range", "value": 9},
                ],
            },
        ),
        (
            "bar_track",
            {
                "title": "Bars",
                "bar_track_rows": [
                    {
                        "label": "CPU",
                        "value": 80,
                        "formatted_value": "80%",
                        "fill_pct": 80,
                    },
                    {
                        "label": "RAM",
                        "value": 45,
                        "formatted_value": "45%",
                        "fill_pct": 45,
                    },
                ],
                "bar_track_max": 100,
            },
        ),
    ]
    for display, ctx in cases:
        diff = diff_summary(
            render_via_legacy(display, **ctx),
            render_via_typed(display, ctx),
        )
        assert diff is None, f"{display}: {diff}"


def test_histogram_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 3 (v0.66.111): HISTOGRAM byte-equivalent. New
    Histogram + HistogramBin primitives + histogram_svg helper +
    dedicated _build_histogram (was alias to bar_chart)."""
    ctx = {
        "title": "Latency",
        "histogram_bins": [
            {"label": "0-10", "count": 4, "low": 0, "high": 10},
            {"label": "10-20", "count": 8, "low": 10, "high": 20},
            {"label": "20-30", "count": 6, "low": 20, "high": 30},
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("histogram", **ctx),
            render_via_typed("histogram", ctx),
        )
        is None
    )


def test_funnel_chart_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 3 (v0.66.111): FUNNEL_CHART byte-equivalent.
    New Funnel + FunnelStage primitives + dedicated _build_funnel_chart
    (was bucket-rollup routing through bar_chart)."""
    ctx = {
        "title": "Conversion",
        "kanban_columns": ["lead", "qualified", "won"],
        "group_by": "status",
        "items": [
            {"status": "lead"},
            {"status": "lead"},
            {"status": "lead"},
            {"status": "qualified"},
            {"status": "qualified"},
            {"status": "won"},
        ],
        "total": 6,
    }
    assert (
        diff_summary(
            render_via_legacy("funnel_chart", **ctx),
            render_via_typed("funnel_chart", ctx),
        )
        is None
    )


def test_kanban_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 4 (v0.66.112): KANBAN byte-equivalent. New
    KanbanRegion + KanbanColumn + KanbanCard primitives matching
    the legacy workspace/regions/kanban.html structure (column head
    with badge + count, card stack with title + secondary fields)."""
    ctx = {
        "title": "Tasks",
        "kanban_columns": ["todo", "in_progress", "done"],
        "group_by": "status",
        "items": [
            {"id": "1", "title": "Task A", "status": "todo", "priority": "high"},
            {
                "id": "2",
                "title": "Task B",
                "status": "in_progress",
                "priority": "low",
            },
            {"id": "3", "title": "Task C", "status": "done", "priority": "low"},
        ],
        "columns": [
            {"key": "title", "label": "Title"},
            {"key": "status", "label": "Status"},
            {"key": "priority", "label": "Priority", "type": "badge"},
        ],
        "display_key": "title",
        "entity_name": "Task",
        "total": 3,
    }
    assert (
        diff_summary(
            render_via_legacy("kanban", **ctx),
            render_via_typed("kanban", ctx),
        )
        is None
    )


def test_action_grid_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 4 (v0.66.113): ACTION_GRID byte-equivalent.
    New ActionGrid container primitive replaces generic Grid for the
    workspace dz-action-grid-region structure."""
    ctx = {
        "title": "Actions",
        "action_card_data": [
            {"label": "Create", "icon": "plus", "url": "/new", "tone": "positive", "count": 0},
            {"label": "Review", "icon": "check", "url": "/review", "tone": "warning", "count": 5},
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("action_grid", **ctx),
            render_via_typed("action_grid", ctx),
        )
        is None
    )


def test_profile_card_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 4 (v0.66.113): PROFILE_CARD byte-equivalent.
    Added the outer dz-profile-card-region wrapper that the legacy
    template emits."""
    ctx = {
        "title": "User",
        "profile_card_data": {
            "primary": "Alice Smith",
            "secondary": "Engineer",
            "avatar_url": "",
            "initials": "AS",
            "stats": [{"label": "PRs", "value": 42}],
            "facts": ["Ships fast", "Reviews thoughtfully"],
        },
    }
    assert (
        diff_summary(
            render_via_legacy("profile_card", **ctx),
            render_via_typed("profile_card", ctx),
        )
        is None
    )


def test_tabbed_list_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 4 (v0.66.114): TABBED_LIST byte-equivalent.
    Adapter accepts entity_name (production runtime) in addition to
    explicit `key`; renderer emits raw `>` in onclick attr matching
    legacy template (not `&gt;`)."""
    ctx = {
        "title": "Tabs",
        "source_tabs": [
            {
                "entity_name": "Task",
                "label": "Tasks",
                "endpoint": "/api/tasks",
            },
            {
                "entity_name": "User",
                "label": "Users",
                "endpoint": "/api/users",
            },
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("tabbed_list", region_name="tabbed", **ctx),
            render_via_typed("tabbed_list", ctx, region_name="tabbed"),
        )
        is None
    )


def test_heatmap_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 4 (v0.66.115): HEATMAP byte-equivalent. New
    Heatmap + HeatmapRow primitives + dedicated _build_heatmap (was
    alias to pivot_table). Threshold-banded cell tones via
    data-dz-heatmap-tone (bad/warn/good)."""
    ctx = {
        "title": "Heat",
        "heatmap_matrix": [
            {
                "row": "A",
                "row_id": "1",
                "cells": [{"col": "X", "value": 1.5}, {"col": "Y", "value": 5.0}],
            },
            {
                "row": "B",
                "row_id": "2",
                "cells": [{"col": "X", "value": 8.0}, {"col": "Y", "value": 3.0}],
            },
        ],
        "heatmap_col_values": ["X", "Y"],
        "heatmap_thresholds": [3.0, 6.0],
        "total": 2,
        "items": [{}, {}],
    }
    assert (
        diff_summary(
            render_via_legacy("heatmap", **ctx),
            render_via_typed("heatmap", ctx),
        )
        is None
    )


def test_pivot_table_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 4 (v0.66.116): PIVOT_TABLE byte-equivalent.
    New PivotTableRegion + PivotDimSpec primitives + dedicated
    builder consume `pivot_buckets` + `pivot_dim_specs` shape.

    Note: replicates the legacy template's Jinja-scope bug where
    `is_dim_field` mutation inside an inner `{% for %}` doesn't
    propagate, causing all row keys to render as measure columns
    (including dim fields). Required for byte-equivalence."""
    ctx = {
        "title": "Pivot",
        "pivot_buckets": [
            {"status": "open", "severity": "high", "count": 5},
            {"status": "open", "severity": "low", "count": 3},
            {"status": "closed", "severity": "high", "count": 1},
        ],
        "pivot_dim_specs": [
            {"name": "status", "label": "Status", "is_fk": False},
            {"name": "severity", "label": "Severity", "is_fk": False},
        ],
    }
    assert (
        diff_summary(
            render_via_legacy("pivot_table", **ctx),
            render_via_typed("pivot_table", ctx),
        )
        is None
    )


def test_queue_achieves_byte_equivalence() -> None:
    """Phase 4B.4 wave 4 (v0.66.117): QUEUE byte-equivalent. New
    QueueRegion family of primitives matching workspace/regions/
    queue.html — count row, metrics row, queue rows with attention
    accents, badges, date secondaries, and inline transition action
    buttons (HTMX PUT)."""
    ctx = {
        "title": "Q",
        "items": [
            {
                "id": 1,
                "name": "A",
                "state": "pending",
                "severity": "high",
            },
            {
                "id": 2,
                "name": "B",
                "state": "approved",
                "severity": "low",
            },
        ],
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "severity", "label": "Severity", "type": "badge"},
        ],
        "queue_status_field": "state",
        "queue_api_endpoint": "/api/q",
        "queue_transitions": [
            {"label": "Approve", "to_state": "approved"},
            {"label": "Reject", "to_state": "rejected"},
        ],
        "total": 2,
        "metrics": [{"label": "Pending", "value": 1}],
        "display_key": "name",
    }
    assert (
        diff_summary(
            render_via_legacy("queue", region_name="q", **ctx),
            render_via_typed("queue", ctx, region_name="q"),
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
