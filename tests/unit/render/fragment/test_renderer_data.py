"""Renderer support for Table/KPI/BarChart/PivotTable/Timeline/KanbanBoard/CalendarGrid."""

from dazzle.render.fragment import (
    KPI,
    BarChart,
    CalendarGrid,
    KanbanBoard,
    PivotTable,
    Table,
    Text,
    Timeline,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_table() -> None:
    r = FragmentRenderer()
    t = Table(
        columns=("title", "status"),
        rows=(("Buy milk", "open"), ("Walk dog", "done")),
    )
    out = r.render(t)
    assert "<table" in out
    assert "Buy milk" in out
    assert "Walk dog" in out
    assert out.count("<tr") >= 3  # 1 header + 2 body rows
    assert "dz-table" in out


def test_render_table_escapes_cells() -> None:
    r = FragmentRenderer()
    t = Table(columns=("name",), rows=(("<script>",),))
    out = r.render(t)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_kpi() -> None:
    r = FragmentRenderer()
    out = r.render(KPI(label="Revenue", value="$42k", trend="up", delta="+12%"))
    assert "Revenue" in out
    assert "$42k" in out
    assert "dz-kpi--trend-up" in out


def test_render_bar_chart() -> None:
    r = FragmentRenderer()
    out = r.render(BarChart(label="By status", buckets=(("open", 3), ("done", 7))))
    assert "open" in out
    assert "3" in out


def test_render_bar_chart_emits_legacy_track_and_fill_structure() -> None:
    """Phase 4B.1.c — bar chart structure matches the legacy
    `bar_chart.html` template (single-dash classes, track/fill divs,
    width-percent fill, summary line)."""
    r = FragmentRenderer()
    out = r.render(BarChart(label="By status", buckets=(("open", 3), ("done", 9))))
    assert 'class="dz-bar-chart-region"' in out
    assert 'class="dz-bar-chart-bars"' in out
    assert out.count('class="dz-bar-chart-row"') == 2
    assert 'class="dz-bar-chart-track"' in out
    # 3/9 = 33%, 9/9 = 100%
    assert 'style="width: 33%"' in out
    assert 'style="width: 100%"' in out
    # Summary line: total = 12
    assert 'class="dz-bar-chart-summary">12 total</p>' in out
    # aria-label preserves the chart label for screen readers
    assert 'aria-label="By status"' in out


def test_render_bar_chart_handles_zero_max_value() -> None:
    """All-zero buckets should not divide-by-zero — fills go to 0%."""
    r = FragmentRenderer()
    out = r.render(BarChart(label="x", buckets=(("a", 0), ("b", 0))))
    assert 'style="width: 0%"' in out
    assert "0 total" in out


def test_render_pivot_table() -> None:
    r = FragmentRenderer()
    p = PivotTable(
        label="System x severity",
        rows=("auth",),
        columns=("low", "high"),
        cells={("auth", "low"): 1, ("auth", "high"): 2},
    )
    out = r.render(p)
    assert "<table" in out
    assert "auth" in out


def test_render_timeline() -> None:
    r = FragmentRenderer()
    out = r.render(Timeline(events=(("created", "2026-05-05"), ("updated", "2026-05-06"))))
    assert "created" in out
    assert "2026-05-05" in out


def test_render_kanban_board() -> None:
    r = FragmentRenderer()
    k = KanbanBoard(columns=(("open", (Text("a"), Text("b"))), ("done", ())))
    out = r.render(k)
    assert "dz-kanban" in out
    assert out.count("dz-kanban__column") == 2


def test_render_calendar_view_class() -> None:
    r = FragmentRenderer()
    out = r.render(CalendarGrid(view="week"))
    assert "dz-calendar--view-week" in out
