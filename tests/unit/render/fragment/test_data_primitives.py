"""Tests for data primitives — Table, KPI, BarChart, PivotTable, Timeline,
KanbanBoard, CalendarGrid."""

from collections.abc import Callable

import pytest

from dazzle.render.fragment.htmx import URL
from dazzle.render.fragment.primitives.data import (
    KPI,
    BarChart,
    BarTrack,
    CalendarGrid,
    ConfirmCheckItem,
    ConfirmGate,
    CsvExportButton,
    DateRangePicker,
    Diagram,
    FilterBar,
    FilterColumn,
    LazyTab,
    LazyTabPanel,
    MetricTile,
    Pagination,
    PivotTable,
    Radar,
    ReferenceBand,
    ReferenceLine,
    SearchBox,
    SortHeader,
    Table,
    TimeSeries,
    TimeSeriesSeries,
)

# === Guard-clause families (TS-003 parametrize-collapse) ===
# Three shared contracts, one parametrized test each. Every row preserves
# the original pytest.raises match string; ids name primitive.field.


@pytest.mark.parametrize(
    ("ctor", "match"),
    [
        pytest.param(
            lambda: MetricTile(label="", value="0"),
            "non-empty label",
            id="metric_tile.label",
        ),
        pytest.param(
            lambda: LazyTab(key="", label="X", endpoint=URL("/x")),
            "non-empty key",
            id="lazy_tab.key",
        ),
        pytest.param(
            lambda: LazyTab(key="x", label="", endpoint=URL("/x")),
            "non-empty label",
            id="lazy_tab.label",
        ),
        pytest.param(
            lambda: LazyTabPanel(
                region_name="",
                tabs=(LazyTab(key="x", label="X", endpoint=URL("/x")),),
            ),
            "non-empty region_name",
            id="lazy_tab_panel.region_name",
        ),
        pytest.param(
            # `name` becomes part of the results-panel DOM id; empty name
            # would produce a colliding/missing id.
            lambda: SearchBox(name="", fts_endpoint=URL("/_dazzle/fts/X")),
            "non-empty name",
            id="fts_search_input.name",
        ),
        pytest.param(
            lambda: ConfirmCheckItem(title=""),
            "non-empty title",
            id="confirm_check_item.title",
        ),
        pytest.param(
            lambda: FilterColumn(key="", label="X", options=()),
            "non-empty key",
            id="filter_column.key",
        ),
        pytest.param(
            lambda: FilterBar(
                endpoint=URL("/x"),
                region_name="",
                columns=(FilterColumn(key="k", label="L", options=()),),
            ),
            "non-empty region_name",
            id="filter_bar.region_name",
        ),
        pytest.param(
            lambda: SortHeader(label="L", column_key="", endpoint=URL("/x"), region_name="r"),
            "non-empty column_key",
            id="sort_header.column_key",
        ),
        pytest.param(
            lambda: SortHeader(label="L", column_key="k", endpoint=URL("/x"), region_name=""),
            "non-empty region_name",
            id="sort_header.region_name",
        ),
        pytest.param(
            lambda: CsvExportButton(endpoint=URL("/x"), filename=""),
            "non-empty filename",
            id="csv_export_button.filename",
        ),
        pytest.param(
            lambda: DateRangePicker(endpoint=URL("/x"), region_name=""),
            "non-empty region_name",
            id="date_range_picker.region_name",
        ),
    ],
)
def test_rejects_empty_required_field(ctor: Callable[[], object], match: str) -> None:
    """Required string fields reject the empty string at construction time."""
    with pytest.raises(ValueError, match=match):
        ctor()


