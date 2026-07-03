"""WorkspaceRegionAdapter tests (Phase 4A)."""

import pytest

from dazzle.render.fragment import Region, Surface
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    """Lightweight WorkspaceRegion stub — we only consult `display`,
    `title`, `name`, and `empty_message`. The real WorkspaceRegion
    has ~20 fields; for unit tests we duck-type."""

    def __init__(
        self,
        name: str,
        display: str = "",
        title: str | None = None,
        empty_message: str | None = None,
    ) -> None:
        self.name = name
        self.title = title
        self.display = display
        self.empty_message = empty_message


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


# ───────────────── Dispatch ────────────────────────


def test_unsupported_display_raises_with_actionable_hint() -> None:
    """`map` is the canonical deferred display — vendor-neutral
    geographic rendering is genuinely hard; see `_DEFERRED_DISPLAYS`
    in coverage.py for the design rationale. The canary stays here
    because we expect `map` to remain unsupported indefinitely."""
    adapter = WorkspaceRegionAdapter()
    with pytest.raises(NotImplementedError, match="map"):
        adapter.build(_FakeRegion("r", display="map"), {})


# ───────────────── Timeline ───────────────────────


def test_timeline_renders_rich_event_shape() -> None:
    """Phase 4B.4 wave 2 (v0.66.108): Timeline now uses rich
    `TimelineEvent` instances with title + date_label (timeago-
    formatted) + secondary fields. Adapter consumes columns +
    display_key (matches production runtime ctx)."""
    from dazzle.render.fragment import Timeline, TimelineEvent

    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"title": "Login", "created_at": "2026-05-08T12:00:00", "actor": "Alice"},
        ],
        "columns": [
            {"key": "title", "label": "Action"},
            {"key": "created_at", "label": "When", "type": "date"},
            {"key": "actor", "label": "Actor"},
        ],
        "display_key": "title",
    }
    fragment = adapter.build(_FakeRegion("activity", display="timeline"), ctx)
    timeline = fragment.body.body
    assert isinstance(timeline, Timeline)
    assert len(timeline.events) == 1
    evt = timeline.events[0]
    assert isinstance(evt, TimelineEvent)
    assert evt.title == "Login"
    # date_label produced via timeago — non-empty (exact value
    # depends on test execution time).
    assert evt.date_label
    # Actor field appears as a secondary field, date column does NOT.
    assert any(label == "Actor" for label, _ in evt.fields)
    assert not any(label == "When" for label, _ in evt.fields)


def test_timeline_overflow_line_renders_when_total_exceeds_items() -> None:
    """Legacy `<p class="dz-timeline-overflow">Showing N of M</p>`
    appears when ctx total > items length."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"title": "X", "created_at": "2026-05-08T12:00:00"},
        ],
        "columns": [
            {"key": "title", "label": "T"},
            {"key": "created_at", "label": "W", "type": "date"},
        ],
        "display_key": "title",
        "total": 5,
    }
    html = _render(adapter.build(_FakeRegion("e", display="timeline"), ctx))
    assert "Showing 1 of 5" in html
    assert "dz-timeline-overflow" in html


def test_empty_display_routes_to_list_path() -> None:
    """Default display (empty string) is the list view."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("task_list", title="Tasks"),
        {"items": [], "columns": []},
    )
    assert isinstance(fragment, Surface)
    region = fragment.body
    assert isinstance(region, Region)
    assert region.kind == "list"


def test_explicit_list_display_routes_to_list_path() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("r", display="list"),
        {"items": [], "columns": []},
    )
    assert isinstance(fragment, Surface)
    assert fragment.body.kind == "list"


# ───────────────── Kanban ─────────────────────────


def test_kanban_with_items_grouped_into_columns() -> None:
    """v0.66.112: KANBAN now uses KanbanRegion (workspace-shape) with
    KanbanColumn instances. Items bucket by `group_by`; declared
    `kanban_columns` set the column order."""
    from dazzle.render.fragment import KanbanRegion

    adapter = WorkspaceRegionAdapter()
    region = _FakeRegion("task_board", display="kanban", title="Task Board")
    ctx = {
        "items": [
            {"id": "1", "title": "Buy milk", "status": "todo"},
            {"id": "2", "title": "Walk dog", "status": "doing"},
            {"id": "3", "title": "Read book", "status": "todo"},
            {"id": "4", "title": "Stretch", "status": "done"},
        ],
        "kanban_columns": ["todo", "doing", "done"],
        "group_by": "status",
        "display_key": "title",
    }
    fragment = adapter.build(region, ctx)
    assert isinstance(fragment, Surface)
    assert isinstance(fragment.body, Region)
    assert fragment.body.kind == "kanban"
    board = fragment.body.body
    assert isinstance(board, KanbanRegion)
    labels = [c.label for c in board.columns]
    assert labels == ["todo", "doing", "done"]
    by_label = {c.label: c for c in board.columns}
    assert len(by_label["todo"].cards) == 2
    assert len(by_label["doing"].cards) == 1
    assert len(by_label["done"].cards) == 1


def test_kanban_unknown_group_keys_drop() -> None:
    """v0.66.112: items grouped under a key not in `kanban_columns` are
    silently dropped (the legacy template uses `selectattr equalto`
    which excludes off-board items rather than synthesising an Other
    column)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"id": "1", "title": "X", "status": "blocked"},  # not in keys
            {"id": "2", "title": "Y", "status": "todo"},
        ],
        "kanban_columns": ["todo", "doing"],
        "group_by": "status",
        "display_key": "title",
    }
    fragment = adapter.build(_FakeRegion("b", display="kanban"), ctx)
    board = fragment.body.body
    by_label = {c.label: c for c in board.columns}
    # "blocked" doesn't appear in kanban_columns → dropped from the board.
    assert set(by_label.keys()) == {"todo", "doing"}
    assert len(by_label["todo"].cards) == 1
    assert len(by_label["doing"].cards) == 0


def test_kanban_empty_columns_still_render() -> None:
    """A column with declared key but zero items still renders as an
    empty column — important UX so authors see all states."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"id": "1", "title": "X", "status": "todo"}],
        "kanban_columns": ["todo", "doing", "done"],
        "group_by": "status",
        "display_key": "title",
    }
    fragment = adapter.build(_FakeRegion("b", display="kanban"), ctx)
    board = fragment.body.body
    by_label = {c.label: c for c in board.columns}
    assert by_label["doing"].cards == ()
    assert by_label["done"].cards == ()


def test_kanban_no_items_renders_empty_state_or_minimal_board() -> None:
    """Edge case: no items AND no group_keys — empty state."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("b", display="kanban", empty_message="No tasks yet."),
        {},
    )
    # Surface body is a Region containing either EmptyState or a
    # placeholder KanbanBoard — both are acceptable; what matters
    # is no crash and meaningful output.
    html = _render(fragment)
    # One of these strings should appear
    assert "No tasks yet." in html or "All" in html or "dz-kanban" in html


# ───────────────── End-to-end render ──────────────


def test_list_renders_with_table() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"name": "Alice"}, {"name": "Bob"}],
        "columns": [{"key": "name", "label": "Name"}],
    }
    fragment = adapter.build(_FakeRegion("users", display="list"), ctx)
    html = _render(fragment)
    assert "<table" in html
    assert "Alice" in html
    assert "Bob" in html


def test_list_with_filter_columns_renders_filter_bar() -> None:
    """Phase 4B.1.e: when ctx supplies `endpoint` + `filter_columns`,
    the adapter composes a FilterBar above the table."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"name": "X"}],
        "columns": [{"key": "name", "label": "Name"}],
        "endpoint": "/api/regions/r",
        "region_name": "r",
        "filter_columns": [
            {
                "key": "status",
                "label": "Status",
                "options": [("open", "Open"), ("closed", "Closed")],
            },
        ],
        "active_filters": {"status": "open"},
    }
    html = _render(adapter.build(_FakeRegion("r", display="list"), ctx))
    assert "filter-bar" in html
    assert 'name="filter_status"' in html
    assert 'value="open" selected>' in html
    assert "<table" in html


def test_list_with_date_range_renders_picker() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [],
        "endpoint": "/api/x",
        "region_name": "r",
        "date_range": True,
        "date_from": "2026-01-01",
        "date_to": "2026-12-31",
    }
    html = _render(adapter.build(_FakeRegion("r", display="list"), ctx))
    assert "date-range-bar" in html
    assert 'value="2026-01-01"' in html
    assert 'value="2026-12-31"' in html


def test_list_with_csv_export_renders_button() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"name": "X"}],
        "columns": [{"key": "name", "label": "Name"}],
        "endpoint": "/api/x",
        "region_name": "tickets",
        "csv_export": True,
    }
    html = _render(adapter.build(_FakeRegion("r", display="list"), ctx))
    assert "dz-list-csv-button" in html
    assert 'data-dz-csv-filename="tickets.csv"' in html  # default = region_name + ".csv"


def test_list_csv_export_filename_override() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [],
        "endpoint": "/api/x",
        "region_name": "r",
        "csv_export": True,
        "csv_filename": "custom-export.csv",
    }
    html = _render(adapter.build(_FakeRegion("r", display="list"), ctx))
    assert 'data-dz-csv-filename="custom-export.csv"' in html


def test_list_without_endpoint_skips_filter_chrome() -> None:
    """Without `endpoint` ctx key, FilterBar / DateRangePicker chrome
    rendering is skipped — they all need an endpoint URL for HTMX
    wiring. v0.66.109: The CSV button is now always emitted (legacy
    behaviour) inside the dz-list-region wrapper, so we no longer
    assert its absence."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"name": "X"}],
        "columns": [{"key": "name", "label": "Name"}],
        "filter_columns": [{"key": "k", "label": "K", "options": []}],
        "csv_export": True,
        "date_range": True,
    }
    html = _render(adapter.build(_FakeRegion("r", display="list"), ctx))
    assert "filter-bar" not in html
    assert "date-range-bar" not in html
    assert "<table" in html  # body still renders
    # CSV button is always emitted (legacy behaviour); check that the
    # endpoint attr is empty when no endpoint was supplied.
    assert "dz-list-csv-button" in html
    assert 'data-dz-csv-endpoint=""' in html


def test_list_drops_malformed_filter_columns() -> None:
    """Filter columns missing key, non-dict entries, and duplicates
    silently drop rather than crashing FilterBar's strict invariants."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [],
        "endpoint": "/api/x",
        "region_name": "r",
        "filter_columns": [
            None,
            42,
            {"label": "no key"},
            {"key": "valid", "label": "Valid", "options": []},
            {"key": "valid", "label": "Dup"},  # duplicate
        ],
    }
    html = _render(adapter.build(_FakeRegion("r", display="list"), ctx))
    assert "filter-bar" in html
    assert ">All Valid<" in html
    assert "Dup" not in html


# ───────────────── Grid ────────────────────────────


def test_grid_renders_cards_in_columns() -> None:
    """Grid display materialises one Card per item, in N columns."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"title": "Alpha"}, {"title": "Beta"}, {"title": "Gamma"}],
        "columns": 2,
    }
    fragment = adapter.build(_FakeRegion("cards", display="grid", title="Cards"), ctx)
    html = _render(fragment)
    assert "Alpha" in html and "Beta" in html and "Gamma" in html
    assert "Cards" in html


def test_grid_uses_label_field_override() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"label": "Custom", "title": "Ignored"}],
        "label_field": "label",
    }
    fragment = adapter.build(_FakeRegion("c", display="grid"), ctx)
    html = _render(fragment)
    assert "Custom" in html
    assert "Ignored" not in html


def test_grid_clamps_column_count_to_valid_range() -> None:
    """columns=0 → 1; columns=999 → 12 (Grid primitive constraints)."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("c", display="grid"),
        {"items": [{"title": "x"}], "columns": 999},
    )
    # Smoke: render doesn't blow up on the clamp
    assert "x" in _render(fragment)


