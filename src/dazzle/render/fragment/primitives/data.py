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
from typing import Any, Literal

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
class RowCapabilities:
    """Orthogonal per-row capability vector for the converged list row-core
    (#1505 — `docs/superpowers/specs/2026-06-28-list-render-convergence-design.md`
    §3). Each flag honours the one composition rule: *the row owns the bare
    click (`drill`); every interactive sub-element stops propagation*.

    Phase 1 carries only the flags that gate the rich `data-table` archetype's
    output — the subset that varies in today's `_render_table_row`. The field
    set grows in Phase 3 as the `list-region` / `embedded` archetypes are folded
    onto the shared core (e.g. an explicit `row_actions` flavour). Adding a
    capability that cannot satisfy the composition rule is the signal it belongs
    to a new archetype, not a new flag here.
    """

    bulk_select: bool = False
    inline_editable: tuple[str, ...] = ()
    drill: bool = False
    peek: str = "off"


@dataclass(frozen=True, slots=True)
class DataTable:
    """Rich CRUD data-table primitive (#1505) — the `render/` substrate home for
    the `dz-tr-row` archetype previously rendered by
    `http/runtime/htmx_render.py::_render_table_row`.

    Unlike `Table`/`ListRegion` (which carry pre-rendered string/Fragment cells),
    `DataTable` carries the *raw inputs* the row-core needs to render cells
    itself: `columns` are column-spec mappings (``key``/``type``/optional
    ``hidden``/``currency_code``/``semantic_map``/``filter_options``/``label``)
    and `rows` are item mappings. Rendered by `_emit_data_table` (full table) and
    `render_data_table_rows` (the `<tbody>`-only entry the http/ HTMX-refresh
    transport path calls down into).
    """

    columns: tuple[typing.Mapping[str, Any], ...]
    rows: tuple[typing.Mapping[str, Any], ...] = ()
    entity_name: str = "Item"
    api_endpoint: str = ""
    detail_url_template: str = ""
    table_id: str = "dt-table"
    capabilities: RowCapabilities = field(default_factory=RowCapabilities)
    # No empty-columns guard: the rich row-core renders an actions-only row for a
    # column-less table exactly as the retired `_render_table_row` did, so the
    # #1505-P2 switch stays byte-identical even for a misconfigured (column-less)
    # refresh. A column-less data-table is degenerate, not an error to raise.


@dataclass(frozen=True, slots=True)
class Table:
    """Plain tabular data primitive.

    `row_links` (issue #1029 phase 1) is an optional parallel tuple
    aligned to `rows`: when set, each row's first cell is wrapped in
    an `<a href="...">` so clicking the row navigates to that URL.
    Length must match `rows`. Use `None` for rows that should NOT be
    clickable (e.g. summary rows). Backwards-compatible — pass `()` /
    omit to keep the legacy plain-table render."""

    columns: tuple[object, ...]  # str | SortHeader
    rows: tuple[tuple[str, ...], ...]
    row_links: tuple[str | None, ...] = ()
    # Issue #1029 phase 7: bulk-selection support.
    # When `bulk_select=True`, the renderer prepends a checkbox column
    # to the header + each row. `row_ids` (parallel to `rows`) provides
    # the per-row id used in `data-dz-row-id` + Alpine `toggleRow('{id}')`
    # bindings. The dzTable Alpine controller (see legacy
    # `static/js/dz_table.js`) owns the `selected` Set and exposes
    # `toggleRow`, `toggleSelectAll`, `bulkDelete`, `clearSelection`.
    bulk_select: bool = False
    row_ids: tuple[str, ...] = ()
    # ADR-0049 Phase 1 (D2): skeleton mode. When `skeleton=True` the table
    # first-paints chrome (thead) + an empty hydrating `<tbody>` that `hx-get`s
    # the row body from `hx_endpoint` (→ `render_data_row`, the sole row
    # source). No inline `<tr>` rows. Mirrors the legacy
    # `render_filterable_table` skeleton tbody so the hydrate is identical.
    skeleton: bool = False
    tbody_id: str = ""  # legacy `{table_id}-body` — htmx target for refreshes
    hx_endpoint: str = ""  # row-body endpoint (already carries any sort qs)
    hx_trigger: str = "load"  # base trigger; "" suppresses (search_first lists)
    refresh_interval: int | None = None  # appends `, every Ns` to the trigger
    loading_indicator: str = ""  # `#{table_id}-loading-sr` selector
    # ADR-0049 Phase 1 Task 4a: in skeleton mode the list `<table>` carries the
    # canonical `dz-table-grid` class + a visually-hidden `<caption>` (the
    # accessible name) + a trailing actions `<th>` so the thead column count
    # matches the hydrated `render_data_row` rows (which always emit a trailing
    # actions `<td>`). All three are skeleton-only — embedded plain tables are
    # unaffected.
    caption: str = ""
    has_actions: bool = False
    # ADR-0049 Phase 1 Task 4e: parallel column keys (aligned to `columns`).
    # When set, each data `<th>` carries `data-dz-col="{key}"` so the dzTable
    # column-visibility toggle hides the header in lock-step with the hydrated
    # `render_data_row` body cells. Empty = plain headers (embedded tables).
    column_keys: tuple[str, ...] = ()
    # Keys whose canonical list header renders as a dzTable `toggleSort`
    # button (client-state sort + aria-sort + sort icon), not a static label.
    # Only consulted in skeleton mode alongside `column_keys`.
    sortable_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.columns:
            raise ValueError("Table requires at least one column")
        if self.skeleton and self.rows:
            raise ValueError(
                "skeleton tables must not carry inline rows — rows hydrate "
                "from hx_endpoint via render_data_row (ADR-0049 D2)"
            )
        for i, row in enumerate(self.rows):
            if len(row) != len(self.columns):
                raise ValueError(
                    f"row arity mismatch at index {i}: row has {len(row)} cells, "
                    f"columns has {len(self.columns)}"
                )
        if self.row_links and len(self.row_links) != len(self.rows):
            raise ValueError(
                f"row_links length {len(self.row_links)} != rows length {len(self.rows)}"
            )
        if self.bulk_select and self.rows and len(self.row_ids) != len(self.rows):
            raise ValueError(
                f"row_ids length {len(self.row_ids)} != rows length {len(self.rows)} "
                "(bulk_select requires a per-row id for the checkbox/Alpine binding)"
            )