@pytest.mark.parametrize(
    ("ctor", "match"),
    [
        pytest.param(
            lambda: Table(columns=(), rows=(("x",),)),
            "at least one column",
            id="table.columns",
        ),
        pytest.param(
            lambda: BarChart(label="x", buckets=()),
            "at least one bucket",
            id="bar_chart.buckets",
        ),
        pytest.param(
            lambda: TimeSeries(label="x", points=()),
            "at least one point",
            id="time_series.points",
        ),
        pytest.param(
            lambda: TimeSeries(label="x", points=(), series=()),
            "at least one point",
            id="time_series.points_or_series",
        ),
        pytest.param(
            lambda: TimeSeriesSeries(name="empty", points=()),
            "at least one point",
            id="time_series_series.points",
        ),
        pytest.param(
            lambda: Radar(label="x", axes=()),
            "at least one axis",
            id="radar.axes",
        ),
        pytest.param(
            lambda: BarTrack(rows=(), max_value=100.0),
            "at least one row",
            id="bar_track.rows",
        ),
        pytest.param(
            lambda: LazyTabPanel(region_name="r", tabs=()),
            "at least one tab",
            id="lazy_tab_panel.tabs",
        ),
        pytest.param(
            lambda: FilterBar(endpoint=URL("/x"), region_name="r", columns=()),
            "at least one column",
            id="filter_bar.columns",
        ),
    ],
)
def test_rejects_empty_collection(ctor: Callable[[], object], match: str) -> None:
    """Collection-bearing primitives reject an empty collection at construction time."""
    with pytest.raises(ValueError, match=match):
        ctor()


@pytest.mark.parametrize(
    ("ctor", "match"),
    [
        pytest.param(
            lambda: KPI(label="x", value="0", trend="sideways"),  # type: ignore[arg-type]
            "invalid trend",
            id="kpi.trend",
        ),
        pytest.param(
            lambda: TimeSeries(label="x", points=(("a", 1.0),), view="pie"),  # type: ignore[arg-type]
            "invalid view",
            id="time_series.view",
        ),
        pytest.param(
            lambda: MetricTile(label="X", value="0", tone="purple"),  # type: ignore[arg-type]
            "invalid tone",
            id="metric_tile.tone",
        ),
        pytest.param(
            lambda: MetricTile(label="X", value="0", delta_direction="sideways"),  # type: ignore[arg-type]
            "invalid delta_direction",
            id="metric_tile.delta_direction",
        ),
        pytest.param(
            lambda: MetricTile(label="X", value="0", delta_sentiment="ambiguous"),  # type: ignore[arg-type]
            "invalid delta_sentiment",
            id="metric_tile.delta_sentiment",
        ),
        pytest.param(
            lambda: ReferenceLine(value=1, style="wavy"),  # type: ignore[arg-type]
            "invalid style",
            id="reference_line.style",
        ),
        pytest.param(
            lambda: ReferenceBand(from_value=0, to_value=1, color="magenta"),  # type: ignore[arg-type]
            "invalid color",
            id="reference_band.color",
        ),
        pytest.param(
            lambda: SortHeader(
                label="L",
                column_key="k",
                endpoint=URL("/x"),
                region_name="r",
                current_direction="random",  # type: ignore[arg-type]
            ),
            "invalid current_direction",
            id="sort_header.current_direction",
        ),
    ],
)
def test_rejects_invalid_enum_value(ctor: Callable[[], object], match: str) -> None:
    """Enum-constrained fields reject values outside their literal set."""
    with pytest.raises(ValueError, match=match):
        ctor()


