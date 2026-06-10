"""
Workspace types for DAZZLE IR.

This module contains workspace specifications for composing related
information needs into cohesive user experiences.
"""

from __future__ import annotations  # required: forward reference

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .aggregates import AggregateRef, DerivedMetric
from .conditions import ConditionExpr, ViaCondition
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
    STATUS_LIST = "status_list"  # v0.61.69 (#7): vertical icon + title + copy + state-pill list
    CONFIRM_ACTION_PANEL = (
        "confirm_action_panel"  # v0.61.72 (#6): irreversible-action consent panel
    )
    SEARCH_BOX = "search_box"  # #954 cycle 4: htmx search input + ranked results
    # AegisMark Day-One demo region primitives (#1015–#1018).
    # Currently driven by `cohort_strip_config` / `task_inbox_config` /
    # `day_timeline_config` / `entity_card_config` typed config blocks
    # on WorkspaceRegion — discriminated by the `display` value here.
    COHORT_STRIP = "cohort_strip"  # #1018: cohort-skim with lens toggle
    DAY_TIMELINE = "day_timeline"  # #1016: chronological MIS landing
    TASK_INBOX = "task_inbox"  # #1015: workflow-led landing surface
    ENTITY_CARD = "entity_card"  # #1017: 360° single-entity drill-down composite


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
        aggregate: A typed :class:`AggregateRef` driving the overlay's
            single measure. Same vocabulary as the region's
            ``aggregate:`` block; one measure per overlay series.
            ADR-0024.
    """

    label: str
    source: str | None = None
    filter: ConditionExpr | None = None
    aggregate: AggregateRef

    model_config = ConfigDict(frozen=True)


class PipelineStageSpec(BaseModel):
    """v0.61.56 (#890): one stage in a pipeline_steps region.

    Each stage has a label (the kicker), an optional caption (sub-text
    under the headline number), and a value — either an aggregate
    expression OR a literal string. Aggregate expressions fire
    independently per stage with RBAC scope rules applied. Literal
    strings render verbatim (used for descriptive flow labels — e.g.
    "Daily 02:00 UTC", "Manual review"). Stages are ordered
    left-to-right (or top-to-bottom on mobile).

    v0.61.78 (#911) added per-stage progress: turns the menu-shape into
    a thermometer-shape so operators see how complete each stage is,
    not just whether anything is in it. Same expression vocabulary as
    `value:` — either a literal number string or an aggregate. Clamped
    to 0-100 at render time.

    Attributes:
        label: Human-readable stage name (e.g. "Scanned", "Rubric pass").
        caption: Optional sub-text describing what's at this stage.
        value: Either a typed :class:`AggregateRef` (fires a query) OR a
            literal string (rendered verbatim — used for descriptive flow
            labels like "Daily 02:00 UTC"). ``None`` means no value
            (renders as ``—``). Per ADR-0024 the parser shape-detects on
            the token stream — if the next tokens form an aggregate call,
            ``parse_aggregate_ref()`` consumes them; otherwise the input
            is captured as a literal string.
        progress: Per-stage progress bar fraction (0-100). Same union
            shape as ``value:``. ``None`` means no bar rendered.
            Clamped to 0-100 at render time; values >100 set
            ``data-dz-progress-overshoot="true"`` so themes can flag.
    """

    label: str
    caption: str = ""
    value: AggregateRef | str | None = None
    progress: AggregateRef | str | None = None

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
        count: Optional :class:`AggregateRef` driving the count badge —
            same vocabulary as any other aggregate consumer (ADR-0024).
            ``None`` means no count badge. DSL key remains
            ``count_aggregate:`` for familiarity.
        action: Surface name to navigate to on click — same resolution
            path as region-level ``action:``. Empty string means no
            click-through (informational card).
        tone: Palette token — ``positive`` / ``warning`` / ``destructive``
            / ``neutral`` / ``accent``. Defaults to ``neutral``.
    """

    label: str
    icon: str = ""
    count: AggregateRef | None = None
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


class StatusListEntrySpec(BaseModel):
    """v0.61.69 (#3): one entry in a status_list region.

    Each entry is an icon + title + secondary copy + state pill —
    the canonical row shape for AegisMark's "agreement card",
    "schedule grid", and "scope grid" patterns. Authored as a static
    list (this initial cycle); a source-bound variant that maps
    entity rows to entries is deferred per the roadmap.

    Attributes:
        title: Strong primary line — the entry headline.
        caption: Secondary descriptive line. Empty string omits the
            line. Field name matches `PipelineStageSpec.caption` for
            consistency across components — and dodges `copy` which
            shadows Pydantic's deprecated `BaseModel.copy()` method.
        icon: Lucide icon name (e.g. "check-circle", "clock"). Empty
            string omits the icon column.
        state: Pill state token — same vocabulary as action_grid /
            metrics / notice tones (``positive`` / ``warning`` /
            ``destructive`` / ``accent`` / ``neutral``). Defaults to
            ``neutral``. Empty string also resolves to ``neutral``.
    """

    title: str
    caption: str = ""
    icon: str = ""
    state: str = "neutral"

    model_config = ConfigDict(frozen=True)


class ConfirmationItemSpec(BaseModel):
    """v0.61.72 (#6): one row in a confirm_action_panel `confirmations:` block.

    The AegisMark "Final authorisation" panel uses a checklist of
    obligations the actor must affirm before the irreversible action
    (e.g. ``Enable live SIMS sync``) becomes available. Required
    items must all be ticked for the primary action to enable;
    optional items are advisory.

    Attributes:
        title: The check-row's strong line (e.g.
            ``"I confirm the school has signed the DPA"``).
        caption: Optional secondary line for context. Empty omits.
        required: When True (default), the primary action stays
            disabled until this row is ticked. When False, the row
            is informational only.
    """

    title: str
    caption: str = ""
    required: bool = True

    model_config = ConfigDict(frozen=True)


class RowActionSpec(BaseModel):
    """#1148: per-row click-to-POST action on row-oriented region displays.

    Closes the "every workflow surface needs a custom Python route for
    its primary per-row action" gap that overrides in AegisMark, the
    Manuscript review queue, the Behaviour incident inbox, and the
    Fastmark starter-pack picker all worked around. One typed block
    covers `list`, `cohort_strip`, `day_timeline`, and `status_list`
    rows — `action_id` resolves against the project's declared
    surface actions (same machinery `entity_card.quick_actions` uses
    at the card level), CSRF + route binding inherited.

    Attributes:
        label: Button copy shown on each row (e.g. "Approve & release").
        action_id: Reference to a declared surface action. The runtime
            resolves the POST URL via the same machinery as
            ``entity_card.quick_actions`` — projects don't manage
            URLs by hand.
        bind: Row-field → action-arg mapping. The simple case is
            ``{id: id}`` (row's id → action's id param). Multi-key
            forms compose URL-encoded bodies. Empty dict means the
            action takes no row-derived args.
        visible_when: Optional per-row predicate. When set, the row's
            action button only renders when the condition evaluates
            truthy against the row dict (e.g. ``status != released``
            hides the button on already-released rows). ``None`` =
            always visible.
        confirm: Optional confirmation step that pops a panel before
            the POST fires. Reuses the v0.61.72 (#1072)
            confirm_action_panel item shape — same shape across the
            framework. ``None`` = no confirmation (action fires
            immediately on click).
    """

    label: str
    action_id: str
    bind: dict[str, str] = Field(default_factory=dict)
    visible_when: ConditionExpr | None = None
    confirm: ConfirmationItemSpec | None = None

    model_config = ConfigDict(frozen=True)


class NoticeSpec(BaseModel):
    """v0.61.68: prominent notice band rendered above the region body
    inside the dashboard slot. AegisMark's SIMS-sync-opt-in prototype
    uses notices for legal-basis disclosure, status banners, and
    consent context — strong line + secondary copy with a tone tint.

    Authors declare a notice region-side (per-region, not per-card)
    and the framework renders it as a horizontal band between the
    panel header and the data body. Pure presentation hook — no
    impact on data, scope, or aggregates. AegisMark UX patterns
    roadmap item #7.

    Attributes:
        title: Strong primary line — the headline of the notice.
        body: Optional secondary line — the explanation. Empty string
            means single-line notice.
        tone: Palette token — ``positive`` / ``warning`` / ``destructive``
            / ``accent`` / ``neutral``. Reuses the action_grid +
            metrics tones vocabulary so the visual language stays
            consistent across components. Defaults to ``neutral``
            (subtle muted band).
    """

    title: str
    body: str = ""
    tone: str = "neutral"

    model_config = ConfigDict(frozen=True)


class LensAggregatePrimary(BaseModel):
    """#1144 Gap 1 / part 3: aggregate-expression primary for
    cohort_strip lenses.

    Pre-fix `primary:` could only name a field already on the
    resolved member record. Cross-entity metrics (attainment %
    across `MarkingResult` rows joined through `ClassEnrolment`,
    behaviour counts in a 7-day window, MRR per CRM cohort, etc.)
    forced a Python route override. This shape lets a lens declare
    an aggregate expression evaluated by the framework's
    ``Repository.aggregate`` machinery, joined through an optional
    junction table, filtered by an optional predicate.

    **Runtime status:** fully wired. ``compute_cohort_aggregate_primary``
    in ``workspace_region_computes.py`` dispatches to one of three
    batched helpers depending on the link strategy (direct FK, true
    junction via :class:`ViaCondition`, or shared parent via ``share``).
    All three execute a single ``GROUP BY`` query per region — no N+1,
    no enumeration.

    Attributes:
        aggregate: Typed :class:`AggregateRef` driving the lens
            computation. Any of the three AggregateRef shapes work:
            ``count(Entity)``, ``avg(column)``, ``avg(Entity.column)``.
            Row-level predicates ride inside the AggregateRef's own
            ``where:`` clause (ADR-0024).
        via: Optional junction-table join. Reuses the
            :class:`ViaCondition` shape from #530 — same parser, same
            SQL compiler. ``None`` means no junction (aggregate
            operates against the source-entity directly, scoped by
            the member's FK relationship). Mutually exclusive with
            ``share`` (parse-time refusal).
        share: Optional shared-parent join (#1216). Names a pivot
            entity that both the cohort source row and the aggregated
            row reference via a single ``ref`` field each. Mutually
            exclusive with ``via``.
        format: Optional Python format spec applied to the computed
            aggregate value when rendering the cell (#1300). Mirrors
            bar_track's ``track_format``: a bare format spec (``".1f"``,
            ``".0%"``) or a ``str.format`` template (``"{:,.2f}"``).
            Empty (default) → the renderer applies a sensible numeric
            default-round (2dp, trailing zeros trimmed) so an ``avg``
            lens never emits a raw float like ``7.7500000000000000``.
    """

    aggregate: AggregateRef
    via: ViaCondition | None = None
    # #1216: shared-parent JOIN. When the cohort source row and the
    # aggregated entity both reference the same parent entity (the
    # "pivot") but don't FK to each other, `share` names that parent.
    # Semantics: "for each cohort row, aggregate rows that reference
    # the SAME pivot entity as the cohort row does." Mutually
    # exclusive with `via:` (true-junction semantics) — set one or
    # the other, never both.
    share: str | None = None
    # #1300: per-lens render format for the aggregate value. Empty →
    # default-round in the renderer (_default_round_numeric).
    format: str = ""

    model_config = ConfigDict(frozen=True)


class CompositePrimaryPart(BaseModel):
    """#1144 part 2: one part of a composite cohort_strip primary.

    Lets a lens render tuple metrics — e.g. AO1/AO2/AO3 breakdown
    as ``45 / 52 / 38`` in one cell, or +pos/-neg behaviour
    counters as ``+12 / -3`` side-by-side. Each part resolves to
    a single row-field value at render time (matching the existing
    `primary: <field>` semantics, just one slot of a multi-value
    composite).

    Attributes:
        field: Field name on the resolved member record (same
            resolution rules as `CohortStripLens.primary` for the
            scalar case).
        tone: Optional palette token applied to this part only
            (``good`` / ``warn`` / ``bad`` / ``neutral`` / ``accent``).
            Useful for the +pos green / -neg red case — different
            parts of the same composite carry different tints.
            Empty means inherit the cell-level tone.
    """

    field: str
    tone: str = ""

    model_config = ConfigDict(frozen=True)


class CompositePrimarySpec(BaseModel):
    """#1144 part 2: composite primary for cohort_strip lenses.

    Renders a tuple of values joined by a separator instead of a
    single scalar — matches the ``45 / 52 / 38`` AO breakdown or
    ``+12 / -3`` behaviour counter shape.

    The renderer resolves each part's ``field`` against the row,
    converts to string (empty for missing/None — graceful
    degradation), and joins with ``separator``. When any part
    declares a ``tone``, the renderer emits per-part spans so CSS
    can tint each value independently.

    Attributes:
        parts: Ordered list of value slots. Empty list is rejected
            (use the scalar ``primary:`` form for a single value).
        separator: String inserted between rendered parts.
            Defaults to ``" / "`` matching the AegisMark contract.
    """

    parts: list[CompositePrimaryPart]
    separator: str = " / "

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _validate_non_empty(self) -> CompositePrimarySpec:
        if not self.parts:
            raise ValueError(
                "CompositePrimarySpec requires at least one part — "
                "use the scalar `primary:` form for a single value."
            )
        return self


class ToneBandSpec(BaseModel):
    """#1144 part 1: one tone band on a ``cohort_strip`` lens.

    Multi-band threshold replacement for the scalar `threshold:`
    field — gives DSL authors explicit control over the value→tone
    mapping instead of inheriting the hardcoded "≥threshold = good,
    ≥90% threshold = warn, else bad" trichotomy.

    A band fires when ``value >= at`` AND no earlier band (higher
    ``at`` value, evaluated first) already matched. Bands are
    walked in *descending* order of ``at`` regardless of authoring
    order — the renderer sorts them — so the highest threshold
    a value clears determines its tone.

    Attributes:
        at: Threshold value the row's primary must clear. Float so
            percentages, scores, and absolute counts all compose.
        tone: Palette token from the framework's tone vocabulary
            (``good`` / ``warn`` / ``bad`` / ``neutral`` / ``accent``
            etc) — same set the existing scalar-threshold path uses.
    """

    at: float
    tone: str

    model_config = ConfigDict(frozen=True)


class CohortStripLens(BaseModel):
    """One lens in a `cohort_strip` region's lens toggle (#1018).

    The viewer picks a lens; the strip re-renders keeping the member
    row stable but rotating the visual primary. Each lens names the
    field on the source-FK target (typically a profile entity
    carrying name + avatar + secondary metadata) that supplies the
    primary value.

    Attributes:
        id: Stable identifier used in the lens-swap URL parameter
            (`?lens=<id>`) and in the active-lens highlight contract.
        label: Human-readable text on the lens-toggle button.
        primary: Field on the resolved member record that supplies
            the value rendered as the visual primary.
        threshold: Optional scalar RAG threshold. When set (and
            ``tone_bands`` is empty), the renderer tints the primary
            value relative to it via the hardcoded above/warn/below
            trichotomy. Mutually exclusive with ``tone_bands``.
        tone_bands: Optional multi-band tone mapping (#1144 part 1).
            When non-empty, supersedes ``threshold:`` — the row's
            primary value is matched against the highest band whose
            ``at`` it clears. Empty list → fall back to ``threshold:``
            (or neutral if neither is set).
        primary_composite: Optional tuple-display primary (#1144
            part 2). When set, supersedes the scalar ``primary``
            field — the renderer resolves each part's field against
            the row and joins them with the spec's separator. Use
            this for AO breakdowns (``45 / 52 / 38``) or +pos/-neg
            counters (``+12 / -3``). Mutually exclusive with a
            non-empty ``primary``; setting both is a parse-time
            error.
        primary_aggregate: Optional aggregate-expression primary
            (#1144 part 3). When set, supersedes the scalar
            ``primary`` and ``primary_composite`` — the framework's
            ``Repository.aggregate`` machinery computes the value
            against the joined entity per member. Mutually exclusive
            with both scalar and composite forms.
    """

    id: str
    label: str
    primary: str = ""
    threshold: float | None = None
    tone_bands: list[ToneBandSpec] = Field(default_factory=list)
    primary_composite: CompositePrimarySpec | None = None
    primary_aggregate: LensAggregatePrimary | None = None

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _validate_threshold_or_bands(self) -> CohortStripLens:
        """#1144 parts 1/2/3: mutual-exclusion validators.

        - ``threshold:`` and ``tone_bands:`` can't both be set.
        - Exactly one of ``primary:`` / ``primary_composite:`` /
          ``primary_aggregate:`` must carry a value. All-empty
          rejects; more-than-one-set rejects.
        """
        if self.threshold is not None and self.tone_bands:
            raise ValueError(
                f"cohort_strip lens {self.id!r}: `threshold:` and "
                "`tone_bands:` are mutually exclusive — use one or "
                "the other (tone_bands supersedes the scalar)."
            )
        primary_forms = [
            ("primary", bool(self.primary)),
            ("primary_composite", self.primary_composite is not None),
            ("primary_aggregate", self.primary_aggregate is not None),
        ]
        set_forms = [name for name, present in primary_forms if present]
        if len(set_forms) > 1:
            raise ValueError(
                f"cohort_strip lens {self.id!r}: {', '.join(set_forms)} "
                "are mutually exclusive — use exactly one primary form."
            )
        if not set_forms:
            raise ValueError(
                f"cohort_strip lens {self.id!r} requires exactly one of "
                "`primary:` (scalar field), `primary_composite:` "
                "(tuple display), or `primary_aggregate:` (cross-join "
                "aggregate expression)."
            )
        return self


class CohortStripConfig(BaseModel):
    """Per-region config for `display: cohort_strip` (#1018).

    Discriminated config block — only populated when
    `WorkspaceRegion.display == DisplayMode.COHORT_STRIP`. Domain-
    agnostic: school class (pupils + grades), sales team (reps +
    quota), engineering team (engineers + commits), customer cohort
    (customers + MRR), field crew (technicians + SLA) all reuse the
    same shape. Establishes the typed-config pattern for the rest of
    the #1015–#1017 region-primitive quartet.

    Attributes:
        member_via: Field on the source entity whose FK resolves to
            the member's profile entity (any record carrying name +
            avatar + a secondary identifier). The halo renders from
            that record.
        lenses: Ordered list of available lenses; first is the default
            unless `default_lens` overrides.
        default_lens: Lens id to render when no `?lens=` query param is
            present. Must match one of `lenses[*].id`.
    """

    member_via: str
    lenses: list[CohortStripLens]
    default_lens: str = ""

    model_config = ConfigDict(frozen=True)


class EntityCardSectionMode(StrEnum):
    """Density-tuned section renderer modes for `entity_card` (#1017).

    An `entity_card` section's `mode` selects which compact renderer
    the runtime adapter will use, instead of the default list /
    detail layout (which fights for dominance and produces low-
    density wallpaper when stacked). The mode names are deliberately
    domain-agnostic — `entity_card` works for pupil-360 in MIS,
    customer-360 in CRM, asset-360 in field-ops, etc.
    """

    HALO = "halo"
    FLAGS = "flags"
    MINI_BARS = "mini_bars"
    STAMPS = "stamps"
    THREAD_SUMMARY = "thread_summary"
    QUICK_ACTIONS = "quick_actions"


class EntityCardSection(BaseModel):
    """One section in an `entity_card` composite (#1017).

    Each section is independently sourced + scoped + empty-state-
    aware. The IR carries the unresolved filter; the runtime adapter
    queries the source, applies the mode-specific compact renderer,
    and decides whether to emit the section at all (sections that
    resolve to zero rows AND are flagged optional are omitted
    entirely; required sections render their empty placeholder).

    Attributes:
        name: Section identifier — stable id used for CSS targeting
            and the `quick_actions` reference list (when mode is
            QUICK_ACTIONS this is a virtual section with no source).
        mode: Density-tuned renderer (halo / flags / mini_bars /
            stamps / thread_summary / quick_actions).
        source: Entity name. None for the `quick_actions` section.
        filter: Optional scope/predicate. None = match all rows
            within RBAC scope.
        limit: Optional row cap (e.g. ``recent_marks`` limit 5).
        fields: For halo / flags modes, the ordered list of field
            names to surface. Other modes ignore this and resolve
            their own field set per the mode contract.
        actions: For QUICK_ACTIONS mode, the ordered list of action
            ids referencing surface entries (each opens a modal
            flow). Empty for non-actions modes.
    """

    name: str
    mode: EntityCardSectionMode
    source: str | None = None
    filter: ConditionExpr | None = None
    limit: int | None = Field(None, ge=1, le=100)
    fields: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class EntityCardConfig(BaseModel):
    """Per-region config for `display: entity_card` (#1017).

    Discriminated config block — only populated when
    `WorkspaceRegion.display == DisplayMode.ENTITY_CARD`. Models a
    composite 360° single-entity view at calibrated density: any
    combination of halo / flags / mini_bars / stamps / thread_summary
    / quick_actions sections, sourced from arbitrary related entities.
    Use cases include pupil-360 in MIS, customer-360 in CRM,
    asset-360 in field-ops, patient-360 in healthcare, etc.

    Attributes:
        scope_param: Name of the surface route parameter that scopes
            the card to a single entity instance (e.g. ``"id"``,
            ``"pupil_id"``, ``"customer_id"``). The adapter resolves
            the value at request time and applies it as a filter on
            the primary source.
        sections: Ordered list of sections; the renderer composes
            them into a two-column responsive layout (main +
            sidebar) per the spec.
    """

    scope_param: str = "id"
    sections: list[EntityCardSection]

    model_config = ConfigDict(frozen=True)


class TaskSourceTemplate(BaseModel):
    """Per-source `as_task` template (#1015).

    Defines how one row from a `TaskSource` renders as a typed task
    item. Title and meta are template strings with `{field}`
    placeholders resolved against the source row at runtime by the
    adapter (this IR carries the unresolved templates).

    Attributes:
        icon: Named icon token (`register`, `pupil`, `message`,
            etc.) — adapter maps to the framework's icon vocabulary.
        title: Template string for the task's primary line.
            Placeholders reference fields on the source row or
            FK-resolved targets.
        meta: Template string for the secondary copy (period,
            deadline, age). Optional.
        via_joins: Cross-entity alias map (#1145 part 2). Each key
            is an alias usable in ``title``/``meta`` templates; each
            value is a dotted path resolved against the source row
            (typically walking through FK-hydrated sub-dicts). At
            render time the runtime resolves each path and injects
            the result under ``row[alias]`` before template
            interpolation, so ``{{ student.forename }}`` can reach
            ``BehaviourIncident → BehaviourStudent → StudentProfile``
            without route overrides. Empty dict (default) preserves
            pre-#1145-part-2 behaviour.
    """

    icon: str
    title: str
    meta: str = ""
    via_joins: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class TaskSource(BaseModel):
    """One source feeding a `task_inbox` region (#1015).

    Each source resolves to 0..N rows on the source entity scoped by
    `filter`. Either `as_task` (per-row task item) or `count_as`
    (collapsed summary chip) must be set — they are mutually
    exclusive: an `as_task` source emits one task per row, a
    `count_as` source emits one summary chip with the row count
    regardless of cardinality.

    Attributes:
        source: Entity name (the source's row type).
        filter: Optional scope/predicate evaluated against the
            source rows. None = match all (within RBAC scope).
        as_task: Per-row task template. Mutually exclusive with
            `count_as`.
        count_as: Singular noun phrase for the collapsed-summary
            chip (e.g. ``"manuscripts ready to review"``). Mutually
            exclusive with `as_task`.
    """

    source: str
    filter: ConditionExpr | None = None
    as_task: TaskSourceTemplate | None = None
    count_as: str = ""

    model_config = ConfigDict(frozen=True)


class TaskInboxConfig(BaseModel):
    """Per-region config for `display: task_inbox` (#1015).

    Discriminated config block — only populated when
    `WorkspaceRegion.display == DisplayMode.TASK_INBOX`. Models the
    workflow-led "due actions" landing pattern: heterogeneous entity
    states gathered into one prioritised inbox, framed as
    tasks-of-actions rather than entity-of-records.

    Attributes:
        sources: Ordered list of contributing sources. Each is
            either an `as_task` row template or a `count_as`
            summary chip; the runtime adapter resolves both.
        order: Ordered list of sort keys evaluated left-to-right
            against the merged task list. ``urgency`` is the
            built-in priority bucket; other keys reference
            temporal fields on the source rows.
        empty_state: Message rendered when zero tasks AND zero
            summary chips resolve.
    """

    sources: list[TaskSource]
    order: list[str] = Field(default_factory=lambda: ["urgency", "deadline"])
    empty_state: str = "All caught up."

    model_config = ConfigDict(frozen=True)


class DayTimelineConfig(BaseModel):
    """Per-region config for `display: day_timeline` (#1016).

    Discriminated config block — only populated when
    `WorkspaceRegion.display == DisplayMode.DAY_TIMELINE`. Models a
    chronological scroll of slots (typically `TimetableSlot`) where
    one slot is "active now" (rendered highlighted), prior slots
    collapse, and following slots preview at lower contrast.

    Attributes:
        starts_at: Field on the source entity holding the slot's
            start timestamp. The runtime adapter compares ``now``
            against the [starts_at, ends_at] window to determine the
            active slot.
        ends_at: Field on the source entity holding the slot's end
            timestamp.
        card: ``{{ field }}`` / ``{{ field.path }}`` template
            rendered against each slot's source row to produce the
            slot body (#1146 part 1). Same grammar as
            ``profile_card`` / ``task_inbox`` templates — graceful
            degradation when a path is unresolved (renders as empty
            string). When ``card == ""`` slots render with a minimal
            default body (start/end label only).
        as_of: Optional date anchor for ``HH:MM`` timetables
            (#1146 part 2). When ``starts_at`` / ``ends_at`` resolve
            to a ``time`` value (or ``HH:MM`` string) rather than a
            full datetime, the runtime composes them with the date
            from ``as_of``:

            - ``""`` (default) → no composition; the field values
              must parse as datetimes on their own.
            - ``"today"`` → compose with today's date (UTC).
            - any other identifier → field name on the row holding
              the date component (e.g. ``schedule_date``).

            One ``as_of`` applies to both ``starts_at`` and
            ``ends_at`` — the typical timetable case is one date
            per row.
    """

    starts_at: str
    ends_at: str
    card: str = ""
    as_of: str = ""

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
    # Plan 2: renderer name override at region level. Optional;
    # `None` means the framework default applies. Validated at link
    # time against the RendererRegistry. Resolution order
    # (region → surface → framework default) is deferred to Plan 3.
    render: str | None = None
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
    # ADR-0024: aggregate metrics are typed AggregateRef IR. Parser
    # desugars `count(Entity [where ...])` / `avg(col)` / `avg(Entity.col)`
    # into the structured shape at parse time.
    # #1359: derived metrics (arithmetic over earlier metric names) join
    # plain aggregate refs in the same block.
    aggregates: dict[str, AggregateRef | DerivedMetric] = Field(default_factory=dict)
    # v0.61.68: optional notice band rendered above the region body
    # inside the dashboard slot. Authors declare title (strong),
    # body (secondary copy), and tone (positive/warning/destructive/
    # accent/neutral). AegisMark UX patterns roadmap item #7.
    notice: NoticeSpec | None = None
    # v0.61.65: per-tile palette tokens for `display: metrics`. Map metric
    # name → tone token (positive / warning / destructive / accent / neutral).
    # Reuses the action_grid card vocabulary for consistency. Surfaced by
    # the metrics template as a per-tile background tint. Pure presentation
    # — no impact on data, scope, or semantics. AegisMark UX patterns
    # roadmap item #2.
    tones: dict[str, str] = Field(default_factory=dict)
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
    # AegisMark Day-One demo region primitives — discriminated typed
    # config blocks (#1015–#1018). Only one config is populated per
    # region, matched against `display`. Establishes the pattern for
    # subsequent primitives' configs to land alongside without
    # bloating the flat field set with mutually-exclusive options.
    cohort_strip_config: CohortStripConfig | None = None  # #1018 (v0.67.2)
    day_timeline_config: DayTimelineConfig | None = None  # #1016 (v0.67.3)
    task_inbox_config: TaskInboxConfig | None = None  # #1015 (v0.67.4)
    entity_card_config: EntityCardConfig | None = None  # #1017 (v0.67.5)
    # #1148: per-row click-to-POST action for row-oriented displays
    # (list, cohort_strip, day_timeline, status_list). One typed block,
    # one renderer contract; supersedes #1146's `slot_action:` proposal.
    # Renderer plumbing per-display landed incrementally — projects can
    # author `row_action:` ahead of full renderer support, the IR is
    # ready and the parser locks the shape.
    row_action: RowActionSpec | None = None
    # #1303: per-row drill-to-detail on row-oriented displays (list,
    # task_inbox). Values: None (default) → AUTO (rows link to
    # `/app/<entity>/{id}` when the source entity has a VIEW surface,
    # mirroring the standalone list); "none" → opt out (no row links even
    # if a detail surface exists); "detail" → explicit auto (same as
    # default, states intent). The runtime gates on VIEW-surface existence
    # in all cases, so a drill link never points at a non-existent route.
    drill: str | None = None
    # v0.61.63 (#903): explicit region title override. When set, replaces
    # the auto-derived title from the region key (e.g. `hero_marked` →
    # "Hero Marked"). Empty string is treated as None — the runtime
    # falls back to the auto-derived title. Pure presentation hook.
    title: str | None = None
    # v0.61.83 (#914): explicit grid-column span override. When set,
    # overrides both the stage-default (12 for unknown stages, 4 for
    # `metrics`, etc.) and any project-CSS `:has()` + `!important`
    # contortion projects previously needed to coerce hero strips and
    # KPI rows. Saved layouts (drag-resize via the dashboard builder)
    # still win — the user's explicit resize is the highest signal.
    # Range: 1..12 inclusive; values outside that band are clamped at
    # parse time with a warning. None = "use stage default".
    width: int | None = None
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
    # v0.61.69 (#3): status_list entries — vertical icon + title + copy
    # + state-pill list. Authored shape (source-bound variant deferred).
    # Empty list = legacy behaviour (no entries).
    status_entries: list[StatusListEntrySpec] = Field(default_factory=list)
    # v0.61.72 (#6): confirm_action_panel — irreversible-action consent
    # primitive. AegisMark UX patterns roadmap item #6. The panel reads
    # the entity's `state_field` to decide its visual mode (off/pending
    # → checklist + primary; live/active → summary + revoke; revoked →
    # audit + re-enable). All five fields default to empty so non-
    # confirm_action_panel regions are unaffected.
    confirmations: list[ConfirmationItemSpec] = Field(default_factory=list)
    state_field: str | None = None  # entity column driving panel mode
    revoke: str | None = None  # action surface shown when state is "live"
    primary_action: str | None = None  # primary action surface (typically the commit)
    secondary_action: str | None = None  # optional draft / cancel surface

    model_config = ConfigDict(frozen=True)


class NavItemIR(BaseModel):
    """A navigation item within a workspace or nav group.

    Attributes:
        entity: Entity or workspace name to link to
        icon: Optional Lucide icon name (e.g., "file-text", "check-circle")
        when: Optional render-time VISIBILITY condition (#1324 FR-4). Same
            ``ConditionExpr`` shape as ``RowActionSpec.visible_when``. When
            set, the item is hidden if the condition evaluates falsy against
            roles/grants/per-tenant config at render time. Visibility only —
            NOT access control (the RBAC matrix still gates reachability).
            ``None`` = always visible. Inert until slice B wires the render
            filter; this field is parsed but not yet read by the renderer.
    """

    entity: str
    icon: str | None = None
    when: ConditionExpr | None = None

    model_config = ConfigDict(frozen=True)


class NavGroupSpec(BaseModel):
    """A collapsible navigation group within a workspace.

    Attributes:
        label: Display label for the group header
        icon: Optional Lucide icon name for the group header
        collapsed: Whether the group starts collapsed (default: False)
        items: Navigation items within this group
        when: Optional render-time VISIBILITY condition (#1324 FR-4). Same
            ``ConditionExpr`` shape as ``RowActionSpec.visible_when``. When
            set, the whole group is hidden if the condition evaluates falsy
            against roles/grants/per-tenant config at render time. Visibility
            only — NOT access control. ``None`` = always visible. Inert until
            slice B wires the render filter.
    """

    label: str
    icon: str | None = None
    collapsed: bool = False
    items: list[NavItemIR] = Field(default_factory=list)
    when: ConditionExpr | None = None

    model_config = ConfigDict(frozen=True)


class NavSpec(BaseModel):
    """A reusable, named navigation definition (v0.61.95, #926).

    Top-level `nav <name>:` blocks declare a list of nav groups that
    can be referenced from multiple workspaces via `uses nav <name>`,
    eliminating the duplication that arises when several workspaces in
    the same persona share a sidebar shape (a primary landing plus N
    drill-downs).

    Attributes:
        name: Definition identifier — referenced by `uses nav <name>`.
        groups: Nav groups (header + items) in display order.
    """

    name: str
    groups: list[NavGroupSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class WorkspacePrimaryActionSpec(BaseModel):
    """A declarative call-to-action button in a workspace heading (#1324 FR-5).

    Authored via a ``primary_actions:`` block on a workspace. Each entry
    references a declared SURFACE or WORKSPACE by name (validated at lint
    time — an unknown target is a validation ERROR). The renderer emits a
    plain nav link (``<a href hx-boost>``, GET) — no method/confirm/POST.

    NOTE: this is the PLURAL heading-CTA list, distinct from the SINGULAR
    ``primary_action: str | None`` on :class:`WorkspaceRegion` (which names
    the commit surface of a confirm_action_panel — a different concept).

    There is NO per-action persona gating in v1: the workspace page's own
    access gates visibility, so authored actions show to anyone who can see
    the workspace.

    Attributes:
        label: Button text (e.g. "New Invoice").
        target_kind: Whether ``target`` names a surface or a workspace.
        target: The declared surface/workspace name to link to.
    """

    label: str
    target_kind: Literal["surface", "workspace"]
    target: str

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
    # v0.61.95 (#926): reference to a shared `nav <name>:` definition.
    # When set, the linker prepends the named definition's groups to
    # `nav_groups` so the workspace's own `nav_group` blocks (if any)
    # append after the inherited ones.
    nav_ref: str | None = None
    ux: UXSpec | None = None  # Workspace-level UX (e.g., persona variants)
    access: WorkspaceAccessSpec | None = None  # v0.22.0: Access control
    context_selector: ContextSelectorSpec | None = None  # v0.38.0
    # #1324 FR-5: authored heading CTA buttons. Each references a declared
    # surface or workspace by name (validated at lint time). At the build
    # site these APPEND AFTER the auto-inferred create-surface CTAs (#827);
    # inference is unchanged. Empty list = legacy behaviour (inferred only).
    # NOTE: this PLURAL list is the workspace-heading CTA set — distinct
    # from the SINGULAR `WorkspaceRegion.primary_action` (the commit surface
    # of a confirm_action_panel).
    primary_actions: list[WorkspacePrimaryActionSpec] = Field(default_factory=list)
    # v0.31.0: Source location for error reporting
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)

    def get_region(self, name: str) -> WorkspaceRegion | None:
        """Get region by name."""
        for region in self.regions:
            if region.name == name:
                return region
        return None
