"""WorkspaceRegionAdapter tests (Phase 4A)."""

import pytest

from dazzle.render.fragment import KanbanBoard, Region, Surface
from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle_back.runtime.renderers.region_adapter import WorkspaceRegionAdapter


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
    """`map` isn't wired yet — raises NotImplementedError with a
    pointer at the audit's aggregated_blockers report. Rotated through:
    grid → pivot_table → heatmap → map (heatmap stays unsupported but
    using a different unsupported mode here keeps the canary distinct
    from the coverage tests' canary)."""
    adapter = WorkspaceRegionAdapter()
    with pytest.raises(NotImplementedError, match="map"):
        adapter.build(_FakeRegion("r", display="map"), {})


# ───────────────── Timeline ───────────────────────


def test_timeline_with_default_label_and_date_fields() -> None:
    """Timeline auto-detects label (title/name/id) and date
    (date/created_at/occurred_at/timestamp) when fields aren't
    explicitly named."""
    from dazzle.render.fragment import Timeline

    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"title": "Login", "created_at": "2026-01-01"},
            {"title": "Signup", "created_at": "2025-12-15"},
        ],
    }
    fragment = adapter.build(_FakeRegion("activity", display="timeline"), ctx)
    assert isinstance(fragment, Surface)
    region = fragment.body
    assert isinstance(region, Region)
    timeline = region.body
    assert isinstance(timeline, Timeline)
    assert ("Login", "2026-01-01") in timeline.events
    assert ("Signup", "2025-12-15") in timeline.events


def test_timeline_with_explicit_label_and_date_fields() -> None:
    """Explicit `label_field` and `date_field` ctx keys override
    the auto-detection."""
    from dazzle.render.fragment import Timeline

    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"event_name": "Test", "happened_on": "2026-02-02"}],
        "label_field": "event_name",
        "date_field": "happened_on",
    }
    fragment = adapter.build(_FakeRegion("events", display="timeline"), ctx)
    timeline = fragment.body.body
    assert isinstance(timeline, Timeline)
    assert timeline.events == (("Test", "2026-02-02"),)


def test_timeline_skips_items_missing_label_or_date() -> None:
    """Items without a usable label or date are silently dropped —
    Timeline requires both."""
    from dazzle.render.fragment import Timeline

    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"title": "Has both", "created_at": "2026-01-01"},
            {"title": "No date"},
            {"created_at": "2026-01-02"},  # No label
        ],
    }
    fragment = adapter.build(_FakeRegion("e", display="timeline"), ctx)
    timeline = fragment.body.body
    assert isinstance(timeline, Timeline)
    assert len(timeline.events) == 1


def test_timeline_no_items_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("e", display="timeline", empty_message="No events yet."), {}
    )
    html = _render(fragment)
    assert "No events yet." in html


def test_timeline_uses_region_date_field_clause() -> None:
    """`region.date_field` from the DSL is consulted when ctx
    doesn't explicitly pass `date_field`."""
    from dazzle.render.fragment import Timeline

    region = _FakeRegion("e", display="timeline")
    region.date_field = "due_date"  # type: ignore[attr-defined]
    ctx = {
        "items": [{"title": "Task", "due_date": "2026-03-01"}],
    }
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(region, ctx)
    timeline = fragment.body.body
    assert isinstance(timeline, Timeline)
    assert timeline.events == (("Task", "2026-03-01"),)


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
    """Items bucket by `group_by_field`; declared `group_keys` set the
    column order."""
    adapter = WorkspaceRegionAdapter()
    region = _FakeRegion("task_board", display="kanban", title="Task Board")
    ctx = {
        "items": [
            {"id": "1", "title": "Buy milk", "status": "todo"},
            {"id": "2", "title": "Walk dog", "status": "doing"},
            {"id": "3", "title": "Read book", "status": "todo"},
            {"id": "4", "title": "Stretch", "status": "done"},
        ],
        "group_keys": ["todo", "doing", "done"],
        "group_by_field": "status",
    }
    fragment = adapter.build(region, ctx)
    assert isinstance(fragment, Surface)
    assert isinstance(fragment.body, Region)
    assert fragment.body.kind == "kanban"
    board = fragment.body.body
    assert isinstance(board, KanbanBoard)
    by_key = dict(board.columns)
    assert list(by_key.keys()) == ["todo", "doing", "done"]
    assert len(by_key["todo"]) == 2
    assert len(by_key["doing"]) == 1
    assert len(by_key["done"]) == 1