# ───────────────── Metrics ─────────────────────────


def test_metrics_renders_kpi_tiles_with_pre_computed_values() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "metrics": [
            {"label": "Open", "value": "42", "trend": "up", "delta": "+5"},
            {"label": "Closed", "value": "18", "trend": "flat"},
        ],
    }
    fragment = adapter.build(_FakeRegion("kpis", display="metrics"), ctx)
    html = _render(fragment)
    assert "Open" in html and "42" in html
    assert "Closed" in html and "18" in html


def test_metrics_falls_back_to_aggregates_dict() -> None:
    """Without a `metrics` list, ctx['aggregates'] (legacy shape)
    is mapped to KPIs label-cased from the dict keys."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("kpis", display="metrics"),
        {"aggregates": {"total_open": 7, "total_closed": 3}},
    )
    html = _render(fragment)
    assert "Total Open" in html
    assert "7" in html


def test_metrics_scope_denied_aggregates_render_empty_state_not_raw_ir() -> None:
    """#1425: on scope-denial the orchestrator leaves `metrics` empty but
    ctx['aggregates'] still holds the *raw* IR (AggregateRef /
    DerivedMetricExpr). The fallback must drop unresolved IR rather than
    stringify its Pydantic repr (which leaks the where-clause of an entity
    the user can't read) — it should render the clean empty state."""
    from dazzle.core.ir import AggregateRef, DerivedMetricExpr

    adapter = WorkspaceRegionAdapter()
    raw_agg = {
        "total_secret": AggregateRef(func="count", entity="SecretEntity"),
        "ratio": DerivedMetricExpr(metric_name="ratio"),
    }
    fragment = adapter.build(
        _FakeRegion("kpis", display="metrics", empty_message="No access."),
        {"aggregates": raw_agg},
    )
    html = _render(fragment)
    # The clean empty state renders…
    assert "No access." in html
    # …and none of the raw IR repr leaks into the tile.
    assert "func=" not in html
    assert "entity=" not in html
    assert "SecretEntity" not in html
    assert "metric_name=" not in html


def test_metrics_summary_alias_dispatches_same_path() -> None:
    """`display: summary` reuses the metrics adapter — they're spelt
    differently in DSL but render identically."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("k", display="summary"),
        {"metrics": [{"label": "X", "value": "1"}]},
    )
    assert "X" in _render(fragment)


def test_metrics_invalid_tone_coerced_to_default() -> None:
    """Defensive: garbage tone values shouldn't crash the MetricTile primitive."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("k", display="metrics"),
        {"metrics": [{"label": "X", "value": "1", "tone": "garbage"}]},
    )
    html = _render(fragment)
    assert "X" in html
    assert 'data-dz-tone="garbage"' not in html  # garbage stripped


def test_metrics_extended_deltas_render_full_block() -> None:
    """Phase 4B.1.a: `_build_metrics` now produces MetricTile primitives
    so the legacy delta block (delta_pct, delta_period_label,
    delta_sentiment, delta_direction, sign, arrow) is preserved."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "metrics": [
            {
                "label": "Open Tickets",
                "value": 1234,
                "tone": "warning",
                "delta_direction": "up",
                "delta_sentiment": "positive_down",  # up = bad
                "delta": "42",
                "delta_pct": 12.5,
                "delta_period_label": "last week",
            }
        ]
    }
    html = _render(adapter.build(_FakeRegion("k", display="metrics"), ctx))
    assert 'data-dz-metric-key="open_tickets"' in html
    assert 'data-dz-tone="warning"' in html
    assert 'data-dz-delta-tone="destructive"' in html  # up + positive_down = bad
    assert "1,234" in html  # metric_number applied (thousands separator)
    assert "↑" in html and "+42" in html
    assert "(12.5%)" in html
    assert "vs last week" in html


def test_metrics_delta_sentiment_positive_up_renders_good() -> None:
    """`up` direction + `positive_up` sentiment = good = positive tone."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "metrics": [
            {
                "label": "Revenue",
                "value": 50000,
                "delta_direction": "up",
                "delta_sentiment": "positive_up",
                "delta": "5000",
                "delta_period_label": "last month",
            }
        ]
    }
    html = _render(adapter.build(_FakeRegion("k", display="metrics"), ctx))
    assert 'data-dz-delta-tone="positive"' in html


def test_metrics_no_delta_omits_delta_block() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {"metrics": [{"label": "Total", "value": 42}]}
    html = _render(adapter.build(_FakeRegion("k", display="metrics"), ctx))
    assert "dz-metric-delta" not in html
    assert ">42<" in html  # plain value with no thousands separator


def test_metrics_value_passes_through_metric_number_filter() -> None:
    """Integers get thousands separators; bools become Yes/No;
    None becomes "0"."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "metrics": [
            {"label": "Big", "value": 1500000},
            {"label": "Bool", "value": True},
            {"label": "Null", "value": None},
        ]
    }
    html = _render(adapter.build(_FakeRegion("k", display="metrics"), ctx))
    assert "1,500,000" in html
    assert ">Yes<" in html
    assert ">0<" in html  # None → "0"


def test_metrics_sub_one_float_rounds_to_2dp_no_leak() -> None:
    """#1479: a sub-1.0 float aggregate (e.g. avg(confidence)) rounds to
    2dp instead of leaking full precision (0.8850441412520064)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {"metrics": [{"label": "Avg Confidence", "value": 0.8850441412520064}]}
    html = _render(adapter.build(_FakeRegion("k", display="metrics"), ctx))
    assert "0.89" in html
    assert "0.8850441412520064" not in html


# ───────────────── Bar chart ───────────────────────


def test_bar_chart_renders_buckets() -> None:
    """v0.66.110: bucket labels go through `render_status_badge` macro
    via humanize filter — "low" → "Low", etc."""
    adapter = WorkspaceRegionAdapter()
    ctx = {"buckets": [("low", 3), ("medium", 7), ("high", 2)]}
    fragment = adapter.build(_FakeRegion("severity", display="bar_chart"), ctx)
    html = _render(fragment)
    assert "Low" in html
    assert "Medium" in html
    assert "High" in html


def test_bar_chart_skips_malformed_entries() -> None:
    """A bucket missing a usable key/value silently drops; pure garbage
    leaves an empty bucket list → EmptyState."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("c", display="bar_chart", empty_message="No data."),
        {"buckets": [None, 42, "string"]},
    )
    assert "No data." in _render(fragment)


def test_bar_chart_uses_chart_label_override() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {"buckets": [("a", 1)], "chart_label": "Custom Chart"}
    fragment = adapter.build(_FakeRegion("c", display="bar_chart"), ctx)
    # The label should appear somewhere in the rendered output
    html = _render(fragment)
    assert "a" in html  # smoke; label rendering is BarChart's concern


def test_bar_chart_renders_with_reference_overlays_supplied() -> None:
    """v0.66.110: BAR_CHART chrome stripped — the Phase 4B-only
    `<dl class="dz-bar-chart__references">` annotation block has no
    legacy counterpart and was dropped. Reference overlays are silently
    ignored in the bar chart body (legacy doesn't render them either
    in the bucketed_metrics primary branch)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "buckets": [("low", 3), ("high", 9)],
        "reference_lines": [{"value": 10, "label": "SLA", "style": "dashed"}],
        "reference_bands": [{"from": 0, "to": 5, "label": "Healthy", "color": "positive"}],
    }
    html = _render(adapter.build(_FakeRegion("c", display="bar_chart"), ctx))
    # Bars still render; reference overlays no longer carry to the typed output.
    assert "Low" in html and "High" in html
    assert "dz-bar-chart-region" in html


def test_box_plot_carries_reference_overlays() -> None:
    """v0.66.107: BOX_PLOT chrome stripped to byte-match legacy
    template — the `<dl class="dz-box-plot__references">` block was
    a Phase 4B-only addition with no legacy counterpart, dropped to
    align. Reference lines now overlay inside the SVG (legacy parity)
    rather than rendering as a separate dl/dt/dd block."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "groups": [("p50", 0, 1, 2, 3, 4)],
        "reference_lines": [{"value": 3.5, "label": "Threshold"}],
    }
    html = _render(adapter.build(_FakeRegion("b", display="box_plot"), ctx))
    # Reference line renders inside the SVG as a <line> with <title>.
    assert "<title>Threshold: 3.5</title>" in html


def test_bar_track_carries_reference_overlays() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "bar_track_rows": [{"label": "CPU", "value": 80, "formatted_value": "80%", "fill_pct": 80}],
        "bar_track_max": 100,
        "reference_lines": [{"value": 90, "label": "Critical", "style": "dotted"}],
    }
    html = _render(adapter.build(_FakeRegion("b", display="bar_track"), ctx))
    assert "dz-bar-track__references" in html
    assert 'data-style="dotted"' in html


# ───────────────── Pivot table ─────────────────────


def test_pivot_table_renders_rows_and_columns() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "rows": ["low", "high"],
        "columns": ["open", "closed"],
        "cells": {("low", "open"): 3, ("high", "closed"): 7},
    }
    fragment = adapter.build(_FakeRegion("p", display="pivot_table"), ctx)
    html = _render(fragment)
    assert "low" in html and "high" in html
    assert "open" in html and "closed" in html
    assert "3" in html and "7" in html


def test_pivot_table_drops_cells_with_unknown_dimensions() -> None:
    """Defensive: cells whose row or column isn't declared get
    silently dropped (PivotTable raises if they're passed in)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "rows": ["a"],
        "columns": ["x"],
        "cells": {("a", "x"): 1, ("z", "x"): 99},  # ('z', 'x') is bogus
    }
    fragment = adapter.build(_FakeRegion("p", display="pivot_table"), ctx)
    html = _render(fragment)
    assert "1" in html
    assert "99" not in html


# ───────────────── Tabbed list ─────────────────────


def test_tabbed_list_renders_tabs_with_tables() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "tabs": [
            {
                "key": "open",
                "label": "Open",
                "items": [{"name": "Alpha"}],
                "columns": [{"key": "name", "label": "Name"}],
            },
            {
                "key": "closed",
                "label": "Closed",
                "items": [{"name": "Beta"}],
                "columns": [{"key": "name", "label": "Name"}],
            },
        ]
    }
    fragment = adapter.build(_FakeRegion("t", display="tabbed_list"), ctx)
    html = _render(fragment)
    assert "Alpha" in html
    assert "Beta" in html


def test_tabbed_list_legacy_slices_alias_works() -> None:
    """ctx['slices'] is accepted as alias for ctx['tabs']."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "slices": [
            {
                "key": "k",
                "items": [{"x": "1"}],
                "columns": [{"key": "x", "label": "X"}],
            }
        ]
    }
    fragment = adapter.build(_FakeRegion("t", display="tabbed_list"), ctx)
    assert "1" in _render(fragment)


def test_tabbed_list_dedupes_duplicate_tab_keys() -> None:
    """Tabs primitive raises on duplicate keys; the adapter dedups
    silently (first key wins)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "tabs": [
            {
                "key": "k",
                "items": [{"x": "FirstValue"}],
                "columns": [{"key": "x", "label": "X"}],
            },
            {
                "key": "k",  # duplicate
                "items": [{"x": "SecondValue"}],
                "columns": [{"key": "x", "label": "X"}],
            },
        ]
    }
    fragment = adapter.build(_FakeRegion("t", display="tabbed_list"), ctx)
    html = _render(fragment)
    assert "FirstValue" in html
    assert "SecondValue" not in html


