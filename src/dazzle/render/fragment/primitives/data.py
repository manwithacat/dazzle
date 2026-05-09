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

from dazzle.render.fragment.htmx import URL

_TRENDS = ("up", "down", "flat")
_CALENDAR_VIEWS = ("day", "week", "month")
_TIMESERIES_VIEWS = ("line", "area", "sparkline")
_REFERENCE_LINE_STYLES = ("solid", "dashed", "dotted")
_REFERENCE_BAND_COLORS = ("target", "positive", "warning", "destructive", "muted")


# ─── Reference overlay data primitives (used by chart primitives) ────


@dataclass(frozen=True, slots=True)
class ReferenceLine:
    """Horizontal annotation on a chart axis at `value` (e.g. a target,
    SLA threshold, or grade boundary).

    Not a Fragment union member — held inside chart primitives like
    `TimeSeries`, `BarChart`, `BarTrack`, `BoxPlot`. Renders as a
    `<dt>/<dd>` annotation in the chart's references list (Phase
    4B.1.b initial). A future ship will wire inline SVG layout so
    reference lines appear over the chart body.
    """

    value: float
    label: str = ""
    style: Literal["solid", "dashed", "dotted"] = "solid"

    def __post_init__(self) -> None:
        if self.style not in _REFERENCE_LINE_STYLES:
            raise ValueError(
                f"invalid style {self.style!r}; must be one of {_REFERENCE_LINE_STYLES}"
            )


@dataclass(frozen=True, slots=True)
class ReferenceBand:
    """Horizontal range annotation on a chart axis from `from_value` to
    `to_value` (e.g. an acceptable range, SLA band, or quartile zone).

    Not a Fragment union member. Held inside chart primitives. `color`
    is a named token from the design palette (target/positive/warning/
    destructive/muted). The `from_` / `to` distinction renames the
    legacy template's `from`/`to` keys (Python keyword conflict).
    Strict invariant: from_value <= to_value.
    """

    from_value: float
    to_value: float
    label: str = ""
    color: Literal["target", "positive", "warning", "destructive", "muted"] = "target"

    def __post_init__(self) -> None:
        if self.color not in _REFERENCE_BAND_COLORS:
            raise ValueError(
                f"invalid color {self.color!r}; must be one of {_REFERENCE_BAND_COLORS}"
            )
        if self.from_value > self.to_value:
            raise ValueError(
                f"ReferenceBand from_value={self.from_value} > to_value={self.to_value}"
            )


_ACTION_CARD_TONES = ("neutral", "positive", "warning", "destructive", "accent")
_METRIC_TILE_TONES = ("", "positive", "warning", "destructive", "accent", "neutral")
_METRIC_DELTA_DIRECTIONS = ("", "up", "down", "flat")
_METRIC_DELTA_SENTIMENTS = ("", "positive_up", "positive_down")


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
    reference_lines: tuple[ReferenceLine, ...] = ()
    reference_bands: tuple[ReferenceBand, ...] = ()

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
class TimelineEvent:
    """Single timeline row — title + already-formatted date + optional
    secondary fields rendered as `<p class="dz-timeline-field">` lines.

    Phase 4B.4 wave 2: extends the Phase 4A `(label, iso-date)` tuple
    shape with a typed dataclass that carries per-event secondary
    fields (the legacy template's per-column iteration).

    `date_label` is the already-formatted relative-time string (e.g.
    "5 hours ago" via the legacy `timeago` filter); `fields` is a
    tuple of `(label, value)` pairs where `value` is either a plain
    string (rendered with HTML escaping) or a Fragment (rendered via
    the renderer's emit dispatch). Trusted markup (e.g. `RawHTML`
    from a legacy filter) renders verbatim.
    """

    title: str
    date_label: str = ""
    fields: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class Timeline:
    """Vertical chronological list.

    Phase 4B.4 wave 2: emits the legacy
    `workspace/regions/timeline.html` shape — `<ul class="dz-timeline-list">`
    of `<li class="dz-timeline-item">` rows, each carrying a bullet
    SVG, formatted date, primary title, and optional secondary fields.
    Optional overflow line "Showing N of M" when `total > len(events)`;
    `empty_message` for the empty-state fallback.

    Backward compatibility: when `events` is a tuple of plain
    `(label, iso-date)` 2-tuples (Phase 4A shape), the renderer
    coerces each to a `TimelineEvent(title=label, date_label=date)`.
    New callers should construct `TimelineEvent` instances directly.
    """

    events: tuple[TimelineEvent | tuple[str, str], ...]
    total: int = 0
    empty_message: str = "No events yet."


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
class StageBar:
    """Workflow progress: header `<progress>` element + chip list of stages.

    Used by `display: progress` regions for an at-a-glance "X of Y
    complete" + per-stage tone (complete/active/empty). Each stage is
    `(name, count, complete)` where `complete: bool` flags the stage
    as already past (chip rendered with the "complete" tone), `count
    > 0` makes it "active", and `count == 0 and not complete` makes
    it "empty".

    `complete_pct` is rendered numerically next to the `<progress>`
    bar; `complete_count + total` produce the "N of M complete"
    summary when `total > 0`.
    """

    stages: tuple[tuple[str, int, bool], ...]
    complete_pct: float = 0.0
    complete_count: int = 0
    total: int = 0

    def __post_init__(self) -> None:
        if not self.stages:
            raise ValueError("StageBar requires at least one stage")
        if not (0.0 <= self.complete_pct <= 100.0):
            raise ValueError(f"StageBar complete_pct={self.complete_pct} outside [0, 100]")


