"""Tests for data primitives — Table, KPI, BarChart, PivotTable, Timeline,
KanbanBoard, CalendarGrid."""

import pytest

from dazzle.render.fragment.htmx import URL
from dazzle.render.fragment.primitives.data import (
    KPI,
    ActionCard,
    BarChart,
    BarTrack,
    BoxPlot,
    CalendarGrid,
    ConfirmCheckItem,
    ConfirmGate,
    CsvExportButton,
    DateRangePicker,
    Diagram,
    FilterBar,
    FilterColumn,
    KanbanBoard,
    LazyTab,
    LazyTabPanel,
    MetricTile,
    PivotTable,
    ProfileCard,
    Radar,
    ReferenceBand,
    ReferenceLine,
    SearchBox,
    SortHeader,
    StageBar,
    Table,
    Timeline,
    TimeSeries,
    TimeSeriesSeries,
)

# === Table ===


def test_table_columns_and_rows() -> None:
    t = Table(
        columns=("title", "status"),
        rows=(("Buy milk", "open"), ("Walk dog", "done")),
    )
    assert len(t.rows) == 2


def test_table_rejects_no_columns() -> None:
    with pytest.raises(ValueError, match="at least one column"):
        Table(columns=(), rows=(("x",),))


def test_table_row_arity_must_match_columns() -> None:
    with pytest.raises(ValueError, match="row arity"):
        Table(columns=("a", "b"), rows=(("only_one",),))


# === KPI ===


def test_kpi_basic() -> None:
    k = KPI(label="Revenue", value="$42k", trend="up")
    assert k.trend == "up"


def test_kpi_invalid_trend() -> None:
    with pytest.raises(ValueError, match="invalid trend"):
        KPI(label="x", value="0", trend="sideways")  # type: ignore[arg-type]


# === BarChart / PivotTable ===


def test_bar_chart_buckets() -> None:
    b = BarChart(label="Tasks by status", buckets=(("open", 3), ("done", 7)))
    assert len(b.buckets) == 2


def test_bar_chart_rejects_no_buckets() -> None:
    with pytest.raises(ValueError, match="at least one bucket"):
        BarChart(label="x", buckets=())


def test_pivot_table_dimensions() -> None:
    p = PivotTable(
        label="System x severity",
        rows=("auth", "billing"),
        columns=("low", "high"),
        cells={
            ("auth", "low"): 1,
            ("auth", "high"): 2,
            ("billing", "low"): 0,
            ("billing", "high"): 5,
        },
    )
    assert p.cells[("auth", "high")] == 2


# === Timeline / Kanban / Calendar ===


def test_timeline_events() -> None:
    t = Timeline(events=(("created", "2026-05-05"),))
    assert len(t.events) == 1


def test_kanban_columns() -> None:
    k = KanbanBoard(columns=(("open", ()), ("done", ())))
    assert len(k.columns) == 2


def test_calendar_view_default() -> None:
    c = CalendarGrid()
    assert c.view == "month"


def test_pivot_table_cells_immutable_after_construction() -> None:
    """frozen=True should mean cells is immutable too — wrapped in MappingProxyType."""
    p = PivotTable(label="x", rows=("r",), columns=("c",), cells={("r", "c"): 0})
    with pytest.raises(TypeError):
        p.cells[("r", "c")] = 99  # type: ignore[index]


# === Diagram ===


def test_diagram_requires_nodes_or_mermaid_source() -> None:
    """v0.66.118: Diagram now accepts EITHER `nodes` OR `mermaid_source`.
    The empty case (neither set) still rejects."""
    with pytest.raises(ValueError, match="nodes OR a mermaid_source"):
        Diagram(nodes=())


def test_diagram_accepts_mermaid_source_without_nodes() -> None:
    """A Mermaid-source-only Diagram is valid; the renderer emits the
    `<pre class="mermaid">` + CDN script form instead of node/edge lists."""
    d = Diagram(mermaid_source="erDiagram\n    A {\n        str x\n    }")
    assert d.nodes == ()
    assert d.mermaid_source.startswith("erDiagram")