def test_tabbed_list_source_tabs_produces_lazy_tab_panel() -> None:
    """Phase 4B.1.d: when ctx supplies `source_tabs` with HTMX endpoints,
    the adapter builds a LazyTabPanel that lazy-loads each tab via
    hx-get. Matches the legacy `tabbed_list.html` runtime shape."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "region_name": "ticket_tabs",
        "source_tabs": [
            {
                "key": "github",
                "label": "GitHub",
                "endpoint": "/api/workspaces/admin/regions/ticket_tabs/github",
            },
            {
                "key": "slack",
                "label": "Slack",
                "endpoint": "/api/workspaces/admin/regions/ticket_tabs/slack",
            },
        ],
    }
    html = _render(adapter.build(_FakeRegion("t", display="tabbed_list"), ctx))
    assert 'role="tablist"' in html
    assert 'id="tabs-ticket_tabs"' in html
    assert 'data-tab-target="tab-ticket_tabs-github"' in html
    assert 'hx-get="/api/workspaces/admin/regions/ticket_tabs/github"' in html
    # First tab eager (load), second tab lazy (intersect once)
    assert 'hx-trigger="load"' in html
    assert 'hx-trigger="intersect once"' in html


def test_tabbed_list_falls_back_to_eager_tabs_when_no_source_tabs() -> None:
    """Pre-Phase-4B.1.d ctx shape `{tabs: [{key, label, items, columns}]}`
    is still accepted — produces the eager Tabs primitive. The runtime
    will switch to source_tabs ahead of the Phase 4B.2 translator."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "tabs": [
            {
                "key": "a",
                "label": "Alpha",
                "items": [{"name": "Item One"}],
                "columns": [{"key": "name", "label": "Name"}],
            }
        ]
    }
    html = _render(adapter.build(_FakeRegion("t", display="tabbed_list"), ctx))
    assert "dz-tabs" in html
    assert "Item One" in html
    assert 'role="tablist"' not in html  # not the lazy shape


def test_tabbed_list_source_tabs_drops_malformed_entries() -> None:
    """Tabs missing key or endpoint silently drop; duplicate keys
    silently drop too (LazyTabPanel rejects dupes)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "region_name": "r",
        "source_tabs": [
            None,
            {"key": "valid", "label": "Valid", "endpoint": "/api/valid"},
            {"label": "Missing key", "endpoint": "/api/x"},  # no key
            {"key": "missing-endpoint"},  # no endpoint
            {
                "key": "valid",  # duplicate
                "label": "Dup",
                "endpoint": "/api/other",
            },
        ],
    }
    html = _render(adapter.build(_FakeRegion("t", display="tabbed_list"), ctx))
    assert ">Valid<" in html
    assert "Missing key" not in html
    assert "Dup" not in html


def test_tabbed_list_source_tabs_uses_region_name_for_dom_ids() -> None:
    """`region_name` ctx key namespaces the DOM ids; falls back to the
    region's `name` attribute when absent."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "source_tabs": [
            {"key": "x", "label": "X", "endpoint": "/api/x"},
        ]
    }
    # No region_name in ctx; the _FakeRegion's name attribute should be used
    html = _render(adapter.build(_FakeRegion("my_region", display="tabbed_list"), ctx))
    assert "tabs-my_region" in html


def test_tabbed_list_eager_flag_overrides_position_default() -> None:
    """When tab.eager is True, the panel fires hx-trigger=load even if
    it isn't the first tab. Default behaviour: only first is eager."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "region_name": "r",
        "source_tabs": [
            {"key": "a", "label": "A", "endpoint": "/a"},
            {"key": "b", "label": "B", "endpoint": "/b", "eager": True},
            {"key": "c", "label": "C", "endpoint": "/c"},
        ],
    }
    html = _render(adapter.build(_FakeRegion("t", display="tabbed_list"), ctx))
    # Both first and explicit-eager tab fire load
    assert html.count('hx-trigger="load"') >= 2
    assert 'hx-trigger="intersect once"' in html  # third tab


# ───────────────── Detail ─────────────────────────


def test_detail_renders_explicit_field_list_in_declared_order() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "item": {"name": "Alice", "email": "a@b.com", "role": "admin"},
        "fields": [
            {"key": "name", "label": "Name"},
            {"key": "email", "label": "Email"},
            # role omitted — adapter should respect declared list
        ],
    }
    fragment = adapter.build(_FakeRegion("d", display="detail"), ctx)
    html = _render(fragment)
    assert "Name" in html and "Alice" in html
    assert "Email" in html and "a@b.com" in html
    assert "admin" not in html  # role wasn't in fields list


def test_detail_falls_back_to_all_keys_when_no_fields() -> None:
    """Without an explicit fields list, adapter shows every dict key
    in declared order — useful for early-prototype DSL where the
    field list isn't wired yet."""
    adapter = WorkspaceRegionAdapter()
    ctx = {"item": {"name": "Bob", "city": "Paris"}}
    fragment = adapter.build(_FakeRegion("d", display="detail"), ctx)
    html = _render(fragment)
    assert "Bob" in html and "Paris" in html


def test_detail_renders_em_dash_for_missing_values() -> None:
    """Empty / None values render as em-dash placeholder so the layout
    doesn't collapse on missing data."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "item": {"name": "Alice", "phone": None},
        "fields": [{"key": "name"}, {"key": "phone"}],
    }
    fragment = adapter.build(_FakeRegion("d", display="detail"), ctx)
    html = _render(fragment)
    assert "Alice" in html
    assert "—" in html


def test_detail_type_aware_badge_renders_status_tone() -> None:
    """Phase 4B.1.a: `type: badge` columns use the Badge primitive with
    a variant computed from `_badge_tone_filter` (mirrors the legacy
    `render_status_badge` macro behaviour)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "item": {"status": "resolved"},
        "fields": [{"key": "status", "label": "Status", "type": "badge"}],
    }
    fragment = adapter.build(_FakeRegion("d", display="detail"), ctx)
    html = _render(fragment)
    # v0.66.108: badge cells now route through `render_status_badge`-
    # equivalent RawHTML for byte-equivalence with the legacy macro.
    # DETAIL passes `bordered=True`. The class scheme is `dz-badge` +
    # `bordered` + `data-dz-tone="<tone>"`.
    assert 'class="dz-badge  bordered"' in html
    assert 'data-dz-tone="success"' in html  # resolved → success tone
    assert ">Resolved<" in html  # humanize filter title-cases


def test_detail_type_aware_bool_renders_check_or_cross() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "item": {"a": True, "b": False, "c": None},
        "fields": [
            {"key": "a", "type": "bool"},
            {"key": "b", "type": "bool"},
            {"key": "c", "type": "bool"},
        ],
    }
    html = _render(adapter.build(_FakeRegion("d", display="detail"), ctx))
    # v0.66.102: bool now uses the legacy `bool_icon` filter directly
    # (HTML entities + tinted span) for byte-equivalence with the
    # legacy template. Check for the entity codes.
    assert "&#10003;" in html  # ✓ (true)
    assert "&#10005;" in html  # ✗ (false)


def test_detail_type_aware_date_uses_dateformat_filter() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "item": {"created": "2026-05-01T12:00:00"},
        "fields": [{"key": "created", "type": "date"}],
    }
    html = _render(adapter.build(_FakeRegion("d", display="detail"), ctx))
    # _date_filter default format is "%d %b %Y"
    assert "01 May 2026" in html


def test_detail_type_aware_currency_formats_minor_units() -> None:
    """`type: currency` uses _currency_filter with `minor=True` default
    — so 12345 GBP minor → £123.45."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "item": {"price": 12345},
        "fields": [{"key": "price", "type": "currency"}],
    }
    html = _render(adapter.build(_FakeRegion("d", display="detail"), ctx))
    assert "£123.45" in html


def test_detail_type_aware_ref_renders_link_with_display() -> None:
    """`type: ref` columns produce a Link primitive when ref_route is
    set; the link text uses `<key>_display` from the item dict."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "item": {"team_id": 7, "team_id_display": "Engineering"},
        "fields": [{"key": "team_id", "type": "ref", "ref_route": "/teams"}],
    }
    html = _render(adapter.build(_FakeRegion("d", display="detail"), ctx))
    assert 'href="/teams/7"' in html
    assert "Engineering" in html


def test_detail_type_aware_ref_resolves_fk_dict_display_not_uuid() -> None:
    """A FK column that arrives as a dict (id + __display__) renders the
    referenced entity's display name as link text — never the raw dict repr
    or a bare UUID (#1389)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "item": {"contact": {"id": "abc-123", "__display__": "Ada Lovelace"}},
        "fields": [{"key": "contact", "type": "ref", "ref_route": "/contacts/{id}"}],
    }
    html = _render(adapter.build(_FakeRegion("d", display="detail"), ctx))
    assert 'href="/contacts/abc-123"' in html
    assert "Ada Lovelace" in html
    assert "__display__" not in html
    assert "'id'" not in html  # no dict repr leaked as link text


def test_detail_type_aware_ref_without_route_falls_back_to_text() -> None:
    """When `ref_route` is empty, the ref renders as plain Text using
    the display value — no broken link."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "item": {"team_id": 7, "team_id_display": "Engineering"},
        "fields": [{"key": "team_id", "type": "ref"}],
    }
    html = _render(adapter.build(_FakeRegion("d", display="detail"), ctx))
    assert "Engineering" in html
    assert "dz-link" not in html


def test_detail_default_type_renders_em_dash_for_none() -> None:
    """Untyped columns with None values fall back to em-dash (not the
    string 'None')."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "item": {"x": None, "y": "OK"},
        "fields": [{"key": "x"}, {"key": "y"}],
    }
    html = _render(adapter.build(_FakeRegion("d", display="detail"), ctx))
    assert "—" in html
    assert "OK" in html
    assert "None" not in html


# ───────────────── Activity feed ──────────────────


def test_radar_with_fewer_than_three_axes_degrades_to_empty_state() -> None:
    """Adapter is permissive — Radar's __post_init__ raises on <3 axes;
    the adapter returns EmptyState rather than crashing."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("r", display="radar", empty_message="Need 3+ axes."),
        {"axes": [("A", 1), ("B", 2)]},
    )
    assert "Need 3+ axes." in _render(fragment)


def test_box_plot_silently_drops_non_monotonic_groups() -> None:
    """The adapter pre-filters groups whose quartiles aren't monotonic
    rather than crashing the BoxPlot primitive's invariant."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "groups": [
            ("good", 0, 1, 2, 3, 4),
            ("bad", 5, 4, 3, 2, 1),  # reversed
        ]
    }
    fragment = adapter.build(_FakeRegion("b", display="box_plot"), ctx)
    html = _render(fragment)
    assert "good" in html
    assert "bad" not in html


def test_sparkline_renders_dedicated_primitive() -> None:
    """v0.66.106: SPARKLINE split from TimeSeries into a dedicated
    `Sparkline` primitive matching the legacy `dz-sparkline-region`
    structure (180×32 viewBox, headline + tiny SVG)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {"points": [("a", 1), ("b", 2), ("c", 3)]}
    html = _render(adapter.build(_FakeRegion("s", display="sparkline"), ctx))
    assert 'class="dz-sparkline-region"' in html
    assert 'class="dz-sparkline-svg"' in html
    assert 'viewBox="0 0 180 32"' in html


def test_time_series_skips_malformed_points() -> None:
    """Points that can't be coerced silently drop; pure garbage leaves
    an empty point list → EmptyState."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("c", display="line_chart", empty_message="No data."),
        {"points": [None, 42, "string"]},
    )
    assert "No data." in _render(fragment)


def test_time_series_carries_reference_lines() -> None:
    """v0.66.110: ctx['reference_lines'] flows through to the
    TimeSeries primitive and renders as `<line>` overlays inside
    the SVG (legacy parity). Phase 4B-only `<dl>` annotation block
    was dropped to byte-match."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "points": [("Jan", 50), ("Feb", 75)],
        "reference_lines": [
            {"value": 100, "label": "Target", "style": "dashed"},
            {"value": 50, "label": "Min", "style": "wavy"},  # unknown → solid
        ],
    }
    html = _render(adapter.build(_FakeRegion("c", display="line_chart"), ctx))
    # Reference lines render inside the SVG with stroke-dasharray.
    assert 'stroke-dasharray="4,3"' in html  # dashed
    assert "<title>Target: 100" in html
    assert "<title>Min: 50" in html


