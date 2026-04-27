"""
Workspace types for DAZZLE IR.

This module contains workspace specifications for composing related
information needs into cohesive user experiences.
"""

from __future__ import annotations  # required: forward reference

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .conditions import ConditionExpr
from .location import SourceLocation
from .params import ParamRef
from .ux import SortSpec, UXSpec


class WorkspaceAccessLevel(StrEnum):
    """Access levels for workspaces."""

    PUBLIC = "public"  # No authentication required
    AUTHENTICATED = "authenticated"  # Any logged-in user
    PERSONA = "persona"  # Specific personas only


class WorkspaceAccessSpec(BaseModel):
    """
    Access control specification for workspaces.

    Defines authentication and authorization requirements for accessing a workspace.
    Default is deny (authenticated required) when auth is enabled globally.

    Attributes:
        level: Access level (public, authenticated, persona)
        allow_personas: List of personas that can access (when level=persona)
        deny_personas: List of personas explicitly denied access
        redirect_unauthenticated: Where to redirect unauthenticated users
    """

    level: WorkspaceAccessLevel = WorkspaceAccessLevel.AUTHENTICATED
    allow_personas: list[str] = Field(default_factory=list)
    deny_personas: list[str] = Field(default_factory=list)
    redirect_unauthenticated: str = "/login"

    model_config = ConfigDict(frozen=True)


class DisplayMode(StrEnum):
    """Display modes for workspace regions."""

    LIST = "list"
    GRID = "grid"
    TIMELINE = "timeline"
    MAP = "map"
    DETAIL = "detail"  # v0.3.1: Single item detail view
    SUMMARY = "summary"  # v0.9.5: Metrics/KPI summary cards
    METRICS = "metrics"  # v0.9.5: Alias for summary
    KANBAN = "kanban"  # v0.9.5: Kanban board view for workflows
    BAR_CHART = "bar_chart"  # v0.9.5: Bar chart visualization
    FUNNEL_CHART = "funnel_chart"  # v0.9.5: Funnel chart (e.g., sales pipeline)
    QUEUE = "queue"  # v0.33.0: Review queue with inline actions
    TABBED_LIST = "tabbed_list"  # v0.33.0: Tabbed multi-source list
    HEATMAP = "heatmap"  # v0.44.0: Heat-map matrix view
    DIAGRAM = "diagram"  # v0.48.15: Entity relationship diagram
    PROGRESS = "progress"  # v0.44.0: Progress bar view
    ACTIVITY_FEED = "activity_feed"  # v0.44.0: Activity feed / timeline display
    TREE = "tree"  # v0.44.0: Tree / hierarchy display
    PIVOT_TABLE = "pivot_table"  # v0.59.3: Multi-dimension cross-tab view (cycle 25)
    LINE_CHART = "line_chart"  # v0.60.0: Time-series line chart (cycle 28)
    AREA_CHART = "area_chart"  # v0.60.0: Stacked time-series area chart (cycle 28)
    SPARKLINE = "sparkline"  # v0.60.0: Compact line for KPI tiles (cycle 28)
    HISTOGRAM = "histogram"  # v0.61.27 (#882): continuous-variable distribution
    RADAR = "radar"  # v0.61.28 (#879): polar/radar profile shape
    BOX_PLOT = "box_plot"  # v0.61.29 (#881): per-group quartile spread
    BULLET = "bullet"  # v0.61.30 (#880): actual-vs-target rows with bands
    BAR_TRACK = "bar_track"  # v0.61.53 (#893): per-row label + filled track + value
    ACTION_GRID = "action_grid"  # v0.61.54 (#891): CTA cards on dashboards
    PROFILE_CARD = "profile_card"  # v0.61.55 (#892): single-record identity panel
    PIPELINE_STEPS = "pipeline_steps"  # v0.61.56 (#890): sequential-stage workflow