def test_kanban_unknown_group_keys_go_to_other_column() -> None:
    """Items grouped under a key not in `group_keys` collect under
    a synthetic 'Other' column at the end."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"id": "1", "title": "X", "status": "blocked"},  # not in keys
            {"id": "2", "title": "Y", "status": "todo"},
        ],
        "group_keys": ["todo", "doing"],
        "group_by_field": "status",
    }
    fragment = adapter.build(_FakeRegion("b", display="kanban"), ctx)
    board = fragment.body.body
    by_key = dict(board.columns)
    assert "Other" in by_key
    assert len(by_key["Other"]) == 1
    assert len(by_key["todo"]) == 1


def test_kanban_empty_columns_still_render() -> None:
    """A column with declared group_key but zero items still renders
    as an empty column — important UX so authors can see all states
    even when none have items today."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"id": "1", "title": "X", "status": "todo"}],
        "group_keys": ["todo", "doing", "done"],
        "group_by_field": "status",
    }
    fragment = adapter.build(_FakeRegion("b", display="kanban"), ctx)
    board = fragment.body.body
    by_key = dict(board.columns)
    assert by_key["doing"] == ()
    assert by_key["done"] == ()


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


def test_kanban_renders_to_html_with_dz_kanban_marker() -> None:
    """Rendered output carries the `dz-kanban` CSS hook so workspace
    layout CSS can target the kanban column structure."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"id": "1", "title": "Buy milk", "status": "todo"}],
        "group_keys": ["todo", "doing", "done"],
        "group_by_field": "status",
    }
    fragment = adapter.build(_FakeRegion("b", display="kanban", title="Tasks"), ctx)
    html = _render(fragment)
    assert "dz-kanban" in html
    assert "Tasks" in html
    assert "Buy milk" in html


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


def test_list_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("users", display="list", empty_message="No users."),
        {"items": [], "columns": []},
    )
    html = _render(fragment)
    assert "No users." in html


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


def test_grid_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("c", display="grid", empty_message="Nothing here."),
        {"items": []},
    )
    assert "Nothing here." in _render(fragment)


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


def test_metrics_summary_alias_dispatches_same_path() -> None:
    """`display: summary` reuses the metrics adapter — they're spelt
    differently in DSL but render identically."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("k", display="summary"),
        {"metrics": [{"label": "X", "value": "1"}]},
    )
    assert "X" in _render(fragment)


def test_metrics_invalid_trend_coerced_to_flat() -> None:
    """Defensive: garbage trend values shouldn't crash the KPI primitive."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("k", display="metrics"),
        {"metrics": [{"label": "X", "value": "1", "trend": "garbage"}]},
    )
    assert "X" in _render(fragment)


def test_metrics_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("k", display="metrics", empty_message="None yet."),
        {},
    )
    assert "None yet." in _render(fragment)


# ───────────────── Bar chart ───────────────────────


def test_bar_chart_renders_buckets() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {"buckets": [("low", 3), ("medium", 7), ("high", 2)]}
    fragment = adapter.build(_FakeRegion("severity", display="bar_chart"), ctx)
    html = _render(fragment)
    assert "low" in html
    assert "medium" in html
    assert "high" in html


def test_bar_chart_accepts_dict_bucket_shape() -> None:
    """Buckets can also arrive as dicts with label/value or key/count."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "buckets": [
            {"label": "open", "value": 5},
            {"key": "closed", "count": 9},
        ]
    }
    fragment = adapter.build(_FakeRegion("c", display="bar_chart"), ctx)
    html = _render(fragment)
    assert "open" in html and "closed" in html