def test_time_series_carries_reference_bands_with_alt_keys() -> None:
    """v0.66.110: bands render inside the SVG as `<rect>` overlays.
    Adapter accepts both `from`/`to` and `from_value`/`to_value`
    key shapes; bands with from > to silently drop."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "points": [("a", 1), ("b", 2)],
        "reference_bands": [
            {"from": 80, "to": 120, "label": "Healthy", "color": "positive"},
            {"from": 200, "to": 100, "label": "Bad order"},  # drop
            {"from_value": 0, "to_value": 30, "label": "Danger", "color": "destructive"},
        ],
    }
    html = _render(adapter.build(_FakeRegion("c", display="line_chart"), ctx))
    assert "<title>Healthy:" in html
    assert "hsl(145, 55%, 45%)" in html  # positive colour
    assert "<title>Danger:" in html
    assert "hsl(var(--destructive))" in html
    assert "Bad order" not in html


def test_time_series_no_references_omits_block() -> None:
    """When neither reference_lines nor reference_bands are supplied,
    the renderer omits the `<dl class=\"dz-timeseries__references\">`
    wrapper entirely (backward compat with Phase 4A renders)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {"points": [("a", 1)]}
    html = _render(adapter.build(_FakeRegion("c", display="line_chart"), ctx))
    assert "dz-timeseries__references" not in html


def test_diagram_drops_edges_with_unknown_endpoints() -> None:
    """Diagram's __post_init__ rejects edges whose endpoints aren't in
    the node list; the adapter silently drops them rather than crashing."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "nodes": ["A"],
        "edges": [("A", "ZZZ"), ("A", "A")],  # ZZZ unknown; A→A self-loop ok
    }
    fragment = adapter.build(_FakeRegion("d", display="diagram"), ctx)
    html = _render(fragment)
    assert "ZZZ" not in html
    # Self-loop A→A still rendered
    assert html.count("A") >= 2


def test_diagram_empty_renders_legacy_hardcoded_message() -> None:
    """v0.66.118: empty diagram emits `<p class="dz-diagram-empty">…</p>`
    matching the legacy template's hardcoded copy. region.empty_message
    is no longer threaded through — the legacy template hardcodes the
    string and we match it for byte-equivalence."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("d", display="diagram", empty_message="ignored"),
        {"nodes": []},
    )
    html = _render(fragment)
    assert "dz-diagram-empty" in html
    assert "No entity relationships to display." in html
    assert "ignored" not in html  # region.empty_message is intentionally ignored


def test_heatmap_renders_dedicated_primitive() -> None:
    """v0.66.115: HEATMAP now uses dedicated `Heatmap` primitive
    matching `dz-heatmap-region` byte-for-byte. Threshold-banded
    cell tones via data-dz-heatmap-tone."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "heatmap_matrix": [
            {
                "row": "mon",
                "row_id": "1",
                "cells": [
                    {"col": "9am", "value": 5.0},
                    {"col": "10am", "value": 0.0},
                ],
            },
            {
                "row": "tue",
                "row_id": "2",
                "cells": [
                    {"col": "9am", "value": 0.0},
                    {"col": "10am", "value": 3.0},
                ],
            },
        ],
        "heatmap_col_values": ["9am", "10am"],
        "heatmap_thresholds": [2.0, 4.0],
    }
    fragment = adapter.build(_FakeRegion("h", display="heatmap"), ctx)
    html = _render(fragment)
    assert "dz-heatmap-region" in html
    assert "mon" in html and "tue" in html
    assert "9am" in html and "10am" in html
    assert "5.0" in html and "3.0" in html
    assert 'data-dz-heatmap-tone="good"' in html  # 5.0 > 4.0
    assert 'data-dz-heatmap-tone="bad"' in html  # 0.0 < 2.0


def test_confirm_action_panel_legacy_prompt_ctx_renders_synthetic_checklist() -> None:
    """Phase 4A fallback: ctx with `prompt` + `action_label` (the
    pre-Phase-4B.1.d shape) is converted into a synthetic single-item
    ConfirmGate. The prompt becomes the checklist title; the panel
    renders in the off state. Mainly for tests; runtime should use
    state_value + confirmations."""
    adapter = WorkspaceRegionAdapter()
    ctx = {"prompt": "This will permanently delete 5 items.", "action_label": "Delete"}
    fragment = adapter.build(
        _FakeRegion("c", display="confirm_action_panel", title="Confirm Delete"), ctx
    )
    html = _render(fragment)
    assert "Confirm Delete" in html
    assert "permanently delete 5 items" in html
    # No more bracketed-text placeholder — replaced by the typed ConfirmGate
    assert "dz-confirm-panel" in html
    assert "&quot;" not in html  # No broken HTML escapes


def test_confirm_action_panel_off_state_renders_alpine_gated_checklist() -> None:
    """Phase 4B preferred: state_value=off + confirmations[] produces
    an Alpine `dzConfirmGate(N)` checklist with `data-dz-required-count`
    matching the count of `required: true` items, plus dual-button
    primary (Alpine-gated) + secondary (always enabled)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "state_value": "off",
        "confirmations": [
            {
                "title": "I have reviewed the data",
                "caption": "All records will be synced",
                "required": True,
            },
            {"title": "I have legal authority", "required": True},
            {"title": "Optional: notify the team"},
        ],
        "primary_action_url": "/admin/sync/confirm",
        "secondary_action_url": "/admin/sync/draft",
        "audit_enabled": True,
    }
    html = _render(adapter.build(_FakeRegion("c", display="confirm_action_panel"), ctx))
    assert 'data-dz-state-value="off"' in html
    assert 'x-data="dzConfirmGate(3)"' in html
    assert 'data-dz-required-count="2"' in html
    assert "I have reviewed the data" in html
    assert "All records will be synced" in html
    assert "/admin/sync/confirm" in html
    assert "/admin/sync/draft" in html
    assert "is-disabled" in html  # Alpine class binding
    assert "dz-confirm-audit" in html


def test_confirm_action_panel_live_state_renders_summary_and_revoke() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "state_value": "live",
        "revoke_url": "/admin/sync/revoke",
    }
    html = _render(adapter.build(_FakeRegion("c", display="confirm_action_panel"), ctx))
    assert "Currently live" in html
    assert "/admin/sync/revoke" in html
    assert "dz-confirm-revoke" in html
    assert "dz-confirm-checklist" not in html  # no checklist in live state


def test_confirm_action_panel_revoked_state_offers_re_enable() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "state_value": "revoked",
        "primary_action_url": "/admin/sync/reenable",
    }
    html = _render(adapter.build(_FakeRegion("c", display="confirm_action_panel"), ctx))
    assert "revoked" in html.lower()
    assert "Re-enable" in html
    assert "/admin/sync/reenable" in html


def test_confirm_action_panel_drops_malformed_confirmations() -> None:
    """Confirmations with empty titles or non-dict entries silently drop."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "state_value": "off",
        "confirmations": [
            None,
            42,
            {"title": ""},  # empty title
            {"title": "Valid item", "required": True},
        ],
        "primary_action_url": "/x",
    }
    html = _render(adapter.build(_FakeRegion("c", display="confirm_action_panel"), ctx))
    assert "Valid item" in html
    assert 'data-dz-required-count="1"' in html
    assert 'x-data="dzConfirmGate(1)"' in html  # only valid items count


def test_search_box_renders_typed_search_box_primitive() -> None:
    """Phase 4B.1.d: `_build_search_box` now produces the typed
    `SearchBox` primitive — HTMX FTS input + lazy result panel +
    Alpine coaching toggle. Replaced the prior plain-Field rendering."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "source_entity": "Manuscript",
        "placeholder": "Find a manuscript",
        "coaching_message": "Type a title or keyword",
    }
    fragment = adapter.build(_FakeRegion("manuscript_search", display="search_box"), ctx)
    html = _render(fragment)
    assert "dz-search-box-region" in html
    assert 'hx-get="/_dazzle/fts/Manuscript?html=1"' in html
    assert 'hx-trigger="input changed delay:250ms, search"' in html
    assert 'aria-live="polite"' in html
    assert 'x-show="!q"' in html
    assert "Type a title or keyword" in html


def test_search_box_uses_region_name_as_endpoint_fallback() -> None:
    """When `source_entity` is missing from ctx, the adapter falls
    back to `/_dazzle/fts/<region.name>?html=1`. Mainly for tests; the
    runtime always supplies source_entity."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("ticket_search", display="search_box"),
        {"placeholder": "Find tickets…"},
    )
    html = _render(fragment)
    assert 'hx-get="/_dazzle/fts/ticket_search?html=1"' in html
    assert "Find tickets" in html


def test_search_box_default_coaching_message() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("s", display="search_box"),
        {"source_entity": "Item"},
    )
    assert "Type to search" in _render(fragment)


def test_search_box_results_div_uses_unique_dom_id_per_region() -> None:
    """Multiple SearchBoxes on one page must have distinct results
    panels. The panel id is derived from the `name` ctx key (or the
    region name as fallback)."""
    adapter = WorkspaceRegionAdapter()
    ctx_a = {"source_entity": "A", "name": "search_a"}
    ctx_b = {"source_entity": "B", "name": "search_b"}
    html_a = _render(adapter.build(_FakeRegion("r", display="search_box"), ctx_a))
    html_b = _render(adapter.build(_FakeRegion("r", display="search_box"), ctx_b))
    assert "dz-search-results-search_a" in html_a
    assert "dz-search-results-search_b" in html_b


def test_bar_track_renders_typed_primitive_with_aria() -> None:
    """Phase 4B.1.b — `bar_track` now produces the typed BarTrack
    primitive directly (replaced the prior alias to _build_progress).
    HTML matches the legacy bar_track.html template: aria-progressbar
    semantics, fill width, summary line."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "bar_track_rows": [
            {"label": "CPU", "value": 80, "formatted_value": "80%", "fill_pct": 80},
            {"label": "RAM", "value": 45, "formatted_value": "45%", "fill_pct": 45},
        ],
        "bar_track_max": 100,
    }
    html = _render(adapter.build(_FakeRegion("b", display="bar_track"), ctx))
    assert 'class="dz-bar-track-region"' in html  # v0.66.98 — legacy outer wrapper
    assert "dz-bar-track-rows" in html
    assert 'role="progressbar"' in html
    # v0.66.110: int-narrowing — whole-valued floats render without `.0`
    # to match Jinja's `{{ value }}` rendering.
    assert 'aria-valuemax="100"' in html
    assert 'aria-valuenow="80"' in html
    assert "width: 80%" in html
    assert "2 rows · scale 0–100" in html


def test_bar_track_legacy_items_fallback() -> None:
    """Pre-Phase-4B.1.b ctx shape `{items: [{label, percent}]}` is still
    accepted — the runtime currently still passes this shape, and the
    Phase 4B.2 translator will switch it to bar_track_rows. Until then
    the adapter handles both."""
    adapter = WorkspaceRegionAdapter()
    ctx = {"items": [{"label": "X", "percent": 25}, {"label": "Y", "percent": 75}]}
    html = _render(adapter.build(_FakeRegion("b", display="bar_track"), ctx))
    assert "X" in html and "25%" in html
    assert "Y" in html and "75%" in html