class BucketRef(BaseModel):
    """A time-bucketed group-by dimension.

    Produced by the parser for the DSL form ``bucket(<field>, <unit>)``.
    Downstream, the workspace runtime maps this into a
    ``Dimension(truncate=<unit>)`` on the aggregate primitive, which
    emits ``date_trunc('<unit>', <col>)`` in SQL.

    Units are whitelisted — only the five literals below are valid.

    Attributes:
        field: Timestamp column on the source entity to bucket by.
        unit: Calendar granularity. One of day/week/month/quarter/year.
    """

    field: str
    unit: str  # "day" | "week" | "month" | "quarter" | "year"

    model_config = ConfigDict(frozen=True)


class ReferenceLine(BaseModel):
    """v0.61.26 (#883): horizontal reference line on a line/area chart.

    A flat horizontal marker at a fixed y-value. Used for target lines,
    grade-boundary lines, threshold markers — anything the data series
    should be read against.

    Attributes:
        label: Human-readable label for the line (rendered as a tooltip
            on the line and as a legend entry).
        value: Y-axis value where the line is drawn.
        style: Stroke style — ``solid`` (default) | ``dashed`` | ``dotted``.
    """

    label: str
    value: float
    style: str = Field(default="solid")

    model_config = ConfigDict(frozen=True)


class ReferenceBand(BaseModel):
    """v0.61.26 (#883): horizontal shaded band on a line/area chart.

    A filled rectangle spanning a y-axis range. Used for target bands,
    acceptable-range markers, RAG-style threshold zones.

    Attributes:
        label: Human-readable label for the band.
        from_value: Lower y-axis value (alias ``from`` in DSL — Pydantic
            field name uses ``from_value`` since ``from`` is a Python
            keyword).
        to_value: Upper y-axis value.
        color: Token-driven colour — ``target`` (primary tint, default) |
            ``positive`` (green) | ``warning`` (amber) | ``destructive``
            (red) | ``muted`` (gray). Maps to design tokens at render time.
    """

    label: str
    from_value: float = Field(alias="from")
    to_value: float = Field(alias="to")
    color: str = Field(default="target")

    model_config = ConfigDict(frozen=True, populate_by_name=True)


class OverlaySeriesSpec(BaseModel):
    """v0.61.33 (#883): an additional data series on a line/area chart.

    Each overlay series is fully specified — its own ``source`` (defaults
    to the parent region's source when omitted), its own ``filter`` (a
    parsed ``ConditionExpr``), and its own single aggregate expression
    (e.g. ``avg(scaled_mark)``). The runtime fires ONE extra
    ``_compute_bucketed_aggregates`` call per overlay using the parent
    region's ``group_by``, then the chart template renders the result as
    an additional polyline / stacked layer.

    Attributes:
        label: Human-readable series name shown in the legend.
        source: Optional source entity override. ``None`` means "use the
            parent region's source".
        filter: Optional ``ConditionExpr`` for the overlay's own scope
            (e.g. cohort vs individual student).
        aggregate_expr: A single aggregate expression string —
            ``count(<Entity>)`` / ``avg(<col>)`` / ``sum(<col>)`` etc.
            Same vocabulary as the region's ``aggregate:`` block; one
            measure per overlay series.
    """

    label: str
    source: str | None = None
    filter: ConditionExpr | None = None
    aggregate_expr: str

    model_config = ConfigDict(frozen=True)


class PipelineStageSpec(BaseModel):
    """v0.61.56 (#890): one stage in a pipeline_steps region.

    Each stage has a label (the kicker), an optional caption (sub-text
    under the headline number), and an aggregate expression that fires
    independently — RBAC scope rules apply per-stage. Stages are
    ordered left-to-right (or top-to-bottom on mobile).

    Attributes:
        label: Human-readable stage name (e.g. "Scanned", "Rubric pass").
        caption: Optional sub-text describing what's at this stage.
        aggregate_expr: A single aggregate expression — same vocabulary
            as region-level ``aggregate:``: ``count(<Entity> where <pred>)``,
            ``avg(<col>)``, etc. Empty string means no value (renders as
            ``—``).
    """

    label: str
    caption: str = ""
    aggregate_expr: str = ""

    model_config = ConfigDict(frozen=True)