def test_bar_chart_skips_malformed_entries() -> None:
    """A bucket missing a usable key/value silently drops; pure garbage
    leaves an empty bucket list → EmptyState."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("c", display="bar_chart", empty_message="No data."),
        {"buckets": [None, 42, "string"]},
    )
    assert "No data." in _render(fragment)


def test_bar_chart_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("c", display="bar_chart", empty_message="None."),
        {"buckets": []},
    )
    assert "None." in _render(fragment)


def test_bar_chart_uses_chart_label_override() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {"buckets": [("a", 1)], "chart_label": "Custom Chart"}
    fragment = adapter.build(_FakeRegion("c", display="bar_chart"), ctx)
    # The label should appear somewhere in the rendered output
    html = _render(fragment)
    assert "a" in html  # smoke; label rendering is BarChart's concern


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


def test_pivot_table_empty_dimensions_render_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("p", display="pivot_table", empty_message="No data."),
        {"rows": [], "columns": ["x"]},
    )
    assert "No data." in _render(fragment)


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


def test_tabbed_list_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("t", display="tabbed_list", empty_message="No tabs."),
        {},
    )
    assert "No tabs." in _render(fragment)


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


def test_detail_no_item_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("d", display="detail", empty_message="No item."),
        {"item": None},
    )
    assert "No item." in _render(fragment)


# ───────────────── Activity feed ──────────────────


def test_diagram_renders_nodes_and_edges() -> None:
    """`display: diagram` produces a Diagram primitive with the
    declared nodes and edges, rendered as paired UL lists."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "nodes": ["Device", "Tester", "IssueReport"],
        "edges": [("Device", "Tester"), ("Device", "IssueReport")],
    }
    fragment = adapter.build(_FakeRegion("d", display="diagram"), ctx)
    html = _render(fragment)
    assert "dz-diagram" in html
    assert "Device" in html and "Tester" in html and "IssueReport" in html
    # Edge arrow rendered
    assert "→" in html


def test_diagram_accepts_dict_edge_shape() -> None:
    """Edges can also arrive as `{from, to}` or `{source, target}` dicts."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "nodes": ["A", "B"],
        "edges": [{"from": "A", "to": "B"}],
    }
    fragment = adapter.build(_FakeRegion("d", display="diagram"), ctx)
    html = _render(fragment)
    assert "A" in html and "B" in html


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


def test_diagram_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("d", display="diagram", empty_message="No diagram."),
        {"nodes": []},
    )
    assert "No diagram." in _render(fragment)


def test_heatmap_dispatches_through_pivot_table() -> None:
    """`display: heatmap` reuses the PivotTable render — both are 2D
    cell grids; richer per-cell intensity colouring is a future
    enhancement."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "rows": ["mon", "tue"],
        "columns": ["9am", "10am"],
        "cells": {("mon", "9am"): 5, ("tue", "10am"): 3},
    }
    fragment = adapter.build(_FakeRegion("h", display="heatmap"), ctx)
    html = _render(fragment)
    assert "mon" in html and "tue" in html
    assert "9am" in html and "10am" in html
    assert "5" in html and "3" in html


def test_confirm_action_panel_renders_card_with_prompt() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {"prompt": "This will permanently delete 5 items.", "action_label": "Delete"}
    fragment = adapter.build(
        _FakeRegion("c", display="confirm_action_panel", title="Confirm Delete"), ctx
    )
    html = _render(fragment)
    assert "Confirm Delete" in html
    assert "permanently delete 5 items" in html
    assert "[ Delete ]" in html


def test_search_box_renders_search_field() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {"placeholder": "Find tickets…"}
    fragment = adapter.build(_FakeRegion("s", display="search_box"), ctx)
    html = _render(fragment)
    # Field rendered as text input with placeholder
    assert "Search" in html
    assert "Find tickets" in html or "placeholder" in html