@dataclass(frozen=True, slots=True)
class BarTrack:
    """Compact horizontal value-bar list — one row per bucket.

    Used by `display: bar_track` regions. Each row carries a label,
    raw value (for aria-valuenow), pre-formatted value string (the
    DSL author may have specified a Python format spec like ``{:.0%}``
    via `track_format:`), and fill percentage already computed from
    `value / max_value`. The primitive renders the track HTML with
    ARIA progressbar semantics + a summary line.

    `rows` is a tuple of `(label, value, formatted_value, fill_pct)`
    tuples. Strict invariants: at least one row; `fill_pct` clamped
    to [0, 100] at construction.
    """

    rows: tuple[tuple[str, float, str, float], ...]
    max_value: float
    reference_lines: tuple[ReferenceLine, ...] = ()
    reference_bands: tuple[ReferenceBand, ...] = ()

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("BarTrack requires at least one row")
        for i, row in enumerate(self.rows):
            if len(row) != 4:
                raise ValueError(
                    f"BarTrack row {i} arity mismatch: expected "
                    f"(label, value, formatted_value, fill_pct), got {row!r}"
                )
            _label, _value, _formatted, fill_pct = row
            if not (0.0 <= fill_pct <= 100.0):
                raise ValueError(f"BarTrack row {i} fill_pct={fill_pct} outside [0, 100]")


@dataclass(frozen=True, slots=True)
class MetricTile:
    """Richer metric-tile primitive for the METRICS / SUMMARY display.

    Replaces simple `KPI` for legacy parity. Beyond label + value (which
    KPI already had), `MetricTile` carries:
      - tone: per-tile tint (e.g. positive/warning/destructive/accent)
      - delta block: direction (up/down/flat), sentiment (positive_up
        means "up = good", positive_down means "up = bad"), the delta
        value as a string, optional delta_pct (rendered as `(N%)` when
        non-zero), period label (rendered as `vs <label>`)

    `value` is expected to be already-formatted (the runtime applies
    `metric_number` before passing — adapter ctx-translation does this
    in `_build_metrics`). KPI remains for simple cases without deltas.
    """

    label: str
    value: str
    tone: Literal["", "positive", "warning", "destructive", "accent", "neutral"] = ""
    delta_direction: Literal["", "up", "down", "flat"] = ""
    delta_sentiment: Literal["", "positive_up", "positive_down"] = ""
    delta_value: str = ""
    delta_pct: float = 0.0
    delta_period_label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("MetricTile requires a non-empty label")
        if self.tone not in _METRIC_TILE_TONES:
            raise ValueError(f"invalid tone {self.tone!r}; must be one of {_METRIC_TILE_TONES}")
        if self.delta_direction not in _METRIC_DELTA_DIRECTIONS:
            raise ValueError(
                f"invalid delta_direction {self.delta_direction!r}; "
                f"must be one of {_METRIC_DELTA_DIRECTIONS}"
            )
        if self.delta_sentiment not in _METRIC_DELTA_SENTIMENTS:
            raise ValueError(
                f"invalid delta_sentiment {self.delta_sentiment!r}; "
                f"must be one of {_METRIC_DELTA_SENTIMENTS}"
            )


_STATUS_LIST_STATES = ("neutral", "positive", "warning", "destructive", "accent")


@dataclass(frozen=True, slots=True)
class ListColumn:
    """Column definition for a `ListRegion` table."""

    key: str
    label: str


@dataclass(frozen=True, slots=True)
class ListRegion:
    """Tabular list region — `<div class="dz-list-region">` with action
    row (CSV export), `<div class="dz-list-scroll">` of `<table class="dz-list-table">`,
    and optional overflow line.

    Phase 4B.4 wave 2: dedicated primitive (replaces generic `Table`
    for workspace list regions) emitting the legacy
    `workspace/regions/list.html` shape byte-for-byte for the basic
    case. Each row is a tuple of cell Fragments aligned to `columns`;
    the adapter pre-renders cells via `_render_typed_value`. Filter
    chrome (filter bar, date range, sortable headers, click-through)
    is deferred to a follow-up — basic table + CSV button + overflow
    only.
    """

    columns: tuple[ListColumn, ...]
    rows: tuple[tuple[object, ...], ...]
    csv_endpoint: str = ""
    csv_filename: str = "export.csv"
    total: int = 0
    empty_message: str = ""

    def __post_init__(self) -> None:
        for i, row in enumerate(self.rows):
            if len(row) != len(self.columns):
                raise ValueError(
                    f"ListRegion row {i} arity mismatch: "
                    f"row has {len(row)} cells, expected {len(self.columns)}"
                )


