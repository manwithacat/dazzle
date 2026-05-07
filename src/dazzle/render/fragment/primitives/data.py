"""Data primitives — Table, KPI, BarChart, PivotTable, Timeline, KanbanBoard,
CalendarGrid.

These are display-only primitives that render structured data. They do not
construct queries themselves — they accept already-aggregated data shaped
to match the IR's aggregate result. The IR-to-Fragment binding lives in the
renderer's surface-mode adapters (added in Plan 2).

Most invariants here concentrate around shape mismatches: a Table's row
arity must match its column count; a PivotTable's cells must reference
declared rows and columns; etc.
"""

import types
import typing
from dataclasses import dataclass, field
from typing import Literal

_TRENDS = ("up", "down", "flat")
_CALENDAR_VIEWS = ("day", "week", "month")
_TIMESERIES_VIEWS = ("line", "area", "sparkline")


@dataclass(frozen=True, slots=True)
class Table:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        if not self.columns:
            raise ValueError("Table requires at least one column")
        for i, row in enumerate(self.rows):
            if len(row) != len(self.columns):
                raise ValueError(
                    f"row arity mismatch at index {i}: row has {len(row)} cells, "
                    f"columns has {len(self.columns)}"
                )


@dataclass(frozen=True, slots=True)
class KPI:
    label: str
    value: str
    trend: Literal["up", "down", "flat"] = "flat"
    delta: str = ""

    def __post_init__(self) -> None:
        if self.trend not in _TRENDS:
            raise ValueError(f"invalid trend {self.trend!r}")


@dataclass(frozen=True, slots=True)
class BarChart:
    label: str
    buckets: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not self.buckets:
            raise ValueError("BarChart requires at least one bucket")


@dataclass(frozen=True, slots=True)
class PivotTable:
    label: str
    rows: tuple[str, ...]
    columns: tuple[str, ...]
    cells: typing.Mapping[tuple[str, str], int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("PivotTable requires at least one row dimension")
        if not self.columns:
            raise ValueError("PivotTable requires at least one column dimension")
        for (r, c), _val in self.cells.items():
            if r not in self.rows:
                raise ValueError(f"cell row {r!r} not in declared rows {self.rows}")
            if c not in self.columns:
                raise ValueError(f"cell column {c!r} not in declared columns {self.columns}")
        # Wrap in a read-only proxy so callers can't mutate after construction.
        # Use object.__setattr__ to bypass frozen=True for this one assignment.
        object.__setattr__(self, "cells", types.MappingProxyType(dict(self.cells)))


@dataclass(frozen=True, slots=True)
class Timeline:
    events: tuple[tuple[str, str], ...]  # (label, iso-date)


@dataclass(frozen=True, slots=True)
class KanbanBoard:
    columns: tuple[tuple[str, tuple[object, ...]], ...]  # (column_key, items)

    def __post_init__(self) -> None:
        if not self.columns:
            raise ValueError("KanbanBoard requires at least one column")


@dataclass(frozen=True, slots=True)
class CalendarGrid:
    view: Literal["day", "week", "month"] = "month"
    events: tuple[tuple[str, str], ...] = ()  # (label, iso-date)

    def __post_init__(self) -> None:
        if self.view not in _CALENDAR_VIEWS:
            raise ValueError(f"invalid view {self.view!r}")


@dataclass(frozen=True, slots=True)
class Radar:
    """Polar/radar profile shape — value per named axis.

    Each `axes` entry is `(axis_label, value)`. The shape is used to
    visualise multi-dimensional comparisons where every dimension uses
    the same scale (e.g. a skill-set radar, a feature-coverage radar).
    """

    label: str
    axes: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not self.axes:
            raise ValueError("Radar requires at least one axis")
        if len(self.axes) < 3:
            raise ValueError(
                f"Radar requires at least 3 axes (got {len(self.axes)}); "
                f"fewer collapses to a line and is not visually a radar"
            )


@dataclass(frozen=True, slots=True)
class BoxPlot:
    """Per-group quartile distribution — min, q1, median, q3, max.

    Each `groups` entry is `(group_label, min, q1, median, q3, max)`.
    Strict invariant: `min <= q1 <= median <= q3 <= max` per group, so
    callers can't pass a malformed quartile spread.
    """

    label: str
    groups: tuple[tuple[str, float, float, float, float, float], ...]

    def __post_init__(self) -> None:
        if not self.groups:
            raise ValueError("BoxPlot requires at least one group")
        for i, group in enumerate(self.groups):
            if len(group) != 6:
                raise ValueError(
                    f"BoxPlot group {i} arity mismatch: "
                    f"expected (label, min, q1, median, q3, max), got {group!r}"
                )
            _label, mn, q1, med, q3, mx = group
            if not (mn <= q1 <= med <= q3 <= mx):
                raise ValueError(
                    f"BoxPlot group {i} ({_label!r}) quartiles not monotonic: "
                    f"min={mn}, q1={q1}, median={med}, q3={q3}, max={mx}"
                )


@dataclass(frozen=True, slots=True)
class TimeSeries:
    """Sequential numeric data plotted over a label axis.

    One primitive covers `line_chart`, `area_chart`, and `sparkline` —
    they differ only in chrome (axis labels, fill, size). The `view`
    discriminator selects the rendering style.

    `points` is a sequence of (label, value) pairs. The label is
    rendered as-is (typically an iso-date string or a bucket name);
    values are floats so callers can pass ratios as well as counts.
    """

    label: str
    points: tuple[tuple[str, float], ...]
    view: Literal["line", "area", "sparkline"] = "line"

    def __post_init__(self) -> None:
        if self.view not in _TIMESERIES_VIEWS:
            raise ValueError(f"invalid view {self.view!r}")
        if not self.points:
            raise ValueError("TimeSeries requires at least one point")


@dataclass(frozen=True, slots=True)
class Diagram:
    """Node-and-edge graph (e.g. an entity-relationship diagram).

    The primitive captures structure only: a list of named nodes and
    directed edges between them. Layout is the renderer's concern;
    Phase 4A renders nodes as labelled boxes and edges as `from → to`
    rows. A future iteration can produce SVG or wire a JS layout
    engine without changing the IR shape.
    """

    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ValueError("Diagram requires at least one node")
        node_set = set(self.nodes)
        for f, t in self.edges:
            if f not in node_set:
                raise ValueError(f"edge from {f!r} not in declared nodes")
            if t not in node_set:
                raise ValueError(f"edge to {t!r} not in declared nodes")