def test_diagram_rejects_edge_with_unknown_from() -> None:
    with pytest.raises(ValueError, match="edge from"):
        Diagram(nodes=("A",), edges=(("Z", "A"),))


def test_diagram_rejects_edge_with_unknown_to() -> None:
    with pytest.raises(ValueError, match="edge to"):
        Diagram(nodes=("A",), edges=(("A", "Z"),))


def test_diagram_accepts_self_loop() -> None:
    """An edge from a node to itself is structurally valid."""
    d = Diagram(nodes=("A",), edges=(("A", "A"),))
    assert d.edges == (("A", "A"),)


def test_diagram_no_edges_is_valid() -> None:
    """Pure node-only diagrams are allowed (e.g. orphans-only graph)."""
    d = Diagram(nodes=("A", "B"))
    assert d.edges == ()


# === TimeSeries ===


def test_timeseries_requires_at_least_one_point() -> None:
    with pytest.raises(ValueError, match="at least one point"):
        TimeSeries(label="x", points=())


def test_timeseries_rejects_invalid_view() -> None:
    with pytest.raises(ValueError, match="invalid view"):
        TimeSeries(label="x", points=(("a", 1.0),), view="pie")  # type: ignore[arg-type]


def test_timeseries_default_view_is_line() -> None:
    t = TimeSeries(label="x", points=(("a", 1.0),))
    assert t.view == "line"


def test_timeseries_accepts_all_three_views() -> None:
    for view in ("line", "area", "sparkline"):
        t = TimeSeries(label="x", points=(("a", 1.0),), view=view)  # type: ignore[arg-type]
        assert t.view == view


def test_timeseries_accepts_multi_series() -> None:
    t = TimeSeries(
        label="x",
        view="area",
        series=(
            TimeSeriesSeries(name="high", points=(("W1", 2.0), ("W2", 3.0))),
            TimeSeriesSeries(name="low", points=(("W1", 1.0), ("W2", 4.0))),
        ),
    )
    assert len(t.series) == 2
    assert t.series[0].name == "high"
    assert t.points == ()


def test_timeseries_with_series_does_not_require_points() -> None:
    # Series-only construction is valid — points stays empty.
    t = TimeSeries(label="x", series=(TimeSeriesSeries(name="a", points=(("a", 1.0),)),))
    assert t.series[0].points == (("a", 1.0),)


def test_timeseries_requires_points_or_series() -> None:
    with pytest.raises(ValueError, match="at least one point"):
        TimeSeries(label="x", points=(), series=())


def test_timeseries_series_requires_at_least_one_point() -> None:
    with pytest.raises(ValueError, match="at least one point"):
        TimeSeriesSeries(name="empty", points=())


# === Radar ===


def test_radar_requires_at_least_one_axis() -> None:
    with pytest.raises(ValueError, match="at least one axis"):
        Radar(label="x", axes=())


def test_radar_requires_at_least_three_axes_to_be_visually_a_radar() -> None:
    """Two axes collapses to a line — reject at construction time."""
    with pytest.raises(ValueError, match="at least 3 axes"):
        Radar(label="x", axes=(("a", 1.0), ("b", 2.0)))


def test_radar_three_axes_minimum() -> None:
    r = Radar(label="x", axes=(("a", 1.0), ("b", 2.0), ("c", 3.0)))
    assert len(r.axes) == 3


# === BoxPlot ===


def test_box_plot_requires_at_least_one_group() -> None:
    with pytest.raises(ValueError, match="at least one group"):
        BoxPlot(label="x", groups=())


def test_box_plot_rejects_non_monotonic_quartiles() -> None:
    with pytest.raises(ValueError, match="quartiles not monotonic"):
        BoxPlot(label="x", groups=(("g1", 5.0, 4.0, 3.0, 2.0, 1.0),))


def test_box_plot_accepts_equal_quartiles() -> None:
    """Degenerate distributions (all values equal) are still valid —
    the constraint is `<=`, not strict `<`."""
    b = BoxPlot(label="x", groups=(("g1", 0.0, 0.0, 0.0, 0.0, 0.0),))
    assert b.groups[0] == ("g1", 0.0, 0.0, 0.0, 0.0, 0.0)