@dataclass(frozen=True, slots=True)
class GridCell:
    """Single cell in a `GridRegion` — title + optional secondary fields.

    Mirrors the legacy `workspace/regions/grid.html` per-cell structure:
    a primary title (display_key value) and zero-or-more secondary
    fields rendered as `<p class="dz-grid-cell-field">` lines under
    the title.
    """

    title: str
    fields: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class GridRegion:
    """Card-grid region — `<div class="dz-grid-list">` of
    `<div class="dz-grid-cell">` items.

    Phase 4B.4 wave 2: dedicated primitive (replaces generic `Grid` for
    workspace grid regions) emitting the legacy
    `workspace/regions/grid.html` shape byte-for-byte. The CSS-driven
    responsive grid layout is owned by `dz-grid-list` rules; cells
    don't carry an explicit column count.
    """

    cells: tuple[GridCell, ...]
    empty_message: str = "No items found."


@dataclass(frozen=True, slots=True)
class TreeNode:
    """Single node in a `Tree` — label + recursive children.

    Children are themselves `TreeNode` instances, building an arbitrary-
    depth hierarchy. Empty `children` tuple means the node is a leaf.
    """

    label: str
    children: tuple["TreeNode", ...] = ()


@dataclass(frozen=True, slots=True)
class Tree:
    """Recursive `<details>`-based hierarchy display.

    Phase 4B.4 wave 2: emits the legacy
    `workspace/regions/tree.html` shape — recursive `<details
    class="dz-tree-node">` with `<summary>` (chevron + label + optional
    child count) and nested `<div class="dz-tree-children">` for
    non-leaf nodes. Top-level nodes (depth 0) render with the
    `[open]` attribute by default; deeper nodes render closed
    (matches the legacy `{% if depth == 0 %}open{% endif %}` guard).
    """

    nodes: tuple[TreeNode, ...]


@dataclass(frozen=True, slots=True)
class ActionGrid:
    """Container for ACTION_GRID region — emits the legacy
    `<div class="dz-action-grid-region"><div class="dz-action-grid">`
    structure wrapping a list of `ActionCard` primitives.

    Phase 4B.4 wave 4: dedicated container primitive (replaces generic
    `Grid` in `_build_action_grid`) for byte-equivalence with
    `workspace/regions/action_grid.html`. Empty state renders the
    `dz-empty-dense` fallback inside the region wrapper.
    """

    cards: tuple[object, ...]
    empty_message: str = "No actions available."


@dataclass(frozen=True, slots=True)
class KanbanCard:
    """Single card in a `KanbanRegion` — title + secondary fields + attention.

    `fields` is a tuple of `(label, value_fragment)` pairs; values are
    typically `RawHTML` from `_render_typed_value` (badge / bool /
    date / currency / ref / default). `attention_level` is one of
    "" (no attention), "critical", "warning", "notice".
    """

    title: str
    fields: tuple[tuple[str, object], ...] = ()
    attention_level: str = ""
    attention_message: str = ""


@dataclass(frozen=True, slots=True)
class KanbanColumn:
    """Single column in a `KanbanRegion` — label + ordered cards."""

    label: str
    cards: tuple[KanbanCard, ...] = ()


@dataclass(frozen=True, slots=True)
class KanbanRegion:
    """Workspace-shaped Kanban board — columns of cards with titles +
    secondary fields + per-card attention tags.

    Phase 4B.4 wave 4: dedicated primitive matching `workspace/regions/
    kanban.html` byte-for-byte. Distinct from the simpler `KanbanBoard`
    primitive (generic column → fragment-list shape) — `KanbanRegion`
    carries the workspace card shape (title, fields, attention).

    `total` + `endpoint` drive the optional "Load all" button when
    the rendered items represent a paginated subset.
    """

    columns: tuple[KanbanColumn, ...]
    total: int = 0
    endpoint: str = ""
    empty_message: str = "No items found."


@dataclass(frozen=True, slots=True)
class FunnelStage:
    """Single stage in a `Funnel` chart — label + count."""

    label: str
    count: int


@dataclass(frozen=True, slots=True)
class Funnel:
    """Stacked proportional bars rendering conversion through ordered stages.

    Phase 4B.4 wave 3: dedicated primitive (replaces alias to BarChart)
    matching `workspace/regions/funnel_chart.html` byte-for-byte. Width
    is calculated relative to the FIRST stage's count (not max), and
    clamped to a 20% minimum so tiny conversion stages stay legible.
    `data-dz-funnel-step` carries the stage index (capped at 7) for
    per-stage opacity fade via CSS.
    """

    stages: tuple[FunnelStage, ...]
    total: int = 0
    empty_message: str = "No data available."