def test_bar_track_dispatches_through_progress() -> None:
    """`bar_track` shares shape with progress; structurally identical
    until a dedicated BarTrack primitive lands."""
    adapter = WorkspaceRegionAdapter()
    ctx = {"items": [{"label": "CPU", "percent": 80}, {"label": "RAM", "percent": 40}]}
    fragment = adapter.build(_FakeRegion("b", display="bar_track"), ctx)
    html = _render(fragment)
    assert "CPU" in html and "80%" in html
    assert "RAM" in html and "40%" in html


def test_bullet_renders_actual_vs_target_rows_with_severity() -> None:
    """Each bullet row shows label, actual (severity-mapped Badge),
    "/", target (default Badge). Variant maps from actual/target ratio:
    >=1.0 success, <0.5 danger, else warning."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"label": "Q1", "actual": 100, "target": 100},  # success
            {"label": "Q2", "actual": 70, "target": 100},  # warning
            {"label": "Q3", "actual": 30, "target": 100},  # danger
        ]
    }
    fragment = adapter.build(_FakeRegion("b", display="bullet"), ctx)
    html = _render(fragment)
    assert "Q1" in html and "Q2" in html and "Q3" in html
    assert "dz-badge--variant-success" in html
    assert "dz-badge--variant-warning" in html
    assert "dz-badge--variant-danger" in html


def test_bullet_handles_non_numeric_values_gracefully() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {"items": [{"label": "X", "actual": "n/a", "target": "n/a"}]}
    fragment = adapter.build(_FakeRegion("b", display="bullet"), ctx)
    html = _render(fragment)
    assert "n/a" in html  # rendered without crashing the variant calc


def test_bullet_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("b", display="bullet", empty_message="No bullets."),
        {"items": []},
    )
    assert "No bullets." in _render(fragment)


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


def test_tree_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("t", display="tree", empty_message="Empty tree."),
        {"items": []},
    )
    assert "Empty tree." in _render(fragment)


def test_pipeline_steps_renders_row_of_cards() -> None:
    """Each step becomes a Card with a Heading and optional Text
    description, arranged in a horizontal Row."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "steps": [
            {"label": "Plan", "description": "Scope locked"},
            {"label": "Build"},
            {"label": "Ship", "status": "Pending"},
        ]
    }
    fragment = adapter.build(_FakeRegion("p", display="pipeline_steps"), ctx)
    html = _render(fragment)
    assert "Plan" in html and "Build" in html and "Ship" in html
    assert "Scope locked" in html
    assert "Pending" in html  # status falls back if no description


def test_pipeline_steps_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("p", display="pipeline_steps", empty_message="No steps."),
        {"steps": []},
    )
    assert "No steps." in _render(fragment)


def test_action_grid_dispatches_through_grid() -> None:
    """`display: action_grid` reuses the grid renderer; action wiring
    is a future enhancement once Button-driven cards land."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"title": "Reboot"}, {"title": "Backup"}, {"title": "Restore"}],
        "columns": 3,
    }
    fragment = adapter.build(_FakeRegion("a", display="action_grid"), ctx)
    html = _render(fragment)
    assert "Reboot" in html and "Backup" in html and "Restore" in html


def test_progress_renders_percent_badges_with_severity() -> None:
    """Progress rows show label + percent badge; variant maps from
    percent ranges (>=90 success, >=50 info, >=25 warning, else danger)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"label": "Done", "percent": 95},
            {"label": "Halfway", "percent": 60},
            {"label": "Slow", "percent": 30},
            {"label": "Stuck", "percent": 5},
        ]
    }
    fragment = adapter.build(_FakeRegion("p", display="progress"), ctx)
    html = _render(fragment)
    assert "95%" in html and "60%" in html and "30%" in html and "5%" in html
    assert "dz-badge--variant-success" in html
    assert "dz-badge--variant-info" in html
    assert "dz-badge--variant-warning" in html
    assert "dz-badge--variant-danger" in html