def test_box_plot_rejects_wrong_arity_group() -> None:
    with pytest.raises(ValueError, match="arity mismatch"):
        BoxPlot(label="x", groups=(("g1", 1.0, 2.0, 3.0),))  # type: ignore[arg-type]


# === ActionCard ===


def test_action_card_requires_label() -> None:
    with pytest.raises(ValueError, match="non-empty label"):
        ActionCard(label="")


def test_action_card_rejects_unknown_tone() -> None:
    with pytest.raises(ValueError, match="invalid tone"):
        ActionCard(label="X", tone="purple")  # type: ignore[arg-type]


def test_action_card_count_zero_distinct_from_none() -> None:
    """`count = 0` should render a badge with "0"; `count = None` is no badge."""
    a = ActionCard(label="Zero", count=0)
    b = ActionCard(label="Empty")
    assert a.count == 0 and b.count is None


def test_action_card_static_when_url_empty() -> None:
    a = ActionCard(label="X", url="")
    assert a.url == ""


def test_action_card_all_tones_accepted() -> None:
    for tone in ("neutral", "positive", "warning", "destructive", "accent"):
        c = ActionCard(label="X", tone=tone)  # type: ignore[arg-type]
        assert c.tone == tone


# === ProfileCard ===


def test_profile_card_requires_at_least_one_identity_element() -> None:
    """The card needs primary, avatar_url, or initials — anything else
    would render an empty shell. The adapter degrades to EmptyState
    rather than letting an invalid card through."""
    with pytest.raises(ValueError, match="at least one of primary"):
        ProfileCard()
    with pytest.raises(ValueError, match="at least one of primary"):
        ProfileCard(secondary="Just a meta line, no name")


def test_profile_card_primary_alone_is_valid() -> None:
    p = ProfileCard(primary="Alice")
    assert p.primary == "Alice"


def test_profile_card_avatar_alone_is_valid() -> None:
    p = ProfileCard(avatar_url="/avatars/x.png")
    assert p.avatar_url == "/avatars/x.png"


def test_profile_card_initials_alone_is_valid() -> None:
    p = ProfileCard(initials="AB")
    assert p.initials == "AB"


def test_profile_card_holds_stats_and_facts_immutably() -> None:
    """`stats` is tuple[tuple[str, str], ...] and `facts` is
    tuple[str, ...] so the dataclass stays frozen."""
    p = ProfileCard(
        primary="X",
        stats=(("Cases", "5"), ("Open", "2")),
        facts=("Lead", "Mentor"),
    )
    assert p.stats == (("Cases", "5"), ("Open", "2"))
    assert p.facts == ("Lead", "Mentor")


# === MetricTile ===


def test_metric_tile_requires_label() -> None:
    with pytest.raises(ValueError, match="non-empty label"):
        MetricTile(label="", value="0")


def test_metric_tile_rejects_unknown_tone() -> None:
    with pytest.raises(ValueError, match="invalid tone"):
        MetricTile(label="X", value="0", tone="purple")  # type: ignore[arg-type]


def test_metric_tile_rejects_unknown_delta_direction() -> None:
    with pytest.raises(ValueError, match="invalid delta_direction"):
        MetricTile(label="X", value="0", delta_direction="sideways")  # type: ignore[arg-type]


def test_metric_tile_rejects_unknown_delta_sentiment() -> None:
    with pytest.raises(ValueError, match="invalid delta_sentiment"):
        MetricTile(label="X", value="0", delta_sentiment="ambiguous")  # type: ignore[arg-type]


def test_metric_tile_minimal_no_delta() -> None:
    m = MetricTile(label="Total", value="42")
    assert m.label == "Total"
    assert m.value == "42"
    assert m.tone == ""
    assert m.delta_direction == ""


def test_metric_tile_full_delta_block() -> None:
    m = MetricTile(
        label="Sales",
        value="1,234",
        tone="warning",
        delta_direction="up",
        delta_sentiment="positive_up",
        delta_value="42",
        delta_pct=3.5,
        delta_period_label="last month",
    )
    assert m.delta_pct == 3.5
    assert m.delta_period_label == "last month"