@dataclass(frozen=True, slots=True)
class PivotDimSpec:
    """Dimension column spec for `PivotTableRegion` — name + label +
    FK indicator. Mirrors legacy `pivot_dim_specs` entries."""

    name: str
    label: str
    is_fk: bool = False


@dataclass(frozen=True, slots=True)
class PivotTableRegion:
    """N-dimension cross-tab matching `workspace/regions/pivot_table.html`
    byte-for-byte. Columns = N dimensions (from `dim_specs`) + M
    measures (from `measure_keys`). Per-row cells: dim cells render
    FK-label fallback for `is_fk=True`, status_badge for non-FK,
    em-dash placeholder for None. Measure cells render raw values
    with `.is-measure` modifier.

    `rows` is a tuple of dicts (the legacy `pivot_buckets` shape)
    — the renderer looks up keys per spec rather than pre-computing
    cell tuples, since the legacy template's per-cell logic is
    sensitive to the FK label key naming convention (`<name>_label`).

    Phase 4B.4 wave 4: replaces the simpler `PivotTable` primitive
    (rows/columns/cells matrix) for byte-equivalence with the
    workspace shape.
    """

    dim_specs: tuple[PivotDimSpec, ...]
    measure_keys: tuple[str, ...]
    rows: tuple[dict, ...]
    empty_message: str = "No data to pivot."


@dataclass(frozen=True, slots=True)
class HeatmapRow:
    """Single row in a `Heatmap` — label + ordered cell values.

    `cells` length must match the parent Heatmap's column count.
    `row_id` is optional for click-through to detail (legacy template
    threads it into the row's hx-get URL).
    """

    label: str
    cells: tuple[float, ...]
    row_id: str = ""


@dataclass(frozen=True, slots=True)
class Heatmap:
    """Threshold-tinted matrix display with row labels + column headers.

    Phase 4B.4 wave 4: dedicated primitive matching `workspace/regions/
    heatmap.html` byte-for-byte. Threshold-banded cell tints route
    through `data-dz-heatmap-tone` (bad / warn / good) attribute
    selectors. Cell values formatted as `%.1f`. Overflow line when
    `total > rows count`.

    `thresholds` carries 1 or 2 ascending values:
      - 0 thresholds: cells render with no tone attr
      - 1 threshold: <T0 → bad, ≥T0 → good
      - 2 thresholds: <T0 → bad, <T1 → warn, ≥T1 → good
    """

    columns: tuple[str, ...]
    rows: tuple[HeatmapRow, ...]
    thresholds: tuple[float, ...] = ()
    total: int = 0
    empty_message: str = "No data available."


@dataclass(frozen=True, slots=True)
class HistogramBin:
    """Single bin in a `Histogram` — label + count + continuous range."""

    label: str
    count: int
    low: float
    high: float


@dataclass(frozen=True, slots=True)
class Histogram:
    """Continuous-axis histogram chart.

    Phase 4B.4 wave 3: dedicated primitive (separate from BarChart)
    matching the legacy `workspace/regions/histogram.html` shape
    byte-for-byte. Bars are equal-width with a 1px gap; vertical
    reference lines overlay at their x-position with a label
    hugging the top.
    """

    label: str
    bins: tuple[HistogramBin, ...]
    reference_lines: tuple[ReferenceLine, ...] = ()
    empty_message: str = "No data available."


@dataclass(frozen=True, slots=True)
class Sparkline:
    """Compact time-series for KPI tiles — title + big-number + tiny line.

    Phase 4B.4 wave 2: dedicated primitive (separate from `TimeSeries`)
    matching the legacy `workspace/regions/sparkline.html` shape
    byte-for-byte. Visually distinct from line/area charts: 180×32
    viewBox, no axis labels, no reference overlays, headline showing
    the latest bucket's label + value.

    `points` is a tuple of `(label, value)` pairs — same shape as
    TimeSeries but without view selection. Single-point series omit
    the SVG entirely (the legacy template's `{% if count > 1 %}` guard).
    """

    points: tuple[tuple[str, float], ...]
    empty_message: str = "—"


@dataclass(frozen=True, slots=True)
class PipelineStage:
    """Single stage in a `PipelineSteps` row.

    `value` is the headline aggregate (None renders as "—" matching the
    legacy template's null-coalesce). `progress` is an optional 0-100
    fill percentage; when None the progress bar block is omitted.
    `progress_overshoot=True` flags values that were clamped from >100
    so themes can surface "over capacity" via `data-dz-progress-overshoot`.
    """

    label: str
    value: int | None = None
    caption: str = ""
    progress: int | None = None
    progress_overshoot: bool = False