def test_bar_track_clamps_out_of_range_fill_pct() -> None:
    """fill_pct > 100 or < 0 is silently clamped to [0, 100] before
    construction so the strict BarTrack invariant doesn't reject."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "bar_track_rows": [
            {"label": "Over", "value": 999, "formatted_value": "999", "fill_pct": 250},
            {"label": "Under", "value": -10, "formatted_value": "-10", "fill_pct": -50},
        ],
        "bar_track_max": 100,
    }
    html = _render(adapter.build(_FakeRegion("b", display="bar_track"), ctx))
    assert "width: 100" in html  # clamped to 100
    assert "width: 0" in html  # clamped to 0


def test_bar_track_drops_malformed_rows() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "bar_track_rows": [
            None,
            42,
            {"label": ""},  # empty label
            {"label": "OK", "value": "bad", "fill_pct": 50},  # bad value
            {"label": "Good", "value": 50, "formatted_value": "50", "fill_pct": 50},
        ]
    }
    html = _render(adapter.build(_FakeRegion("b", display="bar_track"), ctx))
    assert "Good" in html
    assert "OK" not in html  # bad value caused drop


def test_bullet_renders_track_with_actual_target_tick() -> None:
    """Phase 4B.4 wave 2 (v0.66.105): adapter consumes the authored
    `bullet_rows` shape directly with `bullet_max_value` for the
    percentage scale. Emits the legacy `dz-bullet-region` shape with
    per-row label + track + actual bar + target tick + value."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "bullet_rows": [
            {"label": "Q1", "actual": 100, "target": 100},
            {"label": "Q2", "actual": 70, "target": 100},
            {"label": "Q3", "actual": 30, "target": None},
        ],
        "bullet_max_value": 100,
    }
    fragment = adapter.build(_FakeRegion("b", display="bullet"), ctx)
    html = _render(fragment)
    assert "Q1" in html and "Q2" in html and "Q3" in html
    assert 'class="dz-bullet-region"' in html
    assert 'class="dz-bullet-actual"' in html
    # Q1 + Q2 have target ticks; Q3 doesn't.
    assert html.count('class="dz-bullet-target"') == 2
    assert "3 rows · scale 0–100" in html


def test_bullet_drops_non_numeric_values() -> None:
    """Rows with non-coercible `actual`/`target` silently drop —
    matches the adapter's permissive parsing convention."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "bullet_rows": [
            {"label": "X", "actual": "n/a", "target": "n/a"},  # drops
            {"label": "Y", "actual": 50, "target": 100},
        ],
        "bullet_max_value": 100,
    }
    fragment = adapter.build(_FakeRegion("b", display="bullet"), ctx)
    html = _render(fragment)
    assert "Y" in html
    assert "n/a" not in html
    assert "1 rows · scale 0–100" in html


def test_tree_renders_indented_labels_recursively() -> None:
    """`display: tree` flattens nested children into a Stack of Text
    rows, with each level of nesting prefixed by two spaces."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {
                "name": "Root",
                "children": [
                    {"name": "Child1"},
                    {"name": "Child2", "children": [{"name": "Grand"}]},
                ],
            }
        ]
    }
    fragment = adapter.build(_FakeRegion("t", display="tree"), ctx)
    html = _render(fragment)
    assert "Root" in html
    assert "Child1" in html
    assert "Child2" in html
    assert "Grand" in html


def test_pipeline_steps_renders_row_of_cards() -> None:
    """Each step becomes a Card with a Heading and optional Text
    description, arranged in a horizontal Row."""
    adapter = WorkspaceRegionAdapter()
    # v0.66.106: adapter consumes the authored `pipeline_stage_data`
    # shape directly (matches production runtime ctx) instead of the
    # Phase 4A `steps` shape. Caption renders alongside label + value
    # in the legacy `dz-pipeline-stage` row.
    ctx = {
        "pipeline_stage_data": [
            {"label": "Plan", "value": 1, "caption": "Scope locked"},
            {"label": "Build", "value": 2},
            {"label": "Ship", "value": None, "caption": "Pending"},
        ]
    }
    fragment = adapter.build(_FakeRegion("p", display="pipeline_steps"), ctx)
    html = _render(fragment)
    assert "Plan" in html and "Build" in html and "Ship" in html
    assert "Scope locked" in html
    assert "Pending" in html
    # Last stage with value=None renders as "—".
    assert "—" in html
    # 3 stages → 2 connector pairs (last omits).
    assert html.count('class="dz-pipeline-connector"') == 2


def test_action_grid_renders_cta_cards_with_tone_and_count() -> None:
    """`display: action_grid` builds typed ActionCard primitives — tone
    tinting, optional Lucide icon, optional count badge, optional URL.
    Phase 4B.1.b replaced the prior `_build_grid` alias with a dedicated
    builder."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "action_cards": [
            {
                "label": "Open tickets",
                "icon": "ticket",
                "count": 12,
                "tone": "warning",
                "url": "/tickets",
            },
            {"label": "New issue", "icon": "plus", "tone": "accent", "url": "/issues/new"},
            {"label": "Static", "tone": "neutral"},
        ],
        "columns": 3,
    }
    fragment = adapter.build(_FakeRegion("a", display="action_grid"), ctx)
    html = _render(fragment)
    assert "dz-action-card" in html
    assert "Open tickets" in html and "New issue" in html and "Static" in html
    assert 'data-dz-tone="warning"' in html
    assert 'data-dz-tone="accent"' in html
    # "ticket" is in the vendored registry -> server-side inline SVG (TASTE-6)
    assert '<span class="dz-action-card-icon" aria-hidden="true"><svg' in html
    assert "/tickets" in html
    assert ">12<" in html  # count badge


def test_action_grid_accepts_legacy_action_card_data_alias() -> None:
    """ctx['action_card_data'] is accepted as alias for ctx['action_cards']
    so the legacy ctx shape from workspace_rendering.py works during
    Phase 4B.2's translator wiring without two ctx payloads."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "action_card_data": [
            {"label": "Restart", "tone": "destructive", "url": "/admin/restart"},
        ]
    }
    fragment = adapter.build(_FakeRegion("a", display="action_grid"), ctx)
    html = _render(fragment)
    assert "Restart" in html
    assert 'data-dz-tone="destructive"' in html


def test_action_grid_drops_invalid_entries() -> None:
    """Cards with empty labels, non-dict entries, or unknown tones are
    silently dropped — the strict ActionCard primitive would raise."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "action_cards": [
            None,
            42,
            {"label": ""},  # empty label
            {"label": "OK", "tone": "purple"},  # unknown tone falls back to neutral
        ]
    }
    fragment = adapter.build(_FakeRegion("a", display="action_grid"), ctx)
    html = _render(fragment)
    assert "OK" in html
    assert 'data-dz-tone="neutral"' in html  # purple fell back


def test_action_grid_count_zero_renders_badge() -> None:
    """`count = 0` renders a badge with "0"; `count = None` (or omitted)
    renders no badge."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "action_cards": [
            {"label": "Zero", "count": 0, "tone": "positive"},
            {"label": "None", "tone": "neutral"},
        ]
    }
    fragment = adapter.build(_FakeRegion("a", display="action_grid"), ctx)
    html = _render(fragment)
    assert ">0<" in html  # zero badge rendered
    # The "None" card has no count badge — verify by checking only one badge appears
    assert html.count("dz-action-card-count") == 1


def test_profile_card_renders_full_identity_panel() -> None:
    """`display: profile_card` builds a typed ProfileCard with
    avatar/initials + name + meta + stats grid + facts list. Phase
    4B.1.b replaced the prior `_build_detail` alias with a dedicated
    builder so the legacy `profile_card_data` shape lands intact."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "profile_card_data": {
            "primary": "Alice Adams",
            "secondary": "Senior Engineer",
            "avatar_url": "/avatars/alice.png",
            "stats": [
                {"label": "Tickets", "value": 23},
                {"label": "Closed", "value": 18},
                {"label": "SLA", "value": None},
            ],
            "facts": ["Joined 2024", "Lead reviewer"],
        }
    }
    fragment = adapter.build(_FakeRegion("p", display="profile_card"), ctx)
    html = _render(fragment)
    assert "dz-profile-card" in html
    assert "Alice Adams" in html and "Senior Engineer" in html
    assert "Tickets" in html and "23" in html
    assert "Joined 2024" in html and "Lead reviewer" in html
    assert "—" in html  # empty SLA stat falls back to em-dash
    assert "/avatars/alice.png" in html


def test_profile_card_initials_when_no_avatar() -> None:
    """Initials path is used when avatar_url is empty."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "profile_card_data": {
            "primary": "Bob Brown",
            "initials": "BB",
        }
    }
    fragment = adapter.build(_FakeRegion("p", display="profile_card"), ctx)
    html = _render(fragment)
    assert "dz-profile-initials" in html
    assert ">BB<" in html


def test_profile_card_drops_malformed_stats_and_facts() -> None:
    """Stats with missing labels and non-string facts are silently
    dropped to keep the strict ProfileCard primitive happy."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "profile_card_data": {
            "primary": "X",
            "stats": [
                None,  # not a dict
                {"value": 5},  # missing label
                {"label": "OK", "value": 9},
            ],
            "facts": [None, "", "real fact"],
        }
    }
    fragment = adapter.build(_FakeRegion("p", display="profile_card"), ctx)
    html = _render(fragment)
    assert "OK" in html and "9" in html
    assert "real fact" in html


def test_profile_card_empty_data_renders_empty_state() -> None:
    """When none of primary/avatar_url/initials are populated the
    adapter degrades to EmptyState rather than raising ValueError."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("p", display="profile_card", empty_message="No profile."),
        {"profile_card_data": {"secondary": "just meta"}},
    )
    assert "No profile." in _render(fragment)


def test_profile_card_no_data_uses_default_empty_message() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(_FakeRegion("p", display="profile_card"), {})
    assert "No profile data available." in _render(fragment)


def test_progress_renders_typed_stage_bar_with_progress_element() -> None:
    """Phase 4B.1.b: `_build_progress` produces the typed StageBar
    primitive — `<progress>` header + chip list + summary line.
    Replaced the prior Stack-of-Row(Text, Badge) shape."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "stage_counts": [
            {"name": "Backlog", "count": 12, "complete": False},
            {"name": "In Progress", "count": 5, "complete": False},
            {"name": "Done", "count": 23, "complete": True},
        ],
        "complete_pct": 57.5,
        "complete_count": 23,
        "progress_total": 40,
    }
    html = _render(adapter.build(_FakeRegion("p", display="progress"), ctx))
    assert "dz-progress-header" in html
    assert "<progress data-dz-progress" in html
    assert "57.5%" in html
    assert "Backlog (12)" in html
    assert 'data-dz-stage-tone="complete"' in html
    assert "23 of 40 complete" in html


def test_progress_chip_tone_maps_from_complete_and_count() -> None:
    """tone: complete > active (count>0) > empty (count==0)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "stage_counts": [
            {"name": "Empty", "count": 0, "complete": False},  # empty
            {"name": "Active", "count": 5, "complete": False},  # active
            {"name": "Complete", "count": 8, "complete": True},  # complete
        ]
    }
    html = _render(adapter.build(_FakeRegion("p", display="progress"), ctx))
    assert 'data-dz-stage-tone="empty"' in html
    assert 'data-dz-stage-tone="active"' in html
    assert 'data-dz-stage-tone="complete"' in html


def test_progress_legacy_items_fallback_treats_100_pct_as_complete() -> None:
    """Pre-Phase-4B.1.b ctx shape `{items: [{label, percent}]}` is still
    accepted — each row becomes a synthetic stage with `complete=True`
    when percent==100. The Phase 4B.2 translator will switch the
    runtime to stage_counts."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"label": "Build", "percent": 75},
            {"label": "Test", "percent": 100},
        ]
    }
    html = _render(adapter.build(_FakeRegion("p", display="progress"), ctx))
    assert "Build (75%)" in html
    assert "Test (100%)" in html
    # Test stage at 100% is marked complete
    assert 'data-dz-stage-tone="complete"' in html


def test_progress_clamps_out_of_range_complete_pct() -> None:
    """complete_pct outside [0, 100] is clamped before constructing
    the StageBar (which would raise)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "stage_counts": [{"name": "X", "count": 1, "complete": False}],
        "complete_pct": 250,
    }
    html = _render(adapter.build(_FakeRegion("p", display="progress"), ctx))
    # v0.66.105: emit narrows whole values to int repr for byte-equivalence
    # with the legacy Jinja `{{ complete_pct }}` rendering — `100.0` becomes
    # `100`. Fractional values still render with the trailing decimal.
    assert "100%" in html  # clamped to 100, integer repr
    assert "250" not in html