# === BarTrack ===


def test_bar_track_requires_at_least_one_row() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        BarTrack(rows=(), max_value=100.0)


def test_bar_track_rejects_wrong_arity_row() -> None:
    with pytest.raises(ValueError, match="arity mismatch"):
        BarTrack(rows=(("X", 1.0, "1"),), max_value=100.0)  # type: ignore[arg-type]


def test_bar_track_rejects_fill_pct_above_100() -> None:
    with pytest.raises(ValueError, match=r"fill_pct=200"):
        BarTrack(rows=(("X", 1.0, "1", 200.0),), max_value=100.0)


def test_bar_track_rejects_negative_fill_pct() -> None:
    with pytest.raises(ValueError, match=r"fill_pct=-5"):
        BarTrack(rows=(("X", 1.0, "1", -5.0),), max_value=100.0)


def test_bar_track_accepts_zero_and_hundred_fill_pct() -> None:
    """Boundaries are inclusive — 0 and 100 are valid fill values."""
    b = BarTrack(
        rows=(("Empty", 0.0, "0", 0.0), ("Full", 100.0, "100", 100.0)),
        max_value=100.0,
    )
    assert len(b.rows) == 2


# === StageBar ===


def test_stage_bar_requires_at_least_one_stage() -> None:
    with pytest.raises(ValueError, match="at least one stage"):
        StageBar(stages=())


def test_stage_bar_rejects_complete_pct_above_100() -> None:
    with pytest.raises(ValueError, match=r"complete_pct=150"):
        StageBar(stages=(("X", 1, False),), complete_pct=150)


def test_stage_bar_rejects_negative_complete_pct() -> None:
    with pytest.raises(ValueError, match=r"complete_pct=-1"):
        StageBar(stages=(("X", 1, False),), complete_pct=-1)


def test_stage_bar_minimal() -> None:
    s = StageBar(stages=(("Backlog", 5, False),))
    assert s.complete_pct == 0.0
    assert s.total == 0


def test_stage_bar_full_progress_state() -> None:
    s = StageBar(
        stages=(("Done", 10, True),),
        complete_pct=100.0,
        complete_count=10,
        total=10,
    )
    assert s.complete_pct == 100.0


# === ReferenceLine / ReferenceBand ===


def test_reference_line_default_style() -> None:
    r = ReferenceLine(value=100.0, label="Target")
    assert r.style == "solid"


def test_reference_line_rejects_unknown_style() -> None:
    with pytest.raises(ValueError, match="invalid style"):
        ReferenceLine(value=1, style="wavy")  # type: ignore[arg-type]


def test_reference_band_rejects_inverted_range() -> None:
    with pytest.raises(ValueError, match="from_value=10"):
        ReferenceBand(from_value=10, to_value=5)


def test_reference_band_accepts_zero_width_range() -> None:
    """from == to is structurally valid (point band)."""
    b = ReferenceBand(from_value=5, to_value=5, label="threshold")
    assert b.from_value == b.to_value == 5


def test_reference_band_rejects_unknown_color() -> None:
    with pytest.raises(ValueError, match="invalid color"):
        ReferenceBand(from_value=0, to_value=1, color="magenta")  # type: ignore[arg-type]


def test_time_series_carries_optional_references() -> None:
    """Phase 4B.1.b: TimeSeries gained `reference_lines` and
    `reference_bands` tuple fields (default empty)."""
    ts = TimeSeries(
        label="x",
        points=(("a", 1.0),),
        reference_lines=(ReferenceLine(value=10, label="ref"),),
        reference_bands=(ReferenceBand(from_value=0, to_value=5, label="low", color="muted"),),
    )
    assert len(ts.reference_lines) == 1
    assert len(ts.reference_bands) == 1


def test_time_series_default_references_empty() -> None:
    ts = TimeSeries(label="x", points=(("a", 1.0),))
    assert ts.reference_lines == ()
    assert ts.reference_bands == ()