@dataclass(frozen=True, slots=True)
class PipelineSteps:
    """Sequential-stage workflow row — one card per stage with kicker,
    headline value, optional caption, optional progress bar, and arrow
    connectors between stages.

    Phase 4B.4 wave 2: emits the legacy
    `workspace/regions/pipeline_steps.html` shape byte-for-byte —
    `<ol class="dz-pipeline-stages">` of `<li class="dz-pipeline-stage">`
    rows, with non-last stages emitting two connector SVGs (desktop
    arrow + mobile chevron). Empty path renders the `dz-empty-dense`
    fallback inside the region wrapper.
    """

    stages: tuple[PipelineStage, ...]
    empty_message: str = "No pipeline data available."


@dataclass(frozen=True, slots=True)
class BulletRow:
    """Single row in a `Bullet` chart — Stephen Few bullet shape.

    `actual` is the foreground bar value; `target` is the optional
    vertical-tick goal position. Both are absolute values; the `Bullet`
    container's `max_value` provides the percentage scale.
    """

    label: str
    actual: float
    target: float | None = None


@dataclass(frozen=True, slots=True)
class Bullet:
    """Stephen Few bullet rows — actual-vs-target with comparative bands.

    Phase 4B.4 wave 2: emits the legacy
    `workspace/regions/bullet.html` shape byte-for-byte —
    `<div class="dz-bullet-rows">` with per-row label + track (bands
    behind, actual bar, optional target tick) + formatted value, plus
    a summary line "N rows · scale 0–MAX".

    Reference bands render as `<span class="dz-bullet-band">` overlays
    in the track, positioned by `from_value`/`to_value` as a percentage
    of `max_value`. Colour map matches the chart-family palette
    (`hsl(var(--primary))`, `hsl(145,55%,45%)`, etc.) keyed off the
    `color` field.
    """

    rows: tuple[BulletRow, ...]
    max_value: float
    reference_bands: tuple[ReferenceBand, ...] = ()
    empty_message: str = "No data available."

    def __post_init__(self) -> None:
        if self.max_value <= 0 and self.rows:
            raise ValueError("Bullet max_value must be > 0 when rows are present")


@dataclass(frozen=True, slots=True)
class StatusListEntry:
    """Single row in a `StatusList` — title + optional caption/icon/state.

    `state` drives the per-row tone tinting via `data-dz-state` attr
    (CSS in `dz-tones.css`). Neutral entries omit the pill — they read
    as plain info rather than a status row. `icon` is a Lucide name
    (e.g. "check-circle"); empty string means render the spacer column
    so titles align with iconned entries.
    """

    title: str
    state: Literal["neutral", "positive", "warning", "destructive", "accent"] = "neutral"
    caption: str = ""
    icon: str = ""

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("StatusListEntry requires a non-empty title")
        if self.state not in _STATUS_LIST_STATES:
            raise ValueError(f"invalid state {self.state!r}; must be one of {_STATUS_LIST_STATES}")


@dataclass(frozen=True, slots=True)
class StatusList:
    """Vertical list of icon + title + caption + state-pill rows.

    Phase 4B.4 wave 1: emits the legacy
    `workspace/regions/status_list.html` shape byte-for-byte —
    `<ul class="dz-status-list" data-dz-entry-count="N">` with per-row
    `data-dz-state` attribute driving tone tinting via `dz-tones.css`,
    icon column reserved by spacer when entries lack an icon, pill
    rendered only for non-neutral states.
    """

    entries: tuple[StatusListEntry, ...]
    empty_message: str = "No status entries."


@dataclass(frozen=True, slots=True)
class ActivityFeed:
    """Activity feed list — one row per event with time + optional actor +
    description.

    Each `items` entry is `(time_str, actor, description)`. `time_str` is
    the already-formatted relative time (e.g. "5 hours ago" via the legacy
    `timeago` filter); `actor` is the optional person/agent who performed
    the action (rendered as a separate span when non-empty); `description`
    is the action description.

    Phase 4B.4 wave 1: emits the legacy
    `workspace/regions/activity_feed.html` shape byte-for-byte —
    `<ul class="dz-activity-feed">` with per-row dot SVG, time line, and
    bubble containing actor + description.
    """

    items: tuple[tuple[str, str, str], ...]
    empty_message: str = "No activity yet"


@dataclass(frozen=True, slots=True)
class DetailGrid:
    """Container for DETAIL regions — emits the legacy
    `<div class="dz-detail-region"><dl class="dz-detail-region-grid">`
    two-column label/value definition list.

    Phase 4B.4 wave 1 introduced this primitive (replacing
    Card+Stack+Heading composition for detail regions) so the typed-
    Fragment output is byte-equivalent to
    `workspace/regions/detail.html`. Each row is a (label, value
    fragment) pair: the label renders as `<dt class="dz-detail-label">`,
    the value renders as `<dd class="dz-detail-value">{value_html}</dd>`
    where `value_html` is whatever the value Fragment produces (Badge,
    Text, Link, …).
    """

    rows: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("DetailGrid requires at least one row")
        for i, row in enumerate(self.rows):
            if len(row) != 2:
                raise ValueError(
                    f"DetailGrid row {i} arity mismatch: "
                    f"expected (label, value_fragment), got {row!r}"
                )


