"""Tests for data primitives — Table, KPI, BarChart, PivotTable, Timeline,
KanbanBoard, CalendarGrid."""

import pytest

from dazzle.render.fragment.primitives.data import (
    KPI,
    BarChart,
    BoxPlot,
    CalendarGrid,
    Diagram,
    KanbanBoard,
    PivotTable,
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
