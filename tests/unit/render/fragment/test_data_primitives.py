"""Tests for data primitives — Table, KPI, BarChart, PivotTable, Timeline,
KanbanBoard, CalendarGrid."""

import pytest

from dazzle.render.fragment.primitives.data import (
    KPI,
    BarChart,
    CalendarGrid,
    KanbanBoard,
    PivotTable,
    Table,
    Timeline,
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