@dataclass(frozen=True, slots=True)
class MetricsGrid:
    """Container for METRICS / SUMMARY tiles — emits the legacy
    `<div class="dz-metrics-grid" data-dz-tile-count="N">` wrapper.

    Phase 4B.4 wave 1 introduced this primitive (replacing the
    generic `Grid` for metric regions) so the typed-Fragment output
    is byte-equivalent to `workspace/regions/metrics.html`. The
    legacy template's responsive 1/2/4 column layout is driven by
    the `dz-metrics-grid` CSS rule keyed off `data-dz-tile-count`,
    not by an explicit column count.
    """

    tiles: tuple[object, ...]

    def __post_init__(self) -> None:
        if not self.tiles:
            raise ValueError("MetricsGrid requires at least one tile")


@dataclass(frozen=True, slots=True)
class ProfileCard:
    """Single-record identity panel: avatar/initials + name + meta line +
    optional 3-up stats grid + optional bulleted facts list.

    Used by `display: profile_card` regions for showing one focused
    record (typically a person — `id = current_context`). The region's
    `filter:` is expected to narrow to a single row.

    `stats` is a tuple of `(label, value)` pairs; empty values render as
    em-dash. `facts` is a tuple of free-text strings rendered as a
    bulleted list. The card requires at least one identity element so
    we don't render an empty shell — the adapter degrades to EmptyState
    on missing data rather than letting this through.
    """

    primary: str = ""
    secondary: str = ""
    avatar_url: str = ""
    initials: str = ""
    stats: tuple[tuple[str, str], ...] = ()
    facts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not (self.primary or self.avatar_url or self.initials):
            raise ValueError(
                "ProfileCard requires at least one of primary, avatar_url, or initials"
            )


@dataclass(frozen=True, slots=True)
class ActionCard:
    """Tone-tinted CTA card with optional Lucide icon, count badge, and URL.

    Used by `display: action_grid` regions on dashboards. Each card has a
    label and a tone that maps to the design palette (positive → success
    surface, warning → warning surface, destructive → destructive surface,
    accent → primary tint, neutral → muted/default).

    `count = None` means "no badge"; `count = 0` renders a badge with "0".
    `url = ""` makes a static `<div>` card; a non-empty url wraps the card
    in an anchor.
    """

    label: str
    icon: str = ""
    count: int | None = None
    tone: Literal["neutral", "positive", "warning", "destructive", "accent"] = "neutral"
    url: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("ActionCard requires a non-empty label")
        if self.tone not in _ACTION_CARD_TONES:
            raise ValueError(f"invalid tone {self.tone!r}; must be one of {_ACTION_CARD_TONES}")


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
    reference_lines: tuple[ReferenceLine, ...] = ()
    reference_bands: tuple[ReferenceBand, ...] = ()
    # Per-group sample counts — Phase 4B.4 wave 2. When supplied, the
    # renderer adds `n=N` to the box tooltip matching the legacy
    # template's `n={{ s.n }}` suffix. When empty (default), the suffix
    # is omitted so existing 6-tuple-only callers keep the prior
    # behaviour. Length must match `groups` if non-empty.
    samples: tuple[int, ...] = ()

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
                    f"BoxPlot group {i} quartiles not monotonic: "
                    f"min={mn} q1={q1} median={med} q3={q3} max={mx}; "
                    f"required min <= q1 <= median <= q3 <= max"
                )
        if self.samples and len(self.samples) != len(self.groups):
            raise ValueError(
                f"BoxPlot samples length {len(self.samples)} must match "
                f"groups length {len(self.groups)} (or be empty)"
            )
            _label, mn, q1, med, q3, mx = group
            if not (mn <= q1 <= med <= q3 <= mx):
                raise ValueError(
                    f"BoxPlot group {i} ({_label!r}) quartiles not monotonic: "
                    f"min={mn}, q1={q1}, median={med}, q3={q3}, max={mx}"
                )


@dataclass(frozen=True, slots=True)
class DateRangePicker:
    """Two-input from/to date range filter for list/queue regions.

    Renders a `<div class="dz-date-range-picker date-range-bar">` with
    paired `<input type="date">` elements wired to HTMX with
    `hx-include="closest .date-range-bar"` so both values ride along
    on every change. `date_from` and `date_to` are pre-formatted
    iso-date strings (`YYYY-MM-DD`); empty string = no date set.

    `region_name` namespaces the input ids (`date-from-<region>`,
    `date-to-<region>`) so multiple pickers can coexist on one page.
    """

    endpoint: URL
    region_name: str
    date_from: str = ""
    date_to: str = ""

    def __post_init__(self) -> None:
        if not self.region_name:
            raise ValueError("DateRangePicker requires a non-empty region_name")