@dataclass(frozen=True, slots=True)
class DataListScroll:
    """The canonical list-table shell (ADR-0049 Phase 1 Task 4b).

    Wraps a skeleton `Table` with the scroll container + loading-spinner
    overlay + focusable horizontal scroll region + empty-state sibling +
    screen-reader loading indicator — reproducing the legacy
    `render_filterable_table` table shell so the whole `table.css` (loading
    `:has(.htmx-request)`, the `.dz-table-grid ~ .dz-table-empty` empty guard,
    the `--dz-list-rows` sizing) applies unchanged. The outermost `.dz-table`
    class is what scopes those rules.

    `table` is the skeleton `Table` child (rendered inside the scroll region,
    immediately before the empty sibling so the CSS following-sibling guard
    fires). `empty_action_*` render an optional create CTA in the empty state.
    """

    table: object
    table_id: str
    page_size: int = 10
    aria_label: str = ""
    empty_title: str = "No items found"
    empty_description: str = "Try adjusting your search or filter criteria."
    empty_action_href: str = ""
    empty_action_label: str = ""
    # Task 4e: emit the empty `#{table_id}-pagination` footer the /api response
    # fills via its `hx-swap-oob` pagination swap (list_handlers). False for
    # infinite-scroll lists (no footer).
    paginated: bool = True