def test_bar_chart_carries_optional_references() -> None:
    """Phase 4B.1.b extension — BarChart gained reference_lines + bands."""
    bc = BarChart(
        label="x",
        buckets=(("a", 1),),
        reference_lines=(ReferenceLine(value=5, label="ref"),),
        reference_bands=(ReferenceBand(from_value=0, to_value=2, label="zone"),),
    )
    assert len(bc.reference_lines) == 1
    assert len(bc.reference_bands) == 1


def test_bar_track_carries_optional_references() -> None:
    bt = BarTrack(
        rows=(("X", 1.0, "1", 50.0),),
        max_value=100.0,
        reference_lines=(ReferenceLine(value=80, label="critical"),),
    )
    assert len(bt.reference_lines) == 1
    assert bt.reference_bands == ()


def test_box_plot_carries_optional_references() -> None:
    bp = BoxPlot(
        label="x",
        groups=(("g", 0.0, 1.0, 2.0, 3.0, 4.0),),
        reference_bands=(ReferenceBand(from_value=1, to_value=3, label="iqr"),),
    )
    assert len(bp.reference_bands) == 1


def test_chart_primitives_default_references_empty() -> None:
    """Backward compat — pre-Phase-4B.1.b primitives without references
    keep the empty-tuple default."""
    bc = BarChart(label="x", buckets=(("a", 1),))
    bt = BarTrack(rows=(("X", 1.0, "1", 50.0),), max_value=100.0)
    bp = BoxPlot(label="x", groups=(("g", 0.0, 1.0, 2.0, 3.0, 4.0),))
    assert bc.reference_lines == () and bc.reference_bands == ()
    assert bt.reference_lines == () and bt.reference_bands == ()
    assert bp.reference_lines == () and bp.reference_bands == ()


# === LazyTab / LazyTabPanel ===


def test_lazy_tab_requires_key_and_label() -> None:
    with pytest.raises(ValueError, match="non-empty key"):
        LazyTab(key="", label="X", endpoint=URL("/x"))
    with pytest.raises(ValueError, match="non-empty label"):
        LazyTab(key="x", label="", endpoint=URL("/x"))


def test_lazy_tab_panel_requires_at_least_one_tab() -> None:
    with pytest.raises(ValueError, match="at least one tab"):
        LazyTabPanel(region_name="r", tabs=())


def test_lazy_tab_panel_requires_region_name() -> None:
    with pytest.raises(ValueError, match="non-empty region_name"):
        LazyTabPanel(
            region_name="",
            tabs=(LazyTab(key="x", label="X", endpoint=URL("/x")),),
        )


def test_lazy_tab_panel_rejects_duplicate_keys() -> None:
    """DOM ids would collide if two tabs share a key — strict invariant."""
    dup = (
        LazyTab(key="x", label="A", endpoint=URL("/a")),
        LazyTab(key="x", label="B", endpoint=URL("/b")),
    )
    with pytest.raises(ValueError, match="must be unique"):
        LazyTabPanel(region_name="r", tabs=dup)


def test_lazy_tab_panel_default_eager_is_false() -> None:
    """First tab convention is set by the renderer (always eager-loads
    panel index 0). The `eager` flag explicitly overrides for non-first
    tabs that must also fire on load."""
    t = LazyTab(key="x", label="X", endpoint=URL("/x"))
    assert t.eager is False


# === SearchBox ===


def test_search_box_requires_non_empty_name() -> None:
    """`name` becomes part of the results-panel DOM id; empty name
    would produce a colliding/missing id."""
    with pytest.raises(ValueError, match="non-empty name"):
        SearchBox(name="", fts_endpoint=URL("/_dazzle/fts/X"))


def test_search_box_default_strings() -> None:
    s = SearchBox(name="x", fts_endpoint=URL("/_dazzle/fts/X"))
    assert s.placeholder == "Search…"
    assert s.coaching_message == "Type to search"
    assert s.label == ""


# === ConfirmCheckItem / ConfirmGate ===


def test_confirm_check_item_requires_title() -> None:
    with pytest.raises(ValueError, match="non-empty title"):
        ConfirmCheckItem(title="")


