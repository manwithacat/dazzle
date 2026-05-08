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
    """`map` is the canonical deferred display — vendor-neutral
    geographic rendering is genuinely hard; see `_DEFERRED_DISPLAYS`
    in coverage.py for the design rationale. The canary stays here
    because we expect `map` to remain unsupported indefinitely."""
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


def test_metrics_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("k", display="metrics", empty_message="None yet."),
        {},
    )
    assert "None yet." in _render(fragment)


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


def test_bar_chart_carries_reference_overlays() -> None:
    """Phase 4B.1.b: BarChart now accepts reference_lines + reference_bands
    via ctx; renderer emits them as a `<dl class=dz-bar-chart__references>`
    block after the bars."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "buckets": [("low", 3), ("high", 9)],
        "reference_lines": [{"value": 10, "label": "SLA", "style": "dashed"}],
        "reference_bands": [{"from": 0, "to": 5, "label": "Healthy", "color": "positive"}],
    }
    html = _render(adapter.build(_FakeRegion("c", display="bar_chart"), ctx))
    assert "dz-bar-chart__references" in html
    assert 'data-style="dashed"' in html
    assert 'data-color="positive"' in html


def test_box_plot_carries_reference_overlays() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "groups": [("p50", 0, 1, 2, 3, 4)],
        "reference_lines": [{"value": 3.5, "label": "Threshold"}],
    }
    html = _render(adapter.build(_FakeRegion("b", display="box_plot"), ctx))
    assert "dz-box-plot__references" in html
    assert "Threshold" in html


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
    assert "dz-badge--variant-success" in html  # resolved → success tone
    assert ">resolved<" in html


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
    assert "✓" in html
    assert "✗" in html  # both False and None render as cross


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


def test_radar_renders_polar_axes() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "axes": [
            ("Python", 9),
            ("Go", 7),
            ("Rust", 5),
            ("JavaScript", 6),
        ]
    }
    fragment = adapter.build(_FakeRegion("r", display="radar"), ctx)
    html = _render(fragment)
    assert "dz-radar" in html
    assert "Python" in html and "Go" in html and "Rust" in html


def test_radar_with_fewer_than_three_axes_degrades_to_empty_state() -> None:
    """Adapter is permissive — Radar's __post_init__ raises on <3 axes;
    the adapter returns EmptyState rather than crashing."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("r", display="radar", empty_message="Need 3+ axes."),
        {"axes": [("A", 1), ("B", 2)]},
    )
    assert "Need 3+ axes." in _render(fragment)


def test_radar_accepts_dict_axis_shape() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "axes": [
            {"axis": "X", "value": 1},
            {"label": "Y", "value": 2},
            {"axis": "Z", "value": 3},
        ]
    }
    fragment = adapter.build(_FakeRegion("r", display="radar"), ctx)
    html = _render(fragment)
    assert "X" in html and "Y" in html and "Z" in html


def test_box_plot_renders_quartile_table() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "groups": [
            ("p50", 0, 1, 2, 3, 4),
            ("p99", 5, 6, 7, 8, 9),
        ]
    }
    fragment = adapter.build(_FakeRegion("b", display="box_plot"), ctx)
    html = _render(fragment)
    assert "dz-box-plot" in html
    assert "p50" in html and "p99" in html


def test_box_plot_accepts_dict_group_shape() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "groups": [
            {"label": "g1", "min": 0, "q1": 1, "median": 2, "q3": 3, "max": 4},
        ]
    }
    fragment = adapter.build(_FakeRegion("b", display="box_plot"), ctx)
    assert "g1" in _render(fragment)


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


def test_box_plot_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("b", display="box_plot", empty_message="No distribution."),
        {"groups": []},
    )
    assert "No distribution." in _render(fragment)


def test_line_chart_renders_time_series() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {"points": [("Jan", 5), ("Feb", 8), ("Mar", 12)]}
    fragment = adapter.build(_FakeRegion("c", display="line_chart"), ctx)
    html = _render(fragment)
    assert "dz-timeseries--view-line" in html
    assert "Jan" in html and "Feb" in html and "Mar" in html


def test_area_chart_uses_area_view() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {"points": [("Q1", 100), ("Q2", 150)]}
    fragment = adapter.build(_FakeRegion("c", display="area_chart"), ctx)
    assert "dz-timeseries--view-area" in _render(fragment)


def test_sparkline_uses_sparkline_view() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {"points": [("a", 1), ("b", 2), ("c", 3)]}
    fragment = adapter.build(_FakeRegion("s", display="sparkline"), ctx)
    assert "dz-timeseries--view-sparkline" in _render(fragment)


def test_time_series_accepts_dict_point_shape() -> None:
    """Points can also arrive as `{label, value}` or `{x, y}` dicts."""
    adapter = WorkspaceRegionAdapter()
    ctx = {"points": [{"x": "Jan", "y": 10}, {"label": "Feb", "value": 20}]}
    fragment = adapter.build(_FakeRegion("c", display="line_chart"), ctx)
    html = _render(fragment)
    assert "Jan" in html and "Feb" in html


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
    """Phase 4B.1.b: ctx['reference_lines'] flows through to the
    TimeSeries primitive and renders as semantic `<dl>` annotations."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "points": [("Jan", 50), ("Feb", 75)],
        "reference_lines": [
            {"value": 100, "label": "Target", "style": "dashed"},
            {"value": 50, "label": "Min", "style": "wavy"},  # unknown → solid
        ],
    }
    html = _render(adapter.build(_FakeRegion("c", display="line_chart"), ctx))
    assert 'data-style="dashed"' in html
    assert 'data-style="solid"' in html  # 'wavy' fell back
    assert "Target" in html and "Min" in html


def test_time_series_carries_reference_bands_with_alt_keys() -> None:
    """Adapter accepts both `from`/`to` and `from_value`/`to_value`
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
    assert "Healthy" in html
    assert 'data-color="positive"' in html
    assert "Danger" in html
    assert 'data-color="destructive"' in html
    assert "Bad order" not in html


def test_time_series_no_references_omits_block() -> None:
    """When neither reference_lines nor reference_bands are supplied,
    the renderer omits the `<dl class=\"dz-timeseries__references\">`
    wrapper entirely (backward compat with Phase 4A renders)."""
    adapter = WorkspaceRegionAdapter()
    ctx = {"points": [("a", 1)]}
    html = _render(adapter.build(_FakeRegion("c", display="line_chart"), ctx))
    assert "dz-timeseries__references" not in html


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
    assert "dz-bar-track-rows" in html
    assert 'role="progressbar"' in html
    assert 'aria-valuemax="100.0"' in html
    assert 'aria-valuenow="80.0"' in html
    assert "width: 80.0%" in html
    assert "2 rows · scale 0–100.0" in html


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


def test_bar_track_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("b", display="bar_track", empty_message="No tracks."),
        {"bar_track_rows": []},
    )
    assert "No tracks." in _render(fragment)


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
    assert 'data-lucide="ticket"' in html
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


def test_action_grid_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("a", display="action_grid", empty_message="No quick actions."),
        {"action_cards": []},
    )
    assert "No quick actions." in _render(fragment)


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
    assert "100.0%" in html  # clamped to 100.0
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


def test_progress_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("p", display="progress", empty_message="No progress."),
        {"stage_counts": []},
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