@dataclass(frozen=True, slots=True)
class ColumnVisibilityMenu:
    """The list header's column-visibility menu (ADR-0049 Phase 1 Task 4c).

    A dropdown of per-column checkboxes bound to the `dzTable` controller's
    `isColumnVisible`/`toggleColumn` — mirrors the legacy
    `render_filterable_table` column menu. `columns` is the ordered tuple of
    visible `(key, label)` pairs. `_build_list` only constructs the menu when
    there are more than three visible columns (the legacy gate)."""

    columns: tuple[tuple[str, str], ...]


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
    # #1148: optional per-row action column. When ``row_actions`` is
    # non-empty it must have the same arity as ``rows`` (one button
    # HTML string per row, ``""`` for rows whose ``visible_when``
    # evaluated falsy — the renderer emits an empty cell so column
    # arity stays stable). ``row_action_label`` is the column header.
    row_action_label: str = ""
    row_actions: tuple[str, ...] = ()
    # #1303: optional per-row drill-to-detail URLs. When non-empty it must
    # have the same arity as ``rows`` — one URL per row, ``None`` for rows
    # that aren't drillable (missing the template's key). The renderer puts
    # an ``hx-get`` to the URL on the ``<tr>`` (full-page swap, clickable
    # row) when the entry is set — the htmx-idiomatic shape the standalone
    # list uses (#1029), not a cell ``<a>`` which would break ``<td>`` nesting.
    row_links: tuple[str | None, ...] = ()

    def __post_init__(self) -> None:
        for i, row in enumerate(self.rows):
            if len(row) != len(self.columns):
                raise ValueError(
                    f"ListRegion row {i} arity mismatch: "
                    f"row has {len(row)} cells, expected {len(self.columns)}"
                )
        if self.row_actions and len(self.row_actions) != len(self.rows):
            raise ValueError(
                f"ListRegion row_actions arity mismatch: "
                f"{len(self.row_actions)} actions, {len(self.rows)} rows"
            )
        if self.row_links and len(self.row_links) != len(self.rows):
            raise ValueError(
                f"ListRegion row_links arity mismatch: "
                f"{len(self.row_links)} links, {len(self.rows)} rows"
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
class QueueMetric:
    """Single metric tile in a `QueueRegion` summary row."""

    label: str
    value: str


@dataclass(frozen=True, slots=True)
class QueueTransition:
    """Inline state-transition action button on a `QueueRow`.

    `to_state` is the target state (compared against the row's
    current `queue_status_field` value to decide whether to render
    the button). HTMX wiring is `hx-put="{endpoint}/{id}"` with
    `hx-vals='{"<status_field>": "<to_state>"}'`, posted form-urlencoded
    (json-enc was dropped in the htmx 4 migration).
    """

    label: str
    to_state: str


@dataclass(frozen=True, slots=True)
class QueueBadgeColumn:
    """A column-keyed badge to render alongside the row headline title."""

    key: str
    value: object  # any value the legacy render_status_badge accepts


@dataclass(frozen=True, slots=True)
class QueueDateColumn:
    """A column-keyed date label to render as a secondary info line."""

    label: str
    timeago_str: str


@dataclass(frozen=True, slots=True)
class QueueRow:
    """Single row in a `QueueRegion`.

    Layout per legacy template:
      - row_id is the item id used for transition button URL interpolation
      - title is the resolved display label (display_key + _display fallback)
      - badges are the per-row badge columns (rendered next to title)
      - attention_level/message drive the optional attention accent + line
      - date_columns render below as `Label: timeago_str` secondaries
      - transitions are evaluated against current_status to decide which buttons render
    """

    row_id: str
    title: str
    current_status: str = ""
    badges: tuple[QueueBadgeColumn, ...] = ()
    date_columns: tuple[QueueDateColumn, ...] = ()
    attention_level: str = ""
    attention_message: str = ""


@dataclass(frozen=True, slots=True)
class QueueRegion:
    """Review-queue display matching `workspace/regions/queue.html`.

    Phase 4B.4 wave 4: dedicated primitive family (replaces prior
    Card+Stack composition in `_build_queue`). Optional count row +
    metrics row + filter bar + queue rows + overflow line. Transitions
    are inline state-change action buttons; each row renders only the
    transitions whose `to_state != current_status`.
    """

    rows: tuple[QueueRow, ...]
    total: int = 0
    metrics: tuple[QueueMetric, ...] = ()
    transitions: tuple[QueueTransition, ...] = ()
    queue_status_field: str = ""
    queue_api_endpoint: str = ""
    region_name: str = ""
    empty_message: str = "Queue is empty."


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
    rows: tuple[dict[str, Any], ...]
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
    # ADR-0049 Phase 1 Task 4d: filter control kind for ListFilterBar.
    # "select" (static options), "text" (free-text contains), or "ref" (a
    # FK select whose options are fetched at runtime via `dzFilterRefSelect`
    # from `ref_api`). The workspace FilterBar ignores these (it only renders
    # static selects).
    filter_type: str = "select"
    ref_api: str = ""

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
class ListFilterBar:
    """List-surface filter row (ADR-0049 Phase 1 Task 4d).

    Distinct from the workspace `FilterBar`: it targets the list's hydrating
    `<tbody>` (`#{tbody_id}`) with `filter[{key}]` param names + `innerMorph`
    — exactly what the `/api` list handler parses (list_handlers.py) and what
    the skeleton tbody hydrates with. (The workspace `FilterBar` targets
    `#region-{name}` with `filter_{key}` names, which the list handler does
    not parse.) The FTS search box is the canonical free-text affordance;
    these selects narrow the list in place.

    `hx-include="closest [data-dazzle-table]"` makes every active filter ride
    along on each change, matching the legacy list filter bar."""

    tbody_id: str
    endpoint: URL
    columns: tuple[FilterColumn, ...]
    loading_indicator: str = ""

    def __post_init__(self) -> None:
        if not self.tbody_id:
            raise ValueError("ListFilterBar requires a non-empty tbody_id")
        if not self.columns:
            raise ValueError("ListFilterBar requires at least one column")


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
class TimeSeriesSeries:
    """One named series inside a multi-series `TimeSeries`.

    Not a Fragment union member — held inside `TimeSeries.series`. Each
    series carries its own `(label, value)` points; the renderer aligns
    them on a shared label axis (the ordered union of all series'
    labels) and draws them as overlaid transparent layers, one design
    palette colour per series. Used by stacked `area_chart`
    (`group_by: [bucket(date, unit), <dim>]`) and line-chart
    `overlay_series` (#883, #1473).
    """

    name: str
    points: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("TimeSeriesSeries requires at least one point")


@dataclass(frozen=True, slots=True)
class TimeSeries:
    """Sequential numeric data plotted over a label axis.

    One primitive covers `line_chart`, `area_chart`, and `sparkline` —
    they differ only in chrome (axis labels, fill, size). The `view`
    discriminator selects the rendering style.

    `points` is a sequence of (label, value) pairs for the single-series
    case. The label is rendered as-is (typically an iso-date string or a
    bucket name); values are floats so callers can pass ratios as well
    as counts.

    `series` carries the multi-series case (#1473): a tuple of
    `TimeSeriesSeries`, each a named `(label, value)` line. When `series`
    is non-empty it takes precedence over `points` and the renderer draws
    every series as an overlaid transparent layer on a shared label axis
    (line/area views only — sparkline stays single-series). Exactly one of
    `points` / `series` must be non-empty.

    Optional `reference_lines` and `reference_bands` carry chart
    overlays — single-value horizontal annotations and shaded ranges
    respectively. Phase 4B.1.b emits them as semantic `<dl>` data
    after the chart points; future SVG-rendering ship will overlay
    them on the visual chart.
    """

    label: str
    points: tuple[tuple[str, float], ...] = ()
    view: Literal["line", "area", "sparkline"] = "line"
    reference_lines: tuple[ReferenceLine, ...] = ()
    reference_bands: tuple[ReferenceBand, ...] = ()
    series: tuple["TimeSeriesSeries", ...] = ()

    def __post_init__(self) -> None:
        if self.view not in _TIMESERIES_VIEWS:
            raise ValueError(f"invalid view {self.view!r}")
        if not self.points and not self.series:
            raise ValueError("TimeSeries requires at least one point")


@dataclass(frozen=True, slots=True)
class Diagram:
    """Node-and-edge graph (e.g. an entity-relationship diagram).

    Two rendering modes:
      - `mermaid_source` non-empty: emit `<pre class="mermaid">` carrying
        the raw Mermaid syntax + the Mermaid CDN loader script. Matches
        the legacy `workspace/regions/diagram.html` byte-for-byte. This
        is the preferred runtime path (production runtime computes a
        Mermaid `erDiagram` source via `_build_diagram_data`).
      - `mermaid_source` empty + nodes non-empty: emit a structural
        node/edge list (Phase 4A fallback). Useful for tests and any
        consumer that hasn't built a Mermaid source.

    The empty-state path (no nodes, no source) is the adapter's
    responsibility — produce an `EmptyState` instead of a `Diagram`.
    """

    nodes: tuple[str, ...] = ()
    edges: tuple[tuple[str, str], ...] = ()
    mermaid_source: str = ""

    def __post_init__(self) -> None:
        if not self.nodes and not self.mermaid_source:
            raise ValueError("Diagram requires nodes OR a mermaid_source")
        if self.nodes:
            node_set = set(self.nodes)
            for f, t in self.edges:
                if f not in node_set:
                    raise ValueError(f"edge from {f!r} not in declared nodes")
                if t not in node_set:
                    raise ValueError(f"edge to {t!r} not in declared nodes")


@dataclass(frozen=True, slots=True)
class CardPickerEntry:
    """One row in a CardPicker — represents a region the user can add
    to a workspace dashboard. Maps to one Jinja `<button>` in
    `_card_picker.html`.

    `name` is the catalog key (also the value passed to `addCard()`).
    `display` is the lowercase region display tag (e.g. `list`, `kanban`)
    shown as a small chip; legacy template `lower`s it, we do the same
    in the renderer."""

    name: str
    title: str
    entity: str
    display: str = ""


@dataclass(frozen=True, slots=True)
class DashboardNotice:
    """Optional notice band rendered above a DashboardCard's body.

    `tone` keys off `data-dz-notice-tone` (#906) — `neutral` / `success` /
    `warning` / `error` are resolved to colours by `dz-tones.css`. The
    body string is optional; absent body means just a one-line title."""

    title: str
    body: str = ""
    tone: str = "neutral"


@dataclass(frozen=True, slots=True)
class DashboardCard:
    """One region card in the workspace dashboard grid (Phase 4B.5.b.2.ii).

    Carries the chrome (drag handle, title row, remove action, optional
    notice band, body skeleton, resize handle) plus the lazy/eager
    HTMX trigger that pulls the region body from the runtime.

    `card_id` is the per-card unique slug — `data-card-id`, the
    `card-title-{card_id}` aria-labelledby anchor, and the
    `region-{name}-{card_id}` body id all key off it. Generated by
    the adapter as `'card-' + str(loop_index)` to match legacy
    template behaviour.

    `eager` controls the HTMX trigger: `'load'` (eager — above-the-fold)
    vs `'intersect once'` (lazy — defer until scrolled into view).
    Adapter sets `eager = (row_order < fold_count)` per #864.

    `sse_enabled` is true when the workspace declared an `sse_url`;
    adds `, sse:entity.created, sse:entity.updated, sse:entity.deleted`
    to the `hx-trigger` so the card refreshes when the runtime pushes
    a relevant entity event.

    `display` is the lowercased region display value (e.g. `list`,
    `kanban`) — drives the `data-display` attribute the contract
    checker keys off."""

    card_id: str
    name: str
    title: str
    display: str
    col_span: int
    row_order: int
    hx_endpoint: str
    eager: bool = False
    sse_enabled: bool = False
    eyebrow: str = ""
    css_class: str = ""
    notice: DashboardNotice | None = None
    # #1391: declarative live-refresh. When set (seconds, >= 5), the card's
    # HTMX trigger appends `, every Ns` so the region-fetch endpoint re-renders
    # on a poll. `None` = no polling (legacy). Composes with `sse_enabled` and
    # the lazy/eager base trigger.
    refresh_interval: int | None = None
    # #1204: edit-mode chrome gating. When False (the safe default), the
    # `dz-card-actions` div (Remove card × button) is omitted entirely
    # from emitted HTML — no hover-flash, no a11y tab target, no surprise
    # screen-reader click target. The page-route call site flips this to
    # True only for permitted users (currently `is_superuser`).
    edit_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.card_id:
            raise ValueError("DashboardCard requires a card_id")
        if not self.name:
            raise ValueError("DashboardCard requires a region name")
        if self.col_span < 1:
            raise ValueError("col_span must be >= 1")


@dataclass(frozen=True, slots=True)
class DashboardGrid:
    """The card grid container — emits `<div class="dz-dashboard-grid"
    data-grid-container role="application" aria-label="Dashboard card grid">`
    with optional `hx-ext="sse" sse-connect="..."` when the workspace
    declared an `sse_url`.

    Cards are pre-built by the adapter; per-card `card_id`,
    `eager` (loop.index0 < fold_count), `hx_endpoint`, and
    `sse_enabled` are all computed there.

    `edit_enabled` (#1204) gates edit-mode chrome — both the server-rendered
    Remove-card buttons on cards AND the `data-grid-editable` attribute the
    JS dashboard-builder reads when injecting dynamically-added cards.
    Defaults to False (safe). The page-route call site flips it from the
    existing `is_superuser` check."""

    cards: tuple[DashboardCard, ...] = ()
    sse_url: str = ""
    edit_enabled: bool = False


@dataclass(frozen=True, slots=True)
class BulkActionToolbar:
    """Bulk-selection toolbar for list surfaces (Phase 7 of #1029).

    Fixed shape singleton matching legacy `bulk_actions.html` byte-
    for-byte: Delete + Clear-selection buttons. Visibility CSS-driven
    via `[data-dz-bulk-count]` on the outer `.dz-table` wrapper (set
    by dzTable's `$watch` on bulkCount); the count text is mirrored
    to `[data-dz-bulk-count-target]` descendants imperatively per
    ADR-0022 (no Alpine bindings on children that idiomorph could
    re-evaluate before scope rebinds).

    Alpine state lives on the dzTable controller — `selected` Set,
    `bulkDelete()`, `clearSelection()` — already shipped in
    `static/js/dz_table.js`. This primitive emits the matching DOM."""


@dataclass(frozen=True, slots=True)
class CreateButton:
    """The "New <Entity>" link in a list-surface header.

    Issue #1029 phase 3 — matches the legacy `filterable_table.html`
    create-button shape byte-for-byte: `<a href="{href}"
    data-dazzle-action="{entity_name}.create" class="dz-button-primary">`
    + 12×12 plus-icon SVG + "New {entity_name with _ replaced by ' '}"
    label.

    `data-dazzle-action` is the RBAC contract checker's anchor — the
    typed primitive must round-trip it exactly. Distinct from a plain
    `Link` because of the structural label/icon/data-attribute trio.

    Custom label override: when `label` is non-empty, used verbatim
    (e.g., DSL declares `action_primary` with a custom label like
    "Add Contact"). Default label is `New {entity_name}` with
    underscores replaced by spaces."""

    href: object  # URL — typed object to keep the union simple
    entity_name: str
    # #1487: entity's declared display title ("Curriculum Plan"). When set and
    # no explicit `label` override, the default becomes "New <entity_title>"
    # instead of "New <entity_name>" (the raw PascalCase identifier).
    entity_title: str = ""
    label: str = ""

    def __post_init__(self) -> None:
        if not self.entity_name:
            raise ValueError("CreateButton requires a non-empty entity_name")


@dataclass(frozen=True, slots=True)
class Pagination:
    """Page-by-page pagination controls for a table.

    Issue #1029 phase 2 — appended below the LIST adapter's Table when
    `total > page_size`. Renders the legacy `_table_pagination.html`
    contract: a left summary (`<total> rows`) + right page-button row
    with bounded width via ellipsis (`pagination_pages` helper, max
    ~9 entries regardless of total page count, see #984).

    Each page button carries `hx-get="{endpoint}?page=N&page_size=M..."`
    + `hx-target="#{region_name}-body"` + `hx-swap="morph:innerHTML"`
    so clicks fetch the next slice without a full page reload.
    Active page gets `is-current` + `aria-current="page"`.

    `extra_query` is an opaque pre-encoded string (e.g. `"&sort=name&dir=asc"`)
    appended to every page link — used by Phase 5+6 to preserve sort,
    filter, and search state across page hops. Empty string when none."""

    region_name: str
    endpoint: object  # URL — typed object to keep the union simple
    total: int
    page: int
    page_size: int
    extra_query: str = ""

    def __post_init__(self) -> None:
        if not self.region_name:
            raise ValueError("Pagination requires a non-empty region_name")
        if self.page < 1:
            raise ValueError(f"page must be >= 1, got {self.page}")
        if self.page_size < 1:
            raise ValueError(f"page_size must be >= 1, got {self.page_size}")
        if self.total < 0:
            raise ValueError(f"total must be >= 0, got {self.total}")


@dataclass(frozen=True, slots=True)
class Sequence:
    """Transparent multi-child container — emits children concatenated
    with no surrounding markup.

    Stack/Row/Grid all wrap their children in a `<div>` with their
    own classes; Sequence does NOT — useful when you need multiple
    sibling Fragments where the caller's markup already provides the
    structural wrapper (e.g., chrome composition inside a
    WorkspaceShell body where the `.dz-workspace` div is the wrapper
    and the inner pieces are siblings, not stack-children)."""

    children: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceContextSelector:
    """The optional context selector that filters workspace regions
    by an entity FK (Phase 4B.5.b.3).

    Renders `<div class="dz-workspace-context">` with a `<label>` +
    `<select id="dz-context-selector">` carrying the default `All`
    option, plus an inline IIFE that:
      1. Fetches options from `options_url` and populates the select.
      2. Restores any `dzPrefs`-saved selection or defaults to the
         first real option (the legacy "All" landing-page-empty fix
         per #870).
      3. Updates every `[id^="region-"][hx-get]` element's hx-get to
         carry `context_id={selected}` and re-triggers the htmx fetch
         (#980 round 2 guards against htmx not yet loaded).

    `workspace_name` keys the dzPrefs storage (`workspace.X.context`).
    `label` is the resolved display string (adapter applies the
    `context_selector_label or entity.replace('_', ' ')` fallback)."""

    workspace_name: str
    options_url: str
    label: str

    def __post_init__(self) -> None:
        if not self.workspace_name:
            raise ValueError("WorkspaceContextSelector requires a workspace_name")
        if not self.options_url:
            raise ValueError("WorkspaceContextSelector requires an options_url")


@dataclass(frozen=True, slots=True)
class WorkspaceDrawer:
    """Detail-drawer singleton (Phase 4B.5.b.3).

    The drawer is a fixed shape: backdrop div + aside container +
    header (close button + optional expand link) + content slot, plus
    the IIFE that wires `window.dzDrawer.open()` / `.close()` and the
    document-level htmx:after:settle defensive close (#934).

    The IIFE installs an init guard (`window.__dzDrawerInit`) so the
    listeners are registered exactly once across the session — the
    drawer markup gets re-emitted on every workspace nav swap, but
    the listeners are only added on the first emission.

    No parameters — the entire markup + script is emitted verbatim
    from the canonical static asset (`render/fragment/static/
    workspace_drawer.html`)."""


@dataclass(frozen=True, slots=True)
class AddCardRow:
    """The "Add Card" row that anchors the picker popover (Phase 4B.5.b.2.iii).

    Emits `<div class="dz-add-card-row">` with a `+` button toggling
    `showPicker` on the parent `dzDashboardBuilder()` x-data, plus the
    embedded CardPicker. Visibility of the picker is CSS-driven via
    `[data-show-picker="1"]` on the workspace ancestor (#982); this
    primitive doesn't manage that — it just composes the row + picker.

    `data-test-id="dz-add-card-trigger"` is the harness anchor for the
    + button click."""

    picker: "CardPicker"


@dataclass(frozen=True, slots=True)
class WorkspaceToolbar:
    """Workspace toolbar row — Reset + Save buttons (Phase 4B.5.b.2.i).

    Fixed shape singleton matching the legacy `_content.html` toolbar
    section. The Alpine state machine `dzDashboardBuilder()`
    parent owns `saveState`, `resetLayout()`, `save()`, `_saveError`;
    this primitive emits the markup that binds to those.

    Save button has five `x-cloak`+`x-show` spans for the saveState
    states: clean / dirty / saving / saved / error. `x-cloak` gates
    visibility until Alpine evaluates `x-show` — protects against
    degraded state (#866) where alpine:init fails to fire (HTMX morph
    race, layout-JSON parse error, etc.) and the browser's default
    `display: inline` would otherwise stack every status label
    simultaneously."""


@dataclass(frozen=True, slots=True)
class WorkspacePrimaryAction:
    """One link in the workspace heading's primary-actions row.

    Framework-inferred from region entities that expose CREATE
    surfaces and for which the current persona has create permission
    (#827). Renders as a `<a class="dz-workspace-action" hx-boost="true">`
    with a leading `+` SVG icon and the label text."""

    label: str
    route: str


@dataclass(frozen=True, slots=True)
class WorkspaceShell:
    """The outer `.dz-workspace` wrapper (Phase 4B.5.b.1).

    Emits the dashboard chrome shell:
      - Outer `<div class="dz-workspace" x-data="dzDashboardBuilder()" ...>`
        with `data-workspace-name` (always) and optional `data-fold-count`.
      - Heading row: `<h2 class="dz-workspace-title">` + optional
        primary-actions row (`<div class="dz-workspace-primary-actions">`
        with `data-test-id="dz-workspace-primary-actions"`).
      - The `body` slot — a Fragment carrying the rest of the chrome
        (slot grid, drawer, picker). Filled incrementally across
        Phase 4B.5.b.2 (slot grid) and 4B.5.b.3 (drawer + picker +
        context selector).

    Card safety: the workspace owns title chrome (the `h2`); regions
    inside `body` are contentless wrappers (the dashboard slot owns
    region title chrome via region_card invariant)."""

    workspace_name: str
    title: str
    body: object  # Fragment — typed as object per primitive convention
    primary_actions: tuple[WorkspacePrimaryAction, ...] = ()
    fold_count: int | None = None


@dataclass(frozen=True, slots=True)
class CardPicker:
    """The "Add a card" popover used by the workspace dashboard builder
    (Phase 4B.5.a port of `workspace/_card_picker.html`).

    Renders the full `<div class="dz-card-picker">` shell:
      - The `data-card-catalog` JSON blob the JS reads when the user
        picks an entry. The string is opaque to the primitive — the
        adapter stringifies the catalog ahead of time. We single-quote
        the attribute (matching legacy `#963` convention) so embedded
        `"` chars from `tojson` don't terminate the attribute mid-value.
      - A `dz-card-picker-title` heading.
      - One `<button class="dz-card-picker-entry" @click='addCard(...)'>`
        per entry, with `data-test-id` + `data-test-region` for the
        Playwright harness.
      - A `dz-card-picker-empty` fallback when entries is empty.

    Visibility is CSS-driven via `[data-show-picker="1"]` on the
    ancestor `.dz-workspace`; this primitive emits no `x-show` /
    `x-cloak` (matches legacy `#982` move that removed Alpine bindings
    from this morphable child element)."""

    entries: tuple[CardPickerEntry, ...]
    catalog_json: str = "[]"


@dataclass(frozen=True, slots=True)
class CohortStripCell:
    """One member cell in a `CohortStripRegion` (#1018).

    Carries the member halo (initials/avatar, name, optional
    subtitle) plus the active lens's primary value with optional RAG
    tone. The adapter resolves these from the source row + the
    resolved `member_via` FK target; the primitive renders the typed
    shape. Domain-agnostic: pupils with year/form, sales reps with
    region/quarter, engineers with team/level, customers with plan
    tier — anything that fits 'avatar + identifier + secondary
    metadata + a swappable metric'."""

    member_id: str
    member_name: str
    primary_value: str
    subtitle: str = ""  # secondary identifier (year/form, region, plan tier, etc.)
    avatar_initials: str = ""
    tone: str = "neutral"  # neutral | good | warn | bad — RAG tint
    drill_url: str = ""
    # #1148: optional pre-rendered action button HTML (from
    # `_render_row_action_button`). Empty string means no action on
    # this cell — either the region has no `row_action:` or the
    # cell's `visible_when` evaluated falsy.
    action_html: str = ""

    def __post_init__(self) -> None:
        if not self.member_id:
            raise ValueError("CohortStripCell requires a non-empty member_id")


@dataclass(frozen=True, slots=True)
class CohortStripLensTab:
    """One tab in a `CohortStripRegion`'s lens toggle. The active tab
    gets the `is-active` class + `aria-pressed="true"`; clicks fire
    an HTMX swap to the same region endpoint with `?lens=<id>`."""

    id: str
    label: str
    is_active: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("CohortStripLensTab requires a non-empty id")


@dataclass(frozen=True, slots=True)
class CohortStripRegion:
    """Horizontal cohort-skim strip with lens toggle (#1018).

    The viewer picks a lens; the strip re-renders keeping the member
    row stable but rotating the visual primary. Lens-toggle clicks
    fire an HTMX swap to the region endpoint with `?lens=<id>`; the
    runtime re-resolves the data and the primitive re-renders.

    `region_name` is the region's stable id used in the swap target
    (`#region-{name}-body`). `endpoint` is the region data URL.
    `cells` is the resolved row of members for the active lens."""

    region_name: str
    endpoint: object  # URL — typed object to keep the union simple
    lenses: tuple[CohortStripLensTab, ...]
    cells: tuple[CohortStripCell, ...]
    empty_message: str = "No members in this view."

    def __post_init__(self) -> None:
        if not self.region_name:
            raise ValueError("CohortStripRegion requires a non-empty region_name")
        if not self.lenses:
            raise ValueError("CohortStripRegion requires at least one lens")
        active_count = sum(1 for lens in self.lenses if lens.is_active)
        if active_count != 1:
            raise ValueError(
                f"CohortStripRegion requires exactly one active lens, got {active_count}"
            )


@dataclass(frozen=True, slots=True)
class DayTimelineSlot:
    """One chronological slot in a `DayTimelineRegion` (#1016).

    Models a single calendar entry — typically a `TimetableSlot` — in
    the day spine. The adapter resolves `position` from the runtime
    clock against the IR's `starts_at`/`ends_at` fields: exactly one
    slot in a non-empty timeline is `"active"`; earlier slots are
    `"before"` (collapsed-summary), later slots are `"after"`
    (previewable, slightly de-emphasised)."""

    slot_id: str
    label: str  # e.g. "Period 3 — 11:30–12:25"
    position: Literal["before", "active", "after"] = "after"
    body: str = ""  # pre-rendered card body (escape responsibility on adapter)
    drill_url: str = ""
    # #1148: optional pre-rendered action button HTML (from
    # `_render_row_action_button`). Empty string means no action
    # button on this slot — either the region has no `row_action:`
    # or the slot's `visible_when` evaluated falsy. Adapter owns
    # escape responsibility (the helper does the HTML-escape).
    action_html: str = ""

    def __post_init__(self) -> None:
        if not self.slot_id:
            raise ValueError("DayTimelineSlot requires a non-empty slot_id")


@dataclass(frozen=True, slots=True)
class DayTimelineRegion:
    """Vertical chronological scroll of slots — the day spine (#1016).

    Renders one card per slot in chronological order (the adapter is
    responsible for sorting). The slot whose [starts_at, ends_at]
    window contains `now` is rendered with the active highlight; at
    most one such slot exists per timeline. When the day has no
    active slot (before-school / after-school / weekend), all slots
    render in their pre/post position relative to `now`.

    `region_name` matches the region's stable id; the active card's
    container carries `data-dz-position="active"` so project CSS can
    target it without DOM-walking."""

    region_name: str
    slots: tuple[DayTimelineSlot, ...]
    empty_message: str = "No scheduled slots today."

    def __post_init__(self) -> None:
        if not self.region_name:
            raise ValueError("DayTimelineRegion requires a non-empty region_name")
        active_count = sum(1 for slot in self.slots if slot.position == "active")
        if active_count > 1:
            raise ValueError(
                f"DayTimelineRegion permits at most one active slot, got {active_count}"
            )


@dataclass(frozen=True, slots=True)
class TaskInboxItem:
    """One typed task in a `TaskInboxRegion` (#1015).

    Resolved-and-rendered shape: the adapter has already applied the
    `as_task` template against a source row, mapped the icon token,
    classified the urgency, and resolved any drill_url. The primitive
    just renders the typed item."""

    item_id: str
    icon: str  # token resolved to icon class on the renderer side
    title: str
    meta: str = ""
    urgency: Literal["overdue", "due", "soon", "later"] = "later"
    drill_url: str = ""

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("TaskInboxItem requires a non-empty item_id")


@dataclass(frozen=True, slots=True)
class TaskInboxSummaryChip:
    """Collapsed-summary chip for a `count_as` source in a
    `TaskInboxRegion` (#1015). Renders one chip with the count + the
    source's `count_as` noun phrase, shown above the items list."""

    chip_id: str
    count: int
    label: str  # the resolved count_as phrase
    drill_url: str = ""

    def __post_init__(self) -> None:
        if not self.chip_id:
            raise ValueError("TaskInboxSummaryChip requires a non-empty chip_id")
        if self.count < 0:
            raise ValueError(f"TaskInboxSummaryChip count must be >= 0, got {self.count}")


@dataclass(frozen=True, slots=True)
class TaskInboxRegion:
    """Workflow-led task inbox — prioritised list of due actions
    drawn from heterogeneous entity states (#1015).

    `items` are per-row tasks (one per matching source row).
    `summary_chips` are collapsed-summary indicators for sources
    declared with `count_as`. The empty-state path fires only when
    BOTH lists are empty."""

    region_name: str
    items: tuple[TaskInboxItem, ...]
    summary_chips: tuple[TaskInboxSummaryChip, ...] = ()
    empty_message: str = "All caught up."

    def __post_init__(self) -> None:
        if not self.region_name:
            raise ValueError("TaskInboxRegion requires a non-empty region_name")


@dataclass(frozen=True, slots=True)
class EntityCardSection:
    """One resolved section in a `EntityCardRegion` (#1017).

    The runtime adapter has already queried the source, applied the
    mode-specific compact renderer, and produced the section's body
    HTML. The primitive just composes sections into the two-column
    layout — sections with `is_omitted=True` are not emitted at all
    (used when an optional section resolves zero rows)."""

    section_id: str
    label: str
    mode: Literal["halo", "flags", "mini_bars", "stamps", "thread_summary", "quick_actions"] = (
        "halo"
    )
    body: str = ""  # pre-rendered HTML — adapter owns escape responsibility
    column: Literal["main", "sidebar"] = "main"
    is_omitted: bool = False

    def __post_init__(self) -> None:
        if not self.section_id:
            raise ValueError("EntityCardSection requires a non-empty section_id")


@dataclass(frozen=True, slots=True)
class EntityCardRegion:
    """Composite 360° single-entity view — calibrated-density region
    primitive (#1017). Domain-agnostic: pupil-360 in MIS,
    customer-360 in CRM, asset-360 in field-ops, patient-360 in
    healthcare etc. The runtime adapter resolves the entity
    instance; this primitive composes the resolved sections.

    Two-column responsive layout (main + sidebar via project CSS).
    On narrow widths the layout collapses to a single column; the
    primitive emits stable column markers so project CSS owns the
    breakpoint. Sections with `is_omitted=True` are skipped — the
    adapter sets that flag on optional sections that resolved zero
    rows (e.g. no recent activity stream entries)."""

    region_name: str
    sections: tuple[EntityCardSection, ...]
    record_label: str = ""  # for the region's heading; "" = adapter omits

    def __post_init__(self) -> None:
        if not self.region_name:
            raise ValueError("EntityCardRegion requires a non-empty region_name")