def test_progress_omits_summary_when_total_is_zero() -> None:
    """The 'N of M complete' summary only renders when progress_total > 0."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "stage_counts": [{"name": "X", "count": 1, "complete": False}],
        "complete_count": 0,
        "progress_total": 0,
    }
    html = _render(adapter.build(_FakeRegion("p", display="progress"), ctx))
    assert "dz-progress-summary" not in html


def test_status_list_renders_authored_entries() -> None:
    """Phase 4B.4 wave 1 (v0.66.104): adapter consumes `status_entries`
    (authored shape) directly and emits the legacy `dz-status-list`
    structure byte-for-byte. The prior items+status_variants shape was
    a Phase 4A workaround that didn't match production ctx; runtime
    now supplies authored entries per v0.61.69's design."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "status_entries": [
            {
                "title": "Service A",
                "state": "positive",
                "caption": "All systems normal",
            },
            {"title": "Service B", "state": "destructive", "icon": "alert-triangle"},
        ],
    }
    fragment = adapter.build(_FakeRegion("s", display="status_list"), ctx)
    html = _render(fragment)
    assert "Service A" in html and "Service B" in html
    assert 'data-dz-state="positive"' in html
    assert 'data-dz-state="destructive"' in html
    assert "All systems normal" in html
    assert 'data-lucide="alert-triangle"' in html


def test_status_list_unknown_state_falls_back_to_neutral() -> None:
    """A `state` value outside the allowed set silently coerces to
    'neutral' (matching the legacy template's `state | default('neutral')`)
    rather than crashing the StatusListEntry primitive's invariant."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "status_entries": [
            {"title": "Mystery", "state": "purple"},  # not a real state
        ],
    }
    fragment = adapter.build(_FakeRegion("s", display="status_list"), ctx)
    html = _render(fragment)
    # Coerced to neutral → no pill, spacer icon column.
    assert 'data-dz-state="neutral"' in html
    assert "dz-status-list-pill" not in html


def test_funnel_chart_renders_dedicated_primitive() -> None:
    """v0.66.111: FUNNEL_CHART now uses a dedicated `Funnel` primitive
    matching `dz-funnel-chart-region` byte-for-byte. Stages render in
    declared order (kanban_columns), with width relative to the first
    stage's count and a 20% minimum."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "kanban_columns": ["signed_up", "verified", "paid"],
        "group_by": "status",
        "items": (
            [{"status": "signed_up"}] * 100
            + [{"status": "verified"}] * 50
            + [{"status": "paid"}] * 25
        ),
        "total": 175,
    }
    fragment = adapter.build(_FakeRegion("f", display="funnel_chart"), ctx)
    html = _render(fragment)
    assert "dz-funnel-chart-region" in html
    # Stages preserved in declared order: signed_up (100), verified (50), paid (25).
    pos_signed = html.find("signed_up")
    pos_verified = html.find("verified")
    pos_paid = html.find("paid")
    assert pos_signed < pos_verified < pos_paid
    # Width relative to first stage: 100% / 50% / 25%.
    assert "width: 100%" in html
    assert "width: 50%" in html
    # 25% < 20% min → clamped to 20%.
    assert "width: 25%" in html or "width: 20%" in html


def test_queue_renders_minimal_items() -> None:
    """v0.66.117: QUEUE now uses dedicated QueueRegion primitive
    matching `dz-queue-region` byte-for-byte. With `display_key=title`
    and items having `title`, the row title falls back to title via
    the (display+_display → display → id) chain."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"id": 1, "title": "Item One", "title_display": "Item One", "status": "open"},
            {"id": 2, "title": "Item Two", "title_display": "Item Two", "status": "open"},
        ],
        "columns": [{"key": "title", "label": "Title"}],
        "display_key": "title",
    }
    fragment = adapter.build(_FakeRegion("q", display="queue"), ctx)
    html = _render(fragment)
    assert "Item One" in html and "Item Two" in html
    assert "dz-queue-region" in html


def test_queue_renders_transition_buttons_when_supplied() -> None:
    """Phase 4B.1.d: queue_transitions + status_field + api_endpoint
    produce per-row Button primitives with hx_put + hx_vals + hx_ext.
    Buttons matching the item's current state are skipped."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"id": 42, "title": "Bug A", "status": "open"},
        ],
        "endpoint": "/api/regions/tickets",
        "region_name": "tickets",
        "queue_transitions": [
            {"label": "Resolve", "to_state": "resolved"},
            {"label": "Close", "to_state": "closed"},
            {"label": "Reopen", "to_state": "open"},  # matches current — should skip
        ],
        "queue_status_field": "status",
        "queue_api_endpoint": "/api/tickets",
    }
    html = _render(adapter.build(_FakeRegion("q", display="queue"), ctx))
    assert 'hx-put="/api/tickets/42"' in html
    assert "Resolve" in html
    assert "Close" in html
    assert "Reopen" not in html  # skipped — current state already 'open'
    # htmx 4: json-enc dropped — queue transition PUTs go url-encoded and the
    # server's tolerant body parser handles them (no hx-ext needed).


def test_queue_count_metrics_overflow_render_via_dedicated_primitive() -> None:
    """v0.66.117: Queue chrome is now part of the dedicated QueueRegion
    primitive. Filter bar / CSV export are deferred (legacy renders
    them but the typed QueueRegion doesn't yet thread them through).
    Count row, metrics, and overflow line render via the primitive."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"id": 1, "title": "X", "status": "open"}],
        "metrics": [
            {"label": "Open", "value": 12},
            {"label": "Closed", "value": 88},
        ],
        "endpoint": "/api/regions/r",
        "region_name": "r",
        "total": 100,
    }
    html = _render(adapter.build(_FakeRegion("r", display="queue"), ctx))
    assert "dz-queue-count" in html  # count row
    assert "100" in html  # total in count row
    assert "dz-queue-metric" in html  # metrics row
    assert "Showing 1 of 100" in html  # overflow line


def test_queue_skips_transitions_when_required_ctx_keys_missing() -> None:
    """Transition rendering requires queue_status_field + queue_api_endpoint
    + an item.id. Missing any of these silently skips transition
    buttons rather than crashing — the row still renders."""
    adapter = WorkspaceRegionAdapter()
    # Missing queue_api_endpoint
    ctx = {
        "items": [{"id": 1, "title": "X", "title_display": "X", "status": "open"}],
        "display_key": "title",
        "queue_transitions": [{"label": "Close", "to_state": "closed"}],
        "queue_status_field": "status",
        # queue_api_endpoint deliberately missing
    }
    html = _render(adapter.build(_FakeRegion("q", display="queue"), ctx))
    assert "hx-put" not in html
    assert "X" in html  # item still renders


def test_queue_transition_to_current_state_silently_skipped() -> None:
    """A transition whose to_state matches the item's current value
    is filtered out — preserves the legacy 'don't offer transition
    to your current state' UX."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"id": 1, "title": "X", "status": "open"}],
        "endpoint": "/api/r",
        "region_name": "r",
        "queue_transitions": [
            {"label": "Reopen", "to_state": "open"},  # matches current — skip
            {"label": "Close", "to_state": "closed"},  # different — render
        ],
        "queue_status_field": "status",
        "queue_api_endpoint": "/api/items",
    }
    html = _render(adapter.build(_FakeRegion("q", display="queue"), ctx))
    assert "Close" in html
    assert "Reopen" not in html


def test_histogram_renders_dedicated_primitive() -> None:
    """v0.66.111: HISTOGRAM now uses a dedicated `Histogram` primitive
    + `histogram_svg` helper matching `dz-histogram-region` byte-for-
    byte. Bins carry `low`/`high` for continuous-axis positioning."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "histogram_bins": [
            {"label": "0-10", "count": 5, "low": 0, "high": 10},
            {"label": "10-20", "count": 15, "low": 10, "high": 20},
            {"label": "20-30", "count": 8, "low": 20, "high": 30},
        ]
    }
    fragment = adapter.build(_FakeRegion("h", display="histogram"), ctx)
    html = _render(fragment)
    assert "dz-histogram-region" in html
    assert "dz-histogram-svg" in html
    assert "<title>0-10: 5</title>" in html
    assert "3 bins · 28 samples · peak 15" in html


def test_activity_feed_dispatches_through_timeline() -> None:
    """`display: activity_feed` reuses the Timeline renderer — feeds
    are timelines spelt differently in DSL."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"title": "Logged in", "created_at": "2026-05-07T09:00:00"},
            {"title": "Saved record", "created_at": "2026-05-07T09:01:00"},
        ]
    }
    fragment = adapter.build(_FakeRegion("feed", display="activity_feed"), ctx)
    html = _render(fragment)
    assert "Logged in" in html
    assert "Saved record" in html


# ───────────────── CohortStrip (#1018, v0.67.7) ───────────────────


def _cohort_region(
    *,
    member_via: str = "profile",
    lenses: list[dict] | None = None,
    default_lens: str = "",
) -> object:
    """Build a region object exposing a CohortStripConfig — duck-
    typed so the unit test doesn't need a full WorkspaceRegion."""
    from dazzle.core.ir.workspaces import CohortStripConfig, CohortStripLens

    lens_data = lenses or [
        {"id": "attainment", "label": "Attainment", "primary": "score"},
        {"id": "attendance", "label": "Attendance", "primary": "att_pct"},
    ]
    cfg = CohortStripConfig(
        member_via=member_via,
        lenses=[CohortStripLens(**spec) for spec in lens_data],
        default_lens=default_lens,
    )

    class _Region:
        name = "cohort"
        title = None
        display = "cohort_strip"
        empty_message = None
        cohort_strip_config = cfg

    return _Region()


def test_cohort_strip_dispatches_to_builder() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _cohort_region()
    surface = adapter.build(region, {"cohort_cells": [], "cohort_endpoint": "/r/cohort"})
    assert isinstance(surface, Surface)
    html = _render(surface)
    assert 'class="dz-cohort-strip-region"' in html


def test_cohort_strip_emits_lens_toggle_with_active_from_default() -> None:
    """When ctx omits `cohort_active_lens`, the config's
    default_lens drives the active highlight."""
    adapter = WorkspaceRegionAdapter()
    region = _cohort_region(default_lens="attendance")
    surface = adapter.build(region, {"cohort_cells": [], "cohort_endpoint": "/r/cohort"})
    html = _render(surface)
    # Two tabs, one active.
    assert html.count('aria-pressed="true"') == 1
    assert html.count('aria-pressed="false"') == 1
    # The active one is "Attendance" (matches default_lens).
    import re

    match = re.search(r'aria-pressed="true"[^>]*>([^<]+)</button>', html)
    assert match is not None
    assert "Attendance" in match.group(1)


def test_cohort_strip_active_lens_from_ctx_wins_over_default() -> None:
    """Explicit `cohort_active_lens` in ctx overrides the config
    default — supports the `?lens=<id>` URL-param flow."""
    adapter = WorkspaceRegionAdapter()
    region = _cohort_region(default_lens="attendance")
    surface = adapter.build(
        region,
        {
            "cohort_cells": [],
            "cohort_endpoint": "/r/cohort",
            "cohort_active_lens": "attainment",
        },
    )
    html = _render(surface)
    import re

    match = re.search(r'aria-pressed="true"[^>]*>([^<]+)</button>', html)
    assert match is not None
    assert "Attainment" in match.group(1)