def test_confirm_check_item_default_required_is_false() -> None:
    item = ConfirmCheckItem(title="X")
    assert item.required is False
    assert item.caption == ""


def test_confirm_gate_minimal() -> None:
    """Empty ConfirmGate is valid — defaults to off state, no
    confirmations, no urls. Renders to a minimal `<div>` with the
    bare wrapper."""
    g = ConfirmGate()
    assert g.state == "off"
    assert g.confirmations == ()
    assert g.audit_enabled is False


def test_confirm_gate_holds_confirmations_immutably() -> None:
    g = ConfirmGate(
        state="off",
        confirmations=(
            ConfirmCheckItem(title="A", required=True),
            ConfirmCheckItem(title="B"),
        ),
    )
    assert len(g.confirmations) == 2
    assert g.confirmations[0].required is True
    assert g.confirmations[1].required is False


def test_confirm_gate_default_copy_strings() -> None:
    g = ConfirmGate()
    assert g.primary_label == "Confirm and enable"
    assert g.secondary_label == "Save as draft"
    assert g.revoke_label == "Revoke"
    assert g.live_title == "Currently live."


# === FilterColumn / FilterBar ===


def test_filter_column_requires_key() -> None:
    with pytest.raises(ValueError, match="non-empty key"):
        FilterColumn(key="", label="X", options=())


def test_filter_column_default_selected_empty() -> None:
    c = FilterColumn(key="k", label="L", options=(("a", "A"),))
    assert c.selected == ""


def test_filter_bar_requires_region_name() -> None:
    with pytest.raises(ValueError, match="non-empty region_name"):
        FilterBar(
            endpoint=URL("/x"),
            region_name="",
            columns=(FilterColumn(key="k", label="L", options=()),),
        )


def test_filter_bar_requires_at_least_one_column() -> None:
    with pytest.raises(ValueError, match="at least one column"):
        FilterBar(endpoint=URL("/x"), region_name="r", columns=())


def test_filter_bar_rejects_duplicate_column_keys() -> None:
    """Form field names must be unique — `name=filter_<key>` collides
    when two columns share a key."""
    with pytest.raises(ValueError, match="must be unique"):
        FilterBar(
            endpoint=URL("/x"),
            region_name="r",
            columns=(
                FilterColumn(key="k", label="A", options=()),
                FilterColumn(key="k", label="B", options=()),
            ),
        )


# === SortHeader ===


def test_sort_header_requires_column_key() -> None:
    with pytest.raises(ValueError, match="non-empty column_key"):
        SortHeader(label="L", column_key="", endpoint=URL("/x"), region_name="r")


def test_sort_header_requires_region_name() -> None:
    with pytest.raises(ValueError, match="non-empty region_name"):
        SortHeader(label="L", column_key="k", endpoint=URL("/x"), region_name="")


def test_sort_header_rejects_invalid_direction() -> None:
    with pytest.raises(ValueError, match="invalid current_direction"):
        SortHeader(
            label="L",
            column_key="k",
            endpoint=URL("/x"),
            region_name="r",
            current_direction="random",  # type: ignore[arg-type]
        )


def test_sort_header_default_direction_is_asc() -> None:
    s = SortHeader(label="L", column_key="k", endpoint=URL("/x"), region_name="r")
    assert s.current_direction == "asc"
    assert s.current_sort == ""


# === CsvExportButton ===


def test_csv_export_button_requires_filename() -> None:
    with pytest.raises(ValueError, match="non-empty filename"):
        CsvExportButton(endpoint=URL("/x"), filename="")


def test_csv_export_button_defaults() -> None:
    c = CsvExportButton(endpoint=URL("/api/x"))
    assert c.filename == "export.csv"
    assert c.label == "Export CSV"


# === DateRangePicker ===


def test_date_range_picker_requires_region_name() -> None:
    with pytest.raises(ValueError, match="non-empty region_name"):
        DateRangePicker(endpoint=URL("/x"), region_name="")


def test_date_range_picker_defaults_empty() -> None:
    d = DateRangePicker(endpoint=URL("/x"), region_name="r")
    assert d.date_from == ""
    assert d.date_to == ""