@pytest.mark.parametrize(
    ("ctor", "match"),
    [
        pytest.param(
            lambda: Table(columns=("a", "b"), rows=(("only_one",),)),
            "row arity",
            id="table.row_arity",
        ),
        # v0.66.118: Diagram takes nodes OR mermaid_source; neither still rejects.
        pytest.param(lambda: Diagram(nodes=()), "nodes OR a mermaid_source", id="diagram.empty"),
        pytest.param(
            lambda: Diagram(nodes=("A",), edges=(("Z", "A"),)),
            "edge from",
            id="diagram.edge_unknown_from",
        ),
        pytest.param(
            lambda: Diagram(nodes=("A",), edges=(("A", "Z"),)),
            "edge to",
            id="diagram.edge_unknown_to",
        ),
        # Two axes collapse to a line — not visually a radar.
        pytest.param(
            lambda: Radar(label="x", axes=(("a", 1.0), ("b", 2.0))),
            "at least 3 axes",
            id="radar.two_axes",
        ),
        pytest.param(
            lambda: BarTrack(rows=(("X", 1.0, "1"),), max_value=100.0),  # type: ignore[arg-type]
            "arity mismatch",
            id="bar_track.row_arity",
        ),
        pytest.param(
            lambda: BarTrack(rows=(("X", 1.0, "1", 200.0),), max_value=100.0),
            r"fill_pct=200",
            id="bar_track.fill_pct_above_100",
        ),
        pytest.param(
            lambda: BarTrack(rows=(("X", 1.0, "1", -5.0),), max_value=100.0),
            r"fill_pct=-5",
            id="bar_track.fill_pct_negative",
        ),
        pytest.param(
            lambda: ReferenceBand(from_value=10, to_value=5),
            "from_value=10",
            id="reference_band.inverted_range",
        ),
        # DOM ids would collide if two tabs share a key.
        pytest.param(
            lambda: LazyTabPanel(
                region_name="r",
                tabs=(
                    LazyTab(key="x", label="A", endpoint=URL("/a")),
                    LazyTab(key="x", label="B", endpoint=URL("/b")),
                ),
            ),
            "must be unique",
            id="lazy_tab_panel.duplicate_keys",
        ),
        # `name=filter_<key>` form fields collide when two columns share a key.
        pytest.param(
            lambda: FilterBar(
                endpoint=URL("/x"),
                region_name="r",
                columns=(
                    FilterColumn(key="k", label="A", options=()),
                    FilterColumn(key="k", label="B", options=()),
                ),
            ),
            "must be unique",
            id="filter_bar.duplicate_column_keys",
        ),
    ],
)
def test_rejects_structural_violation(ctor: Callable[[], object], match: str) -> None:
    """Cross-field structural invariants are enforced at construction time."""
    with pytest.raises(ValueError, match=match):
        ctor()


@pytest.mark.parametrize(
    "ctor",
    [
        # Boundary cases on the valid side of the invariants above.
        pytest.param(lambda: Diagram(nodes=("A",), edges=(("A", "A"),)), id="diagram.self_loop"),
        pytest.param(lambda: Diagram(nodes=("A", "B")), id="diagram.nodes_without_edges"),
        pytest.param(
            lambda: Diagram(mermaid_source="erDiagram\n    A {\n        str x\n    }"),
            id="diagram.mermaid_source_without_nodes",
        ),
        pytest.param(
            lambda: Radar(label="x", axes=(("a", 1.0), ("b", 2.0), ("c", 3.0))),
            id="radar.three_axes",
        ),
        pytest.param(
            lambda: BarTrack(
                rows=(("Empty", 0.0, "0", 0.0), ("Full", 100.0, "100", 100.0)),
                max_value=100.0,
            ),
            id="bar_track.fill_pct_0_and_100_inclusive",
        ),
        pytest.param(
            lambda: ReferenceBand(from_value=5, to_value=5, label="threshold"),
            id="reference_band.zero_width",
        ),
        *(
            pytest.param(
                lambda view=view: TimeSeries(label="x", points=(("a", 1.0),), view=view),
                id=f"time_series.view_{view}",
            )
            for view in ("line", "area", "sparkline")
        ),
        pytest.param(
            lambda: TimeSeries(
                label="x",
                view="area",
                series=(
                    TimeSeriesSeries(name="high", points=(("W1", 2.0), ("W2", 3.0))),
                    TimeSeriesSeries(name="low", points=(("W1", 1.0), ("W2", 4.0))),
                ),
            ),
            id="time_series.series_without_points",
        ),
    ],
)
def test_accepts_boundary_construction(ctor: Callable[[], object]) -> None:
    """The valid edge of each structural invariant constructs without raising."""
    ctor()