def test_cohort_strip_unknown_active_lens_falls_back_to_first() -> None:
    """A stale URL param like `?lens=ghost` should not crash; the
    adapter coerces to the first declared lens."""
    adapter = WorkspaceRegionAdapter()
    region = _cohort_region()  # default unset
    surface = adapter.build(
        region,
        {
            "cohort_cells": [],
            "cohort_endpoint": "/r/cohort",
            "cohort_active_lens": "ghost-lens",
        },
    )
    html = _render(surface)
    # Active is the first config lens (attainment).
    import re

    match = re.search(r'aria-pressed="true"[^>]*>([^<]+)</button>', html)
    assert match is not None
    assert "Attainment" in match.group(1)


def test_cohort_strip_empty_cells_renders_empty_state() -> None:
    """With zero ctx cells, the strip renders the configured
    empty_message — lens toggle still present so the user can swap."""

    class _Region:
        name = "cohort"
        title = None
        display = "cohort_strip"
        empty_message = "Nobody here yet."
        cohort_strip_config = _cohort_region().cohort_strip_config

    adapter = WorkspaceRegionAdapter()
    surface = adapter.build(_Region(), {"cohort_endpoint": "/r/cohort"})
    html = _render(surface)
    assert "Nobody here yet." in html
    assert 'class="dz-cohort-strip-empty"' in html
    assert 'role="tablist"' in html  # toggle still rendered


def test_cohort_strip_builds_cells_from_ctx_dicts() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _cohort_region()
    cells_data = [
        {
            "member_id": "p1",
            "member_name": "Alice",
            "primary_value": "78",
            "subtitle": "9G",
            "tone": "good",
            "drill_url": "/m/p1",
        },
        {
            "member_id": "p2",
            "member_name": "Bob",
            "primary_value": "62",
            "subtitle": "9G",
            "tone": "warn",
        },
    ]
    surface = adapter.build(region, {"cohort_cells": cells_data, "cohort_endpoint": "/r/cohort"})
    html = _render(surface)
    assert 'data-member-id="p1"' in html
    assert 'data-member-id="p2"' in html
    assert "Alice" in html
    assert "Bob" in html
    assert 'data-dz-tone="good"' in html
    assert 'data-dz-tone="warn"' in html


def test_cohort_strip_skips_cells_with_missing_member_id() -> None:
    """Defensive: an upstream resolver that produces a row with no
    member_id (FK miss?) shouldn't crash the primitive."""
    adapter = WorkspaceRegionAdapter()
    region = _cohort_region()
    cells_data = [
        {"member_id": "p1", "member_name": "OK", "primary_value": "1"},
        {"member_id": "", "member_name": "Bad", "primary_value": "?"},
        {"member_name": "Missing key", "primary_value": "?"},
    ]
    surface = adapter.build(region, {"cohort_cells": cells_data, "cohort_endpoint": "/r/cohort"})
    html = _render(surface)
    assert 'data-member-id="p1"' in html
    assert "Bad" not in html
    assert "Missing key" not in html


def test_cohort_strip_no_lenses_renders_empty_state_surface() -> None:
    """A misconfigured region with zero lenses degrades to an
    EmptyState rather than crashing the primitive's at-least-one-
    lens invariant."""
    from dazzle.core.ir.workspaces import CohortStripConfig

    class _Region:
        name = "cohort"
        title = None
        display = "cohort_strip"
        empty_message = None
        cohort_strip_config = CohortStripConfig(member_via="x", lenses=[])

    adapter = WorkspaceRegionAdapter()
    surface = adapter.build(_Region(), {})
    html = _render(surface)
    assert "Cohort strip not configured" in html


def test_cohort_strip_unknown_tone_coerces_to_neutral() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _cohort_region()
    surface = adapter.build(
        region,
        {
            "cohort_cells": [
                {"member_id": "p1", "member_name": "A", "primary_value": "1", "tone": "rainbow"},
            ],
            "cohort_endpoint": "/r/cohort",
        },
    )
    html = _render(surface)
    assert 'data-dz-tone="neutral"' in html
    assert "rainbow" not in html


def test_cohort_strip_endpoint_falls_back_to_region_url() -> None:
    """If `cohort_endpoint` isn't supplied, ctx['region_url'] is used —
    matches the convention for hx-target endpoints in this codebase."""
    adapter = WorkspaceRegionAdapter()
    region = _cohort_region()
    surface = adapter.build(region, {"cohort_cells": [], "region_url": "/api/regions/cohort"})
    html = _render(surface)
    assert 'hx-get="/api/regions/cohort?lens=' in html


# ───────────────── DayTimeline (#1016, v0.67.8) ───────────────────


def _day_timeline_region(
    *,
    starts_at: str = "period_start",
    ends_at: str = "period_end",
    card: str = "lesson_card",
    empty_message: str | None = None,
) -> object:
    """Build a region object exposing a DayTimelineConfig — duck-
    typed so the unit test doesn't need a full WorkspaceRegion."""
    from dazzle.core.ir.workspaces import DayTimelineConfig

    cfg = DayTimelineConfig(starts_at=starts_at, ends_at=ends_at, card=card)

    class _Region:
        name = "today"
        title = None
        display = "day_timeline"
        cohort_strip_config = None

    r = _Region()
    r.empty_message = empty_message  # type: ignore[attr-defined]
    r.day_timeline_config = cfg  # type: ignore[attr-defined]
    return r


def test_day_timeline_dispatches_to_builder() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _day_timeline_region()
    surface = adapter.build(region, {})
    assert isinstance(surface, Surface)
    html = _render(surface)
    assert 'class="dz-day-timeline-region"' in html


def test_day_timeline_empty_slots_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _day_timeline_region(empty_message="No periods today.")
    surface = adapter.build(region, {"day_timeline_slots": []})
    html = _render(surface)
    assert 'class="dz-day-timeline-empty"' in html
    assert "No periods today." in html


def test_day_timeline_builds_slots_with_positions() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _day_timeline_region()
    slots_data = [
        {"slot_id": "p1", "label": "Period 1 — 09:00", "position": "before"},
        {"slot_id": "p2", "label": "Period 2 — 10:00", "position": "active"},
        {"slot_id": "p3", "label": "Period 3 — 11:00", "position": "after"},
    ]
    surface = adapter.build(region, {"day_timeline_slots": slots_data})
    html = _render(surface)
    assert 'data-slot-id="p1"' in html
    assert "is-before" in html
    assert "is-active" in html
    assert "is-after" in html
    assert html.count('data-dz-position="active"') == 1


def test_day_timeline_unknown_position_falls_through_to_after() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _day_timeline_region()
    surface = adapter.build(
        region,
        {
            "day_timeline_slots": [
                {"slot_id": "p1", "label": "P1", "position": "weird"},
            ],
        },
    )
    html = _render(surface)
    assert "is-after" in html


def test_day_timeline_collapses_multiple_active_slots() -> None:
    """Defensive: if the resolver mis-classifies two slots as active
    (clock-edge race? overlapping windows?) the adapter keeps the
    first and downgrades the rest rather than crashing the
    at-most-one-active invariant."""
    adapter = WorkspaceRegionAdapter()
    region = _day_timeline_region()
    surface = adapter.build(
        region,
        {
            "day_timeline_slots": [
                {"slot_id": "p1", "label": "P1", "position": "active"},
                {"slot_id": "p2", "label": "P2", "position": "active"},
                {"slot_id": "p3", "label": "P3", "position": "active"},
            ],
        },
    )
    html = _render(surface)
    assert html.count('data-dz-position="active"') == 1


def test_day_timeline_skips_slots_with_missing_id() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _day_timeline_region()
    surface = adapter.build(
        region,
        {
            "day_timeline_slots": [
                {"slot_id": "p1", "label": "OK"},
                {"slot_id": "", "label": "Bad"},
                {"label": "Missing key"},
            ],
        },
    )
    html = _render(surface)
    assert 'data-slot-id="p1"' in html
    assert "Bad" not in html
    assert "Missing key" not in html


def test_day_timeline_drill_url_wraps_slot_in_anchor() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _day_timeline_region()
    surface = adapter.build(
        region,
        {
            "day_timeline_slots": [
                {"slot_id": "p1", "label": "P1", "drill_url": "/lessons/123"},
            ],
        },
    )
    html = _render(surface)
    assert 'href="/lessons/123"' in html


def test_day_timeline_passes_through_pre_rendered_body() -> None:
    """`body` is pre-rendered HTML from the data resolution layer;
    the adapter passes it through and the primitive renders it as-is
    (escape responsibility lives with whoever produced the body)."""
    adapter = WorkspaceRegionAdapter()
    region = _day_timeline_region()
    body_html = '<span class="lesson-card">Year 8 Maths — Room B12</span>'
    surface = adapter.build(
        region,
        {
            "day_timeline_slots": [
                {"slot_id": "p1", "label": "P1", "body": body_html},
            ],
        },
    )
    html = _render(surface)
    assert body_html in html


# ───────────────── TaskInbox (#1015, v0.67.8) ───────────────────


def _task_inbox_region(*, empty_state: str = "All caught up.") -> object:
    """Build a region object exposing a TaskInboxConfig — duck-typed."""
    from dazzle.core.ir.workspaces import TaskInboxConfig

    cfg = TaskInboxConfig(sources=[], empty_state=empty_state)

    class _Region:
        name = "today"
        title = None
        display = "task_inbox"
        empty_message = None

    r = _Region()
    r.task_inbox_config = cfg  # type: ignore[attr-defined]
    return r


def test_task_inbox_dispatches_to_builder() -> None:
    adapter = WorkspaceRegionAdapter()
    surface = adapter.build(_task_inbox_region(), {})
    assert isinstance(surface, Surface)
    html = _render(surface)
    assert 'class="dz-task-inbox-region"' in html


def test_task_inbox_uses_config_empty_state_when_region_empty() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _task_inbox_region(empty_state="Nothing to do.")
    surface = adapter.build(region, {})
    html = _render(surface)
    assert "Nothing to do." in html


def test_task_inbox_builds_items_with_urgency() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _task_inbox_region()
    items = [
        {
            "item_id": "i1",
            "icon": "register",
            "title": "Register 8X",
            "meta": "Period 1",
            "urgency": "due",
            "drill_url": "/r/i1",
        },
        {
            "item_id": "i2",
            "icon": "message",
            "title": "Reply",
            "urgency": "overdue",
        },
    ]
    surface = adapter.build(region, {"task_inbox_items": items})
    html = _render(surface)
    assert 'data-item-id="i1"' in html
    assert 'data-dz-urgency="due"' in html
    assert 'data-dz-urgency="overdue"' in html
    assert 'data-lucide="register"' in html  # unknown name -> client-hydration fallback
    assert 'href="/r/i1"' in html


def test_task_inbox_builds_summary_chips() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _task_inbox_region()
    chips = [
        {"chip_id": "c1", "count": 7, "label": "manuscripts ready", "drill_url": "/m"},
        {"chip_id": "c2", "count": 3, "label": "drafts in review"},
    ]
    surface = adapter.build(region, {"task_inbox_chips": chips})
    html = _render(surface)
    assert 'class="dz-task-inbox-chips"' in html
    assert ">7<" in html
    assert "manuscripts ready" in html
    assert 'href="/m"' in html


def test_task_inbox_skips_items_with_missing_id() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _task_inbox_region()
    items = [
        {"item_id": "i1", "icon": "x", "title": "ok"},
        {"item_id": "", "icon": "x", "title": "bad"},
    ]
    surface = adapter.build(region, {"task_inbox_items": items})
    html = _render(surface)
    assert 'data-item-id="i1"' in html
    assert "bad" not in html


def test_task_inbox_unknown_urgency_falls_through_to_later() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _task_inbox_region()
    surface = adapter.build(
        region,
        {"task_inbox_items": [{"item_id": "i", "icon": "x", "title": "t", "urgency": "weird"}]},
    )
    html = _render(surface)
    assert 'data-dz-urgency="later"' in html


