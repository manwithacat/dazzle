"""Tests for data primitives — Table, KPI, BarChart, PivotTable, Timeline,
KanbanBoard, CalendarGrid."""

import pytest

from dazzle.render.fragment.primitives.data import (
    KPI,
    ActionCard,
    BarChart,
    BarTrack,
    BoxPlot,
    CalendarGrid,
    Diagram,
    KanbanBoard,
    MetricTile,
    PivotTable,
    ProfileCard,
    Radar,
    Table,
    Timeline,
    TimeSeries,
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


def test_diagram_requires_at_least_one_node() -> None:
    with pytest.raises(ValueError, match="at least one node"):
        Diagram(nodes=())


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