def test_pivot_table_cells_immutable_after_construction() -> None:
    """frozen=True should mean cells is immutable too — wrapped in MappingProxyType."""
    p = PivotTable(label="x", rows=("r",), columns=("c",), cells={("r", "c"): 0})
    with pytest.raises(TypeError):
        p.cells[("r", "c")] = 99  # type: ignore[index]


_TEMPORAL_EMPTY = {"include_closed": "", "as_of": ""}


@pytest.mark.parametrize(
    ("ctor", "expected"),
    [
        pytest.param(CalendarGrid, {"view": "month"}, id="calendar_grid"),
        pytest.param(
            lambda: TimeSeries(label="x", points=(("a", 1.0),)),
            {"view": "line", "reference_lines": (), "reference_bands": ()},
            id="time_series",
        ),
        pytest.param(
            lambda: BarChart(label="x", buckets=(("a", 1),)),
            {"reference_lines": (), "reference_bands": ()},
            id="bar_chart",
        ),
        pytest.param(
            lambda: BarTrack(rows=(("X", 1.0, "1", 50.0),), max_value=100.0),
            {"reference_lines": (), "reference_bands": ()},
            id="bar_track",
        ),
        pytest.param(
            lambda: MetricTile(label="Total", value="42"),
            {"tone": "", "delta_direction": ""},
            id="metric_tile",
        ),
        pytest.param(
            lambda: ReferenceLine(value=100.0, label="Target"),
            {"style": "solid"},
            id="reference_line",
        ),
        # The renderer eager-loads tab 0; `eager` only overrides non-first tabs.
        pytest.param(
            lambda: LazyTab(key="x", label="X", endpoint=URL("/x")),
            {"eager": False},
            id="lazy_tab",
        ),
        pytest.param(
            lambda: SearchBox(name="x", fts_endpoint=URL("/_dazzle/fts/X")),
            {"placeholder": "Search…", "coaching_message": "Type to search", "label": ""},
            id="fts_search_input",
        ),
        pytest.param(
            lambda: ConfirmCheckItem(title="X"),
            {"required": False, "caption": ""},
            id="confirm_check_item",
        ),
        pytest.param(
            ConfirmGate,
            {
                "state": "off",
                "confirmations": (),
                "audit_enabled": False,
                "primary_label": "Confirm and enable",
                "secondary_label": "Save as draft",
                "revoke_label": "Revoke",
                "live_title": "Currently live.",
            },
            id="confirm_gate",
        ),
        pytest.param(
            lambda: FilterColumn(key="k", label="L", options=(("a", "A"),)),
            {"selected": ""},
            id="filter_column",
        ),
        pytest.param(
            lambda: FilterBar(
                endpoint=URL("/x"),
                region_name="r",
                columns=(FilterColumn(key="k", label="L", options=()),),
            ),
            _TEMPORAL_EMPTY,
            id="filter_bar",
        ),
        pytest.param(
            lambda: SortHeader(label="L", column_key="k", endpoint=URL("/x"), region_name="r"),
            {"current_direction": "asc", "current_sort": "", **_TEMPORAL_EMPTY},
            id="sort_header",
        ),
        pytest.param(
            lambda: CsvExportButton(endpoint=URL("/api/x")),
            {"filename": "export.csv", "label": "Export CSV", **_TEMPORAL_EMPTY},
            id="csv_export_button",
        ),
        pytest.param(
            lambda: Pagination(
                region_name="t", endpoint=URL("/api/x"), total=100, page=1, page_size=10
            ),
            {"extra_query": "", **_TEMPORAL_EMPTY},
            id="pagination",
        ),
        pytest.param(
            lambda: DateRangePicker(endpoint=URL("/x"), region_name="r"),
            {"date_from": "", "date_to": "", **_TEMPORAL_EMPTY},
            id="date_range_picker",
        ),
    ],
)
def test_defaults(ctor: Callable[[], object], expected: dict[str, object]) -> None:
    """Optional fields default to the values the renderers rely on."""
    obj = ctor()
    assert {key: getattr(obj, key) for key in expected} == expected