def test_task_inbox_negative_chip_count_coerces_to_zero() -> None:
    """Defensive: a buggy resolver producing count=-1 would trip the
    primitive's invariant. The adapter clamps to 0."""
    adapter = WorkspaceRegionAdapter()
    region = _task_inbox_region()
    surface = adapter.build(
        region, {"task_inbox_chips": [{"chip_id": "c", "count": -5, "label": "x"}]}
    )
    html = _render(surface)
    assert ">0<" in html


def test_task_inbox_non_int_chip_count_coerces_to_zero() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _task_inbox_region()
    surface = adapter.build(
        region, {"task_inbox_chips": [{"chip_id": "c", "count": "??", "label": "x"}]}
    )
    html = _render(surface)
    assert ">0<" in html


# ───────────────── EntityCard (#1017, v0.67.8) ───────────────────


def _entity_card_region() -> object:
    """Build a region object exposing an EntityCardConfig — duck-typed."""
    from dazzle.core.ir.workspaces import EntityCardConfig

    cfg = EntityCardConfig(sections=[])

    class _Region:
        name = "card"
        title = None
        display = "entity_card"
        empty_message = None

    r = _Region()
    r.entity_card_config = cfg  # type: ignore[attr-defined]
    return r


def test_entity_card_dispatches_to_builder() -> None:
    adapter = WorkspaceRegionAdapter()
    surface = adapter.build(_entity_card_region(), {})
    assert isinstance(surface, Surface)
    html = _render(surface)
    assert 'class="dz-entity-card-region"' in html


def test_entity_card_renders_record_label_when_set() -> None:
    adapter = WorkspaceRegionAdapter()
    surface = adapter.build(
        _entity_card_region(),
        {
            "entity_card_record_label": "Alice Wong · Year 9",
            "entity_card_sections": [
                {"section_id": "s", "label": "Halo", "body": "<p>x</p>"},
            ],
        },
    )
    html = _render(surface)
    assert "Alice Wong" in html


def test_entity_card_omits_record_label_heading_when_empty() -> None:
    adapter = WorkspaceRegionAdapter()
    surface = adapter.build(
        _entity_card_region(),
        {"entity_card_sections": [{"section_id": "s", "label": "L"}]},
    )
    html = _render(surface)
    assert "dz-entity-card-heading" not in html


def test_entity_card_builds_sections_with_modes() -> None:
    adapter = WorkspaceRegionAdapter()
    sections_data = [
        {
            "section_id": "halo",
            "label": "Halo",
            "mode": "halo",
            "column": "main",
            "body": "<div>halo body</div>",
        },
        {
            "section_id": "flags",
            "label": "Flags",
            "mode": "flags",
            "column": "sidebar",
        },
        {
            "section_id": "marks",
            "label": "Marks",
            "mode": "mini_bars",
            "column": "main",
        },
    ]
    surface = adapter.build(_entity_card_region(), {"entity_card_sections": sections_data})
    html = _render(surface)
    assert 'data-section-id="halo"' in html
    assert 'data-dz-mode="flags"' in html
    assert 'data-dz-mode="mini_bars"' in html
    assert 'data-dz-column="sidebar"' in html


def test_entity_card_skips_omitted_sections() -> None:
    adapter = WorkspaceRegionAdapter()
    sections_data = [
        {"section_id": "shown", "label": "Shown"},
        {"section_id": "hidden", "label": "Hidden", "is_omitted": True},
    ]
    surface = adapter.build(_entity_card_region(), {"entity_card_sections": sections_data})
    html = _render(surface)
    assert 'data-section-id="shown"' in html
    assert 'data-section-id="hidden"' not in html


def test_entity_card_unknown_mode_falls_through_to_halo() -> None:
    adapter = WorkspaceRegionAdapter()
    surface = adapter.build(
        _entity_card_region(),
        {"entity_card_sections": [{"section_id": "s", "label": "L", "mode": "weird"}]},
    )
    html = _render(surface)
    assert 'data-dz-mode="halo"' in html


def test_entity_card_unknown_column_falls_through_to_main() -> None:
    adapter = WorkspaceRegionAdapter()
    surface = adapter.build(
        _entity_card_region(),
        {"entity_card_sections": [{"section_id": "s", "label": "L", "column": "weird"}]},
    )
    html = _render(surface)
    assert 'data-dz-column="main"' in html


def test_entity_card_skips_sections_with_missing_id() -> None:
    adapter = WorkspaceRegionAdapter()
    sections_data = [
        {"section_id": "ok", "label": "OK"},
        {"section_id": "", "label": "Bad"},
    ]
    surface = adapter.build(_entity_card_region(), {"entity_card_sections": sections_data})
    html = _render(surface)
    assert 'data-section-id="ok"' in html
    assert "Bad" not in html


# ───────────────── Cross-display parametrized families (#1530) ─────────────
# Three assertion-shape families collapsed from named per-display tests.
# Membership is deliberately conservative: config-driven displays
# (cohort_strip, day_timeline, task_inbox, entity_card) stay named above
# because their empty paths flow through builder functions — not the
# generic EmptyState arm — and some also pin chrome persistence
# (role="tablist"). Also kept named: metrics scope-denial (#1425 non-leak),
# the kanban either-of-three-outputs test, the radar <3-axes degrade test,
# the diagram legacy hardcoded-message test (v0.66.118 — empty_message is
# intentionally *ignored* there), profile_card degrade/default-message
# contracts, and any smoke test that pins structure (isinstance, viewBox,
# counts) rather than substrings.


# Family 1: empty data + region.empty_message → the message renders via
# the generic EmptyState arm. One row per display; assertion is exactly
# "message in rendered output".
_EMPTY_STATE_CASES: list[tuple[str, dict, str]] = [
    ("timeline", {}, "No events yet."),
    ("list", {"items": [], "columns": []}, "No users."),
    ("grid", {"items": []}, "Nothing here."),
    ("metrics", {}, "None yet."),
    ("bar_chart", {"buckets": []}, "None."),
    ("pivot_table", {"rows": [], "columns": ["x"]}, "No data."),
    ("tabbed_list", {}, "No tabs."),
    ("detail", {"item": None}, "No item."),
    ("box_plot", {"groups": []}, "No distribution."),
    ("bar_track", {"bar_track_rows": []}, "No tracks."),
    ("bullet", {"items": []}, "No bullets."),
    ("tree", {"items": []}, "Empty tree."),
    ("pipeline_steps", {"pipeline_stage_data": []}, "No steps."),
    ("action_grid", {"action_cards": []}, "No quick actions."),
    ("status_list", {"items": []}, "All clear."),
    ("funnel_chart", {"buckets": []}, "No funnel."),
    ("queue", {"items": []}, "Queue is empty."),
    ("progress", {"stage_counts": []}, "No progress."),
]


@pytest.mark.parametrize(
    ("display", "ctx", "message"),
    _EMPTY_STATE_CASES,
    ids=[case[0] for case in _EMPTY_STATE_CASES],
)
def test_empty_data_with_empty_message_renders_empty_state(
    display: str, ctx: dict, message: str
) -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(_FakeRegion("r", display=display, empty_message=message), ctx)
    assert message in _render(fragment)


# Family 2: alternative dict item shapes normalize to the same render as
# the primary tuple shape. Per-row rationale:
# - bar_chart: buckets as {label, value} or {key, count} dicts; labels
#   humanized via render_status_badge (v0.66.110) — "open" → "Open".
# - radar: axes as {axis, value} or {label, value} dicts.
# - box_plot: groups as {label, min, q1, median, q3, max} dicts.
# - line_chart (TimeSeries): points as {x, y} or {label, value} dicts.
# - diagram: edges as {from, to} (or {source, target}) dicts.
_ALT_DICT_SHAPE_CASES: list[tuple[str, dict, tuple[str, ...]]] = [
    (
        "bar_chart",
        {"buckets": [{"label": "open", "value": 5}, {"key": "closed", "count": 9}]},
        ("Open", "Closed"),
    ),
    (
        "radar",
        {
            "axes": [
                {"axis": "X", "value": 1},
                {"label": "Y", "value": 2},
                {"axis": "Z", "value": 3},
            ]
        },
        ("X", "Y", "Z"),
    ),
    (
        "box_plot",
        {"groups": [{"label": "g1", "min": 0, "q1": 1, "median": 2, "q3": 3, "max": 4}]},
        ("g1",),
    ),
    (
        "line_chart",
        {"points": [{"x": "Jan", "y": 10}, {"label": "Feb", "value": 20}]},
        ("Jan", "Feb"),
    ),
    (
        "diagram",
        {"nodes": ["A", "B"], "edges": [{"from": "A", "to": "B"}]},
        ("A", "B"),
    ),
]


@pytest.mark.parametrize(
    ("display", "ctx", "expected"),
    _ALT_DICT_SHAPE_CASES,
    ids=[case[0] for case in _ALT_DICT_SHAPE_CASES],
)
def test_alternative_dict_item_shape_normalizes_to_same_render(
    display: str, ctx: dict, expected: tuple[str, ...]
) -> None:
    adapter = WorkspaceRegionAdapter()
    html = _render(adapter.build(_FakeRegion("r", display=display), ctx))
    for substring in expected:
        assert substring in html


# Family 3: render smoke — each display emits its dz-* marker plus the
# item content (substring assertions only; structural assertions stay in
# named tests). Per-row rationale:
# - kanban: `dz-kanban` CSS hook so workspace layout CSS can target the
#   column structure; title + card content render.
# - radar: polar axes labels render inside dz-radar.
# - box_plot: quartile groups render inside dz-box-plot.
# - line_chart: v0.66.110 — legacy region wrapper class is
#   `dz-line-chart-region` (chrome stripping).
# - area_chart: v0.66.110 — wrapper is `dz-area-chart-region` (legacy
#   class scheme — was BEM `dz-timeseries--view-area`).
# - diagram: nodes + edges render as paired UL lists with the → arrow.
_RENDER_SMOKE_CASES: list[tuple[str, str | None, dict, tuple[str, ...]]] = [
    (
        "kanban",
        "Tasks",
        {
            "items": [{"id": "1", "title": "Buy milk", "status": "todo"}],
            "group_keys": ["todo", "doing", "done"],
            "group_by_field": "status",
        },
        ("dz-kanban", "Tasks", "Buy milk"),
    ),
    (
        "radar",
        None,
        {"axes": [("Python", 9), ("Go", 7), ("Rust", 5), ("JavaScript", 6)]},
        ("dz-radar", "Python", "Go", "Rust"),
    ),
    (
        "box_plot",
        None,
        {"groups": [("p50", 0, 1, 2, 3, 4), ("p99", 5, 6, 7, 8, 9)]},
        ("dz-box-plot", "p50", "p99"),
    ),
    (
        "line_chart",
        None,
        {"points": [("Jan", 5), ("Feb", 8), ("Mar", 12)]},
        ("dz-line-chart-region", "Jan", "Feb", "Mar"),
    ),
    (
        "area_chart",
        None,
        {"points": [("Q1", 100), ("Q2", 150)]},
        ("dz-area-chart-region",),
    ),
    (
        "diagram",
        None,
        {
            "nodes": ["Device", "Tester", "IssueReport"],
            "edges": [("Device", "Tester"), ("Device", "IssueReport")],
        },
        ("dz-diagram", "Device", "Tester", "IssueReport", "→"),
    ),
]


@pytest.mark.parametrize(
    ("display", "title", "ctx", "expected"),
    _RENDER_SMOKE_CASES,
    ids=[case[0] for case in _RENDER_SMOKE_CASES],
)
def test_display_renders_dz_marker_and_item_content(
    display: str, title: str | None, ctx: dict, expected: tuple[str, ...]
) -> None:
    adapter = WorkspaceRegionAdapter()
    html = _render(adapter.build(_FakeRegion("r", display=display, title=title), ctx))
    for substring in expected:
        assert substring in html