@dataclass(frozen=True, slots=True)
class CsvExportButton:
    """Download-CSV button — fetch → Blob → click flow via `dz.downloadCsv`.

    `<a download>` is ignored by Safari for same-origin text/csv
    responses (#862), so the click handler defers to a global JS
    helper that forces a fetch + Blob + synthetic click flow. The
    primitive renders the button shell + `data-dz-csv-*` attrs the
    helper reads at click time. The downloadCsv JS function is
    expected to be registered globally (existing dazzle.min.js).

    `filename` is the suggested download name (e.g. `tickets.csv`);
    no extension enforcement here — the runtime author writes whatever
    makes sense.
    """

    endpoint: URL
    filename: str = "export.csv"
    label: str = "Export CSV"

    def __post_init__(self) -> None:
        if not self.filename:
            raise ValueError("CsvExportButton requires a non-empty filename")


@dataclass(frozen=True, slots=True)
class SortHeader:
    """Column-header link with click-to-sort + direction indicator.

    Used in list/queue table headers. Renders as an `<a>` that sends
    an HTMX request with `?sort=<column_key>&dir=<next>` to the
    region's endpoint. When `current_sort` matches this column's
    key, a ▲ (asc) or ▼ (desc) indicator appears beside the label
    and the link's direction flips on next click. Other columns
    always sort ascending on first click.

    `current_direction` is the direction *currently* active for the
    region (only meaningful when `current_sort == column_key`).
    """

    label: str
    column_key: str
    endpoint: URL
    region_name: str
    current_sort: str = ""
    current_direction: Literal["asc", "desc"] = "asc"

    def __post_init__(self) -> None:
        if not self.column_key:
            raise ValueError("SortHeader requires a non-empty column_key")
        if not self.region_name:
            raise ValueError("SortHeader requires a non-empty region_name")
        if self.current_direction not in ("asc", "desc"):
            raise ValueError(
                f"invalid current_direction {self.current_direction!r}; must be 'asc' or 'desc'"
            )


@dataclass(frozen=True, slots=True)
class FilterColumn:
    """A single filter dropdown inside a FilterBar.

    Not a Fragment union member. `key` is the form field name (will
    be prefixed with `filter_` in the rendered `<select>`'s `name`
    attribute). `options` is the discrete value set; `selected` is
    the currently-active value (empty string = "All <label>").
    """

    key: str
    label: str
    options: tuple[tuple[str, str], ...]  # (value, display_label) pairs
    selected: str = ""

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("FilterColumn requires a non-empty key")


@dataclass(frozen=True, slots=True)
class FilterBar:
    """Row of filter dropdowns above a list/queue region.

    Each dropdown is a `FilterColumn`; the bar emits a `<form>`-less
    flex row of `<select>` elements that re-fire the region endpoint
    on change via HTMX `hx-include="closest .filter-bar"` so all
    active filter values ride along.

    `endpoint` is the region's data URL; `region_name` namespaces the
    HTMX target id (`#region-<name>`) so the swap goes back into the
    same region's body.
    """

    endpoint: URL
    region_name: str
    columns: tuple[FilterColumn, ...]

    def __post_init__(self) -> None:
        if not self.region_name:
            raise ValueError("FilterBar requires a non-empty region_name")
        if not self.columns:
            raise ValueError("FilterBar requires at least one column")
        keys = [c.key for c in self.columns]
        if len(set(keys)) != len(keys):
            raise ValueError(f"FilterBar column keys must be unique; got duplicates in {keys}")


@dataclass(frozen=True, slots=True)
class ConfirmCheckItem:
    """A single item in a ConfirmGate checklist.

    Not a Fragment union member. `required=True` items must be ticked
    before the gate's primary button enables (Alpine logic outside the
    primitive). `caption` is optional explanatory text.
    """

    title: str
    caption: str = ""
    required: bool = False

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("ConfirmCheckItem requires a non-empty title")