class ProfileCardStatSpec(BaseModel):
    """v0.61.55 (#892): one stat in a profile_card's stat grid.

    Attributes:
        label: Human-readable stat label (e.g. "Target", "Projected").
        value: Field name (or dotted path) on the source row to render.
            The runtime resolves the path against the fetched item dict
            and renders the resulting value verbatim.
    """

    label: str
    value: str

    model_config = ConfigDict(frozen=True)


class ActionCardSpec(BaseModel):
    """v0.61.54 (#891): one CTA card in an action_grid region.

    Each card carries a label, optional icon (Lucide name), an optional
    count_aggregate (counted per-card via the existing aggregate
    machinery), an action surface name (resolved to URL at render time),
    and a tone token mapping to the design palette.

    Attributes:
        label: Human-readable CTA text rendered prominently on the card.
        icon: Lucide icon name (e.g. "file-text", "clipboard-check"). Empty
            string means no icon.
        count_aggregate: Optional aggregate expression — ``count(<Entity>
            where <pred>)`` / ``avg(<col>)`` etc. Same vocabulary as
            region-level ``aggregate:``. Empty string means no count badge.
        action: Surface name to navigate to on click — same resolution
            path as region-level ``action:``. Empty string means no
            click-through (informational card).
        tone: Palette token — ``positive`` / ``warning`` / ``destructive``
            / ``neutral`` / ``accent``. Defaults to ``neutral``.
    """

    label: str
    icon: str = ""
    count_aggregate: str = ""
    action: str = ""
    tone: str = "neutral"

    model_config = ConfigDict(frozen=True)


class DeltaSpec(BaseModel):
    """v0.61.25 (#884): period-over-period delta config for summary/metrics tiles.

    Attributes:
        period_seconds: Length of the comparison window in seconds. Computed
            from the parsed period (`1 day` → 86400). Current window =
            `[now() - period, now()]`; prior window =
            `[now() - 2*period, now() - period]`.
        sentiment: One of ``positive_up`` | ``positive_down`` | ``neutral``.
            Drives the colour of the delta arrow at render time.
        date_field: Entity column the windows filter on. Defaults to
            ``created_at`` if the entity has it; otherwise must be set
            explicitly.
        period_label: Human-readable label for the prior-window comparison
            (e.g. ``"yesterday"`` for `1 day`, ``"last week"`` for `7 days`).
            Used in the rendered ``vs <label>`` suffix.
    """

    period_seconds: int = Field(..., ge=1)
    sentiment: str = Field(default="positive_up")
    date_field: str | None = None
    period_label: str = Field(default="prior period")

    model_config = ConfigDict(frozen=True)