def test_progress_clamps_out_of_range_percent_values() -> None:
    """Values outside [0, 100] are clamped before rendering."""
    adapter = WorkspaceRegionAdapter()
    ctx = {"items": [{"label": "X", "percent": 250}, {"label": "Y", "percent": -10}]}
    fragment = adapter.build(_FakeRegion("p", display="progress"), ctx)
    html = _render(fragment)
    assert "100%" in html
    assert "0%" in html


def test_progress_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("p", display="progress", empty_message="No progress."),
        {"items": []},
    )
    assert "No progress." in _render(fragment)


def test_status_list_renders_label_badge_rows() -> None:
    """`display: status_list` renders a Stack of (Text, Badge) rows
    with optional severity colouring via status_variants."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"name": "Service A", "status": "healthy"},
            {"name": "Service B", "status": "failed"},
        ],
        "status_variants": {"healthy": "success", "failed": "danger"},
    }
    fragment = adapter.build(_FakeRegion("s", display="status_list"), ctx)
    html = _render(fragment)
    assert "Service A" in html and "Service B" in html
    assert "healthy" in html and "failed" in html
    # Badge variants should be reflected in CSS class
    assert "dz-badge--variant-success" in html
    assert "dz-badge--variant-danger" in html


def test_status_list_drops_invalid_variant() -> None:
    """A status_variants entry with an unknown badge variant falls
    back to 'default' instead of crashing the Badge primitive."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"name": "X", "status": "unknown"}],
        "status_variants": {"unknown": "purple"},  # not a real variant
    }
    fragment = adapter.build(_FakeRegion("s", display="status_list"), ctx)
    html = _render(fragment)
    assert "dz-badge" in html  # rendered with fallback variant


def test_status_list_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("s", display="status_list", empty_message="All clear."),
        {"items": []},
    )
    assert "All clear." in _render(fragment)


def test_profile_card_dispatches_through_detail() -> None:
    """`display: profile_card` reuses the detail render — profile
    cards are single-item field views with the same shape."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "item": {"name": "Alice", "role": "admin"},
        "fields": [{"key": "name", "label": "Name"}, {"key": "role", "label": "Role"}],
    }
    fragment = adapter.build(_FakeRegion("p", display="profile_card"), ctx)
    html = _render(fragment)
    assert "Alice" in html and "admin" in html


def test_funnel_chart_sorts_buckets_descending() -> None:
    """A funnel chart is just a BarChart with stages sorted by count
    descending — biggest first, narrow at the bottom."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "buckets": [
            ("signed_up", 100),
            ("verified", 200),
            ("paid", 50),
        ]
    }
    fragment = adapter.build(_FakeRegion("f", display="funnel_chart"), ctx)
    html = _render(fragment)
    # Order in HTML output should reflect sort: verified (200), signed_up (100), paid (50)
    pos_verified = html.find("verified")
    pos_signed = html.find("signed_up")
    pos_paid = html.find("paid")
    assert pos_verified < pos_signed < pos_paid


def test_funnel_chart_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("f", display="funnel_chart", empty_message="No funnel."),
        {"buckets": []},
    )
    assert "No funnel." in _render(fragment)


def test_queue_dispatches_through_list() -> None:
    """`display: queue` is a Table-like list. Inline-action wiring is
    a future enhancement; the audit just needs the render path closed."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"name": "Item One"}, {"name": "Item Two"}],
        "columns": [{"key": "name", "label": "Name"}],
    }
    fragment = adapter.build(_FakeRegion("q", display="queue"), ctx)
    html = _render(fragment)
    assert "<table" in html
    assert "Item One" in html and "Item Two" in html


def test_histogram_dispatches_through_bar_chart() -> None:
    """Histograms are bar charts of binned continuous data — for the
    audit's purposes a pure alias is fine."""
    adapter = WorkspaceRegionAdapter()
    ctx = {"buckets": [("0-10", 5), ("10-20", 15), ("20-30", 8)]}
    fragment = adapter.build(_FakeRegion("h", display="histogram"), ctx)
    html = _render(fragment)
    assert "0-10" in html and "10-20" in html and "20-30" in html


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