@dataclass(frozen=True, slots=True)
class ConfirmGate:
    """Multi-state consent panel for irreversible actions.

    Renders one of three branches based on `state`:
      - off / pending / draft / unknown / "" → checklist (when
        `confirmations` is non-empty) + dual button (secondary
        "Save as draft" + primary "Confirm and enable" gated on
        Alpine `dzConfirmGate(count)` checking required checkboxes)
      - live / active / on / enabled → "Currently live" summary +
        optional revoke link
      - revoked / disabled / off-revoked → audit summary + optional
        re-enable link

    Audit footer auto-renders when `audit_enabled = True` regardless
    of state. The Alpine component `dzConfirmGate(n)` is expected to
    be registered globally — the primitive references it but doesn't
    define it.

    All copy strings have sensible defaults so a minimal ConfirmGate
    just needs `state` and `primary_action_url`. DSL authors override
    via the legacy `confirmations:` block + URL fields; runtime
    threads them into ctx.
    """

    state: str = "off"
    confirmations: tuple[ConfirmCheckItem, ...] = ()
    primary_action_url: str = ""
    secondary_action_url: str = ""
    revoke_url: str = ""
    audit_enabled: bool = False
    primary_label: str = "Confirm and enable"
    secondary_label: str = "Save as draft"
    revoke_label: str = "Revoke"
    re_enable_label: str = "Re-enable"
    live_title: str = "Currently live."
    live_body: str = "Action recorded; further changes require a new authorisation."
    revoked_title: str = "Authorisation revoked."
    revoked_body: str = "Re-authorise to enable the integration again."


@dataclass(frozen=True, slots=True)
class SearchBox:
    """HTMX-driven full-text search input + lazy-loaded results panel.

    Used by `display: search_box` regions. Emits:
      - A search `<input type="search">` with HTMX wiring that hits
        the FTS endpoint on every keystroke (250ms debounce) and
        swaps the result list under the input.
      - A results `<div role="region" aria-live="polite">` that's
        empty initially with a coaching message shown via Alpine
        `x-show="!q"` (hidden once the user starts typing).

    The endpoint authoritatively applies scope predicates so the
    user sees only RBAC-filtered results. The result-row rendering
    is the endpoint's responsibility, not the primitive's — the
    primitive just establishes the input + swap target.

    `name` is used as the results-div id slug (`dz-search-results-<name>`)
    so multiple SearchBoxes can coexist on one page. `coaching_message`
    is the already-translated string (i18n is applied by the runtime
    before primitive construction).
    """

    name: str
    fts_endpoint: URL
    placeholder: str = "Search…"
    coaching_message: str = "Type to search"
    label: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("SearchBox requires a non-empty name")


@dataclass(frozen=True, slots=True)
class LazyTab:
    """A single tab inside a LazyTabPanel — key + label + endpoint
    + eager-load flag.

    Not a Fragment union member. `key` becomes part of DOM ids
    (`tab-<region>-<key>`), so it should be a slug (typically a
    snake-cased entity name). `eager=True` makes the panel fetch on
    page load (first tab); `eager=False` defers to intersect-once
    (subsequent tabs).
    """

    key: str
    label: str
    endpoint: URL
    eager: bool = False

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("LazyTab requires a non-empty key")
        if not self.label:
            raise ValueError("LazyTab requires a non-empty label")


@dataclass(frozen=True, slots=True)
class LazyTabPanel:
    """Tabbed container with per-panel HTMX lazy loading.

    Used by `display: tabbed_list` regions. Each tab becomes a button
    in the tab list + a panel `<div>` that fetches its own content
    via `hx-get` on first activation. The first tab fires `load`;
    subsequent tabs fire on `intersect once`. A vanilla-JS click
    handler toggles the `is-active` class and shows/hides panels.

    `region_name` namespaces the DOM ids — `tabs-<region_name>` and
    `tab-<region_name>-<tab.key>` — so multiple LazyTabPanels can
    coexist on one page.

    Strict invariants: at least one tab; tab keys unique; exactly
    one tab marked eager (the first by convention).
    """

    region_name: str
    tabs: tuple[LazyTab, ...]
    empty_message: str = "No data available."

    def __post_init__(self) -> None:
        if not self.region_name:
            raise ValueError("LazyTabPanel requires a non-empty region_name")
        if not self.tabs:
            raise ValueError("LazyTabPanel requires at least one tab")
        keys = [t.key for t in self.tabs]
        if len(set(keys)) != len(keys):
            raise ValueError(f"LazyTabPanel tab keys must be unique; got duplicates in {keys}")


@dataclass(frozen=True, slots=True)
class TimeSeries:
    """Sequential numeric data plotted over a label axis.

    One primitive covers `line_chart`, `area_chart`, and `sparkline` —
    they differ only in chrome (axis labels, fill, size). The `view`
    discriminator selects the rendering style.

    `points` is a sequence of (label, value) pairs. The label is
    rendered as-is (typically an iso-date string or a bucket name);
    values are floats so callers can pass ratios as well as counts.

    Optional `reference_lines` and `reference_bands` carry chart
    overlays — single-value horizontal annotations and shaded ranges
    respectively. Phase 4B.1.b emits them as semantic `<dl>` data
    after the chart points; future SVG-rendering ship will overlay
    them on the visual chart.
    """

    label: str
    points: tuple[tuple[str, float], ...]
    view: Literal["line", "area", "sparkline"] = "line"
    reference_lines: tuple[ReferenceLine, ...] = ()
    reference_bands: tuple[ReferenceBand, ...] = ()

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
