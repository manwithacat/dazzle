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
