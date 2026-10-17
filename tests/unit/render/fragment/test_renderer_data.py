"""Renderer support for Table/KPI/BarChart/PivotTable/Timeline/KanbanBoard/CalendarGrid."""

import pytest

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


@pytest.mark.parametrize(
    ("fragment", "present", "absent", "counts"),
    [
        pytest.param(
            Table(columns=("title", "status"), rows=(("Buy milk", "open"), ("Walk dog", "done"))),
            # HM list-region table (#1799) — never the `.dz-table` shell class.
            ('<table class="dz-list-table">', "Buy milk", "Walk dog"),
            ('class="dz-table"',),
            {"<tr": 3},  # 1 header + 2 body rows
            id="table",
        ),
        pytest.param(
            Table(columns=("name",), rows=(("<script>",),)),
            ("&lt;script&gt;",),
            ("<script>",),
            {},
            id="table-escapes-cells",
        ),
        pytest.param(
            KPI(label="Revenue", value="$42k", trend="up", delta="+12%"),
            # HM metric-tile skin + KPI dual-lock root (#1799).
            (
                '<div class="dz-metric-tile" data-dz-kpi>',
                '<div class="dz-metric-label">Revenue</div>',
                '<div class="dz-metric-value">$42k</div>',
                'data-dz-delta-tone="positive" data-dz-delta-direction="up"',
                '<span class="dz-metric-delta-value">+12%</span>',
            ),
            ("data-dz-metric-key",),
            {},
            id="kpi",
        ),
        # v0.66.110: legacy bar_chart.html bucketed_metrics structure —
        # single-dash classes, track/fill width-percent, labels humanized via
        # render_status_badge, no summary line (items+group_by branch only).
        pytest.param(
            BarChart(label="By status", buckets=(("open", 3), ("done", 9))),
            (
                'class="dz-bar-chart-region"',
                'class="dz-bar-chart-bars"',
                'class="dz-bar-chart-track"',
                'style="width: 33%"',
                'style="width: 100%"',
                ">Open<",
                ">Done<",
            ),
            ("dz-bar-chart-summary",),
            {'class="dz-bar-chart-row"': 2},
            id="bar-chart-legacy-track-and-fill",
        ),
        # All-zero buckets must not divide by zero.
        pytest.param(
            BarChart(label="x", buckets=(("a", 0), ("b", 0))),
            ('style="width: 0%"',),
            (),
            {},
            id="bar-chart-zero-max-value",
        ),
        pytest.param(
            PivotTable(
                label="System x severity",
                rows=("auth",),
                columns=("low", "high"),
                cells={("auth", "low"): 1, ("auth", "high"): 2},
            ),
            ('<table class="dz-pivot-grid" data-dz-pivot-table>', "auth", "low", "high"),
            (),
            {'<td class="is-measure">': 2},
            id="pivot-table",
        ),
        pytest.param(
            Timeline(events=(("created", "2026-05-05"), ("updated", "2026-05-06"))),
            ("created", "2026-05-05", "updated"),
            (),
            {},
            id="timeline",
        ),
        pytest.param(
            KanbanBoard(columns=(("open", (Text("a"), Text("b"))), ("done", ()))),
            # HM kanban skin; never the rearrange controller's opt-in (#1799).
            ('<div class="dz-kanban-board" data-dz-kanban>',),
            ("data-dz-kanban-board",),
            {'class="dz-kanban-column"': 2, 'class="dz-kanban-stack"': 2},
            id="kanban-board",
        ),
        pytest.param(
            CalendarGrid(view="week"),
            ("dz-calendar--view-week",),
            (),
            {},
            id="calendar-view-class",
        ),
    ],
)
def test_renders(
    fragment: object,
    present: tuple[str, ...],
    absent: tuple[str, ...],
    counts: dict[str, int],
) -> None:
    out = FragmentRenderer().render(fragment)
    assert [s for s in present if s not in out] == []
    assert [s for s in absent if s in out] == []
    assert {s: out.count(s) for s in counts} == counts