class WorkspaceRegion(BaseModel):
    """
    Named region within a workspace.

    A region displays data from a source entity or surface with optional
    filtering, sorting, and display customization.

    Attributes:
        name: Region identifier
        source: Entity or surface name to source data from (optional for aggregate-only regions)
        filter: Optional filter expression
        sort: Optional sort specification
        limit: Maximum records to display
        display: Display mode (list, grid, timeline, map)
        action: Surface for quick action on items
        empty_message: Message when no data
        group_by: Field to group data by for aggregation
        aggregates: Named aggregate expressions

    v0.9.5: source is now optional for aggregate-only metric regions
    """

    name: str
    source: str | None = None  # Entity or surface name (optional for aggregate-only)
    sources: list[str] = Field(default_factory=list)  # v0.33.0: Multi-source entity list
    source_filters: dict[str, ConditionExpr] = Field(
        default_factory=dict
    )  # v0.33.0: Per-source filters
    filter: ConditionExpr | None = None
    sort: list[SortSpec] = Field(default_factory=list)
    limit: int | None = Field(None, ge=1, le=1000)
    display: DisplayMode = DisplayMode.LIST
    action: str | None = None  # Surface reference
    empty_message: str | None = None
    group_by: str | BucketRef | None = None  # Field or bucket() ref (single dim)
    # v0.59.3 (cycle 25): multi-dimension group_by for pivot_table /
    # cross-tab views. When set, the runtime composes a multi-dim
    # GROUP BY via Repository.aggregate. Each entry is a column name on
    # the source entity, or a v0.60.0 BucketRef for time-bucketed dims;
    # FK columns auto-LEFT JOIN their target so the bucket carries the
    # resolved display field. Mutually exclusive with group_by — when
    # both are set, group_by_dims wins.
    group_by_dims: list[str | BucketRef] | None = None
    aggregates: dict[str, str] = Field(default_factory=dict)  # metric_name: expr
    # v0.34.0: Date-range filtering
    date_field: str | None = None
    date_range: bool = False  # Enable date picker on this region
    # v0.44.0: Heatmap configuration
    heatmap_rows: str | None = None  # FK field for row grouping
    heatmap_columns: str | None = None  # FK field for column grouping
    heatmap_value: str | None = None  # Expression for cell value
    heatmap_thresholds: list[float] | ParamRef = Field(
        default_factory=list
    )  # e.g. [0.4, 0.6] for RAG
    # v0.44.0: Progress bar configuration
    progress_stages: list[str] = Field(default_factory=list)  # ordered status values
    progress_complete_at: str | None = None  # which stage means "done"
    # v0.61.25 (#884): Period-over-period delta for summary/metrics tiles.
    # When set, the runtime computes a prior-window aggregate alongside the
    # current one and the metrics template renders an arrow + delta + pct.
    delta: DeltaSpec | None = None
    # v0.61.26 (#883): Reference lines + shaded bands on line/area charts.
    # Pure template overlay — no extra DB queries.
    reference_lines: list[ReferenceLine] = Field(default_factory=list)
    reference_bands: list[ReferenceBand] = Field(default_factory=list)
    # v0.61.27 (#882): Histogram-mode bin count.
    # ``None`` means "auto" (Sturges' rule: ⌈log2(N) + 1⌉). A positive int
    # forces N equal-width bins. Histograms read ``heatmap_value`` for the
    # value column to bin (it's a generic "the value to plot" field, just
    # legacy-named — rename deferred to keep this patch focused).
    bin_count: int | None = None
    # v0.61.29 (#881): Box plot — render outlier dots (points outside
    # Tukey fences [Q1 - 1.5*IQR, Q3 + 1.5*IQR]). Default True; set False
    # for a clean compact view that omits the dots.
    show_outliers: bool = True
    # v0.61.30 (#880): Bullet chart — column names on each item that
    # provide the row label, the actual bar length, and the target tick.
    # The bullet template renders one row per item, with `reference_bands`
    # (#883) drawn behind as comparative qualitative zones. Pre-computed
    # MVP — extension to per-group_by aggregates deferred (would need
    # multi-measure support in `_compute_bucketed_aggregates`).
    bullet_label: str | None = None
    bullet_actual: str | None = None
    bullet_target: str | None = None
    # v0.61.33 (#883): line/area chart overlay series — additional
    # polylines/stacked layers driven by their own source/filter/aggregate.
    # Each overlay fires one extra `_compute_bucketed_aggregates` call.
    overlay_series: list[OverlaySeriesSpec] = Field(default_factory=list)
    # v0.61.52 (#894): project-supplied CSS class on the region's outer
    # wrapper. DSL keyword is `class:` (matches HTML); IR field name is
    # `css_class` to avoid the Python keyword. Multiple classes
    # space-separated. Pure presentation hook — no impact on data,
    # scope, or semantics.
    css_class: str | None = None
    # v0.61.60: kicker line rendered ABOVE the region's title in the
    # dashboard-slot panel header. Establishes the AegisMark "eyebrow /
    # title / copy" header convention as a first-class field. Pure
    # presentation; no impact on data or semantics. See
    # `dev_docs/2026-04-27-aegismark-ux-patterns.md` item #1.
    eyebrow: str | None = None
    # v0.61.63 (#903): explicit region title override. When set, replaces
    # the auto-derived title from the region key (e.g. `hero_marked` →
    # "Hero Marked"). Empty string is treated as None — the runtime
    # falls back to the auto-derived title. Pure presentation hook.
    title: str | None = None
    # v0.61.53 (#893): bar_track display config — per-row horizontal
    # value bar. Reuses `group_by` for the row dimension and
    # `aggregates` for the bar value (single-dim chart pipeline). These
    # two fields are bar_track-specific:
    #   track_max — denominator for the fill ratio. None means "auto"
    #     (max of the bucketed values).
    #   track_format — Python format spec applied to the value for the
    #     right-side numeric (e.g. "{:.0%}", "{:,.0f}"). None means raw
    #     str() of the value.
    track_max: float | None = None
    track_format: str | None = None
    # v0.61.54 (#891): action_grid CTA cards. Each entry is fully
    # specified — label / icon / count_aggregate / action / tone. The
    # runtime fires one count query per card with a non-empty
    # `count_aggregate`. Empty list = legacy behaviour (no cards).
    action_cards: list[ActionCardSpec] = Field(default_factory=list)
    # v0.61.55 (#892): profile_card single-record display config. All
    # fields default to empty/None so non-profile_card regions are
    # unaffected. The `secondary` and `facts` strings support tiny
    # `{{ field }}` / `{{ field.path }}` interpolation against the
    # fetched item dict — no Jinja eval, no expressions.
    avatar_field: str | None = None
    primary: str | None = None
    secondary: str | None = None
    profile_stats: list[ProfileCardStatSpec] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    # v0.61.56 (#890): pipeline_steps sequential-stage display.
    # Each stage fires its own aggregate query; renders as a left-to-right
    # row of stage cards with arrow connectors. Empty list = legacy
    # behaviour (no stages).
    pipeline_stages: list[PipelineStageSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class NavItemIR(BaseModel):
    """A navigation item within a workspace or nav group.

    Attributes:
        entity: Entity or workspace name to link to
        icon: Optional Lucide icon name (e.g., "file-text", "check-circle")
    """

    entity: str
    icon: str | None = None

    model_config = ConfigDict(frozen=True)


class NavGroupSpec(BaseModel):
    """A collapsible navigation group within a workspace.

    Attributes:
        label: Display label for the group header
        icon: Optional Lucide icon name for the group header
        collapsed: Whether the group starts collapsed (default: False)
        items: Navigation items within this group
    """

    label: str
    icon: str | None = None
    collapsed: bool = False
    items: list[NavItemIR] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class ContextSelectorSpec(BaseModel):
    """Specifies a context selector dropdown for a workspace.

    Allows trust-level users to pick a scope (e.g., school) that filters
    all regions.  The selected value is available as ``current_context``
    in filter expressions.

    Attributes:
        entity: Entity name to select from (e.g., "School")
        display_field: Field to show in dropdown (default: "name")
        scope_field: Optional FK field on the entity to restrict choices
            to the current user's scope (e.g., "trust" to filter by
            the user's trust).
    """

    entity: str
    display_field: str = "name"
    scope_field: str | None = None

    model_config = ConfigDict(frozen=True)


class WorkspaceSpec(BaseModel):
    """
    Composition of related information needs.

    A workspace brings together multiple data views into a cohesive
    user experience, typically representing a role-specific dashboard.

    Attributes:
        name: Workspace identifier
        title: Human-readable title
        purpose: Why this workspace exists
        stage: Layout stage hint (e.g., "focus_metric", "dual_pane_flow", "command_center")
        regions: List of data regions in the workspace
        ux: Optional workspace-level UX customization
        access: Access control specification (v0.22.0)
        context_selector: Optional context selector for multi-scope users (v0.38.0)
    """

    name: str
    title: str | None = None
    purpose: str | None = None
    stage: str | None = None  # v0.8.0: Layout stage (formerly engine_hint)
    regions: list[WorkspaceRegion] = Field(default_factory=list)
    nav_groups: list[NavGroupSpec] = Field(default_factory=list)  # v0.38.0: Collapsible nav groups
    ux: UXSpec | None = None  # Workspace-level UX (e.g., persona variants)
    access: WorkspaceAccessSpec | None = None  # v0.22.0: Access control
    context_selector: ContextSelectorSpec | None = None  # v0.38.0
    # v0.31.0: Source location for error reporting
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)

    def get_region(self, name: str) -> WorkspaceRegion | None:
        """Get region by name."""
        for region in self.regions:
            if region.name == name:
                return region
        return None
