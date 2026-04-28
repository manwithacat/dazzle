"""
Surface types for DAZZLE IR.

This module contains surface specifications for UI entry points
including modes, elements, sections, actions, and access control.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from .conditions import ConditionExpr
from .location import SourceLocation
from .ux import UXSpec

if TYPE_CHECKING:
    from .expressions import Expr


class BusinessPriority(StrEnum):
    """Business priority for surfaces and experiences."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RelatedDisplayMode(StrEnum):
    """Display modes for related entity groups on detail pages."""

    TABLE = "table"
    STATUS_CARDS = "status_cards"
    FILE_LIST = "file_list"


class RelatedGroup(BaseModel):
    """A named group of related entities with a shared display mode.

    Attributes:
        name: Group identifier (DSL name, e.g. "compliance")
        title: Human-readable label (e.g. "Compliance")
        display: How to render the group's entities
        show: Entity names to include (validated at link time)
    """

    name: str
    title: str | None = None
    display: RelatedDisplayMode
    show: list[str]

    model_config = ConfigDict(frozen=True)


class SurfaceMode(StrEnum):
    """Modes that define surface behavior."""

    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    LIST = "list"
    REVIEW = "review"
    CUSTOM = "custom"


class SurfaceTrigger(StrEnum):
    """Triggers for surface actions."""

    SUBMIT = "submit"
    CLICK = "click"
    AUTO = "auto"


class OutcomeKind(StrEnum):
    """Types of outcomes for surface actions."""

    SURFACE = "surface"
    EXPERIENCE = "experience"
    INTEGRATION = "integration"
    EXTERNAL = "external"


class Outcome(BaseModel):
    """
    Action outcome specification.

    Defines what happens when a surface action is triggered.
    """

    kind: OutcomeKind
    target: str  # surface name, experience name, or integration name
    step: str | None = None  # for experience outcomes
    action: str | None = None  # for integration outcomes
    url: str | None = None  # for external outcomes
    new_tab: bool = True  # for external outcomes

    model_config = ConfigDict(frozen=True)


class SurfaceElement(BaseModel):
    """
    Element within a surface section (typically a field).

    Attributes:
        field_name: Name of the field from the entity
        label: Human-readable label
        options: Additional options for rendering
        when_expr: Conditional visibility expression (v0.30.0).
            When present, the field is only shown if the expression
            evaluates to true for the current record.
        visible: Role-based visibility condition (v0.42.0).
            When present, the field is only shown to users matching the
            condition (e.g. ``visible: role(admin) or role(manager)``).
    """

    field_name: str
    label: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    when_expr: Expr | None = None
    visible: ConditionExpr | None = None
    # v0.61.88 (#918): field-level help text below the label. Renders as
    # a muted paragraph. None = no help text.
    help: str | None = None

    model_config = ConfigDict(frozen=True)


class SurfaceSection(BaseModel):
    """
    Section within a surface containing related elements.

    Attributes:
        name: Section identifier
        title: Human-readable title
        elements: List of elements in this section
        visible: Role-based visibility condition (v0.42.0).
            When present, the entire section is only shown to users
            matching the condition (e.g. ``visible: role(admin)``).
    """

    name: str
    title: str | None = None
    elements: list[SurfaceElement] = Field(default_factory=list)
    visible: ConditionExpr | None = None
    # v0.61.88 (#918): section-level explanatory copy. Renders as a muted
    # paragraph below the section heading. None = no note.
    note: str | None = None

    model_config = ConfigDict(frozen=True)


class SurfaceAction(BaseModel):
    """
    Action that can be triggered from a surface.

    Attributes:
        name: Action identifier
        label: Human-readable label
        trigger: When the action is triggered
        outcome: What happens when action fires
    """

    name: str
    label: str | None = None
    trigger: SurfaceTrigger
    outcome: Outcome

    model_config = ConfigDict(frozen=True)


class CompanionPosition(StrEnum):
    """Where a companion panel renders relative to the form sections.

    Top / bottom run before / after the entire section list. `below_section`
    pairs the companion with a specific section by name — the panel
    renders directly under that section's content."""

    TOP = "top"
    BOTTOM = "bottom"
    BELOW_SECTION = "below_section"


class CompanionEntrySpec(BaseModel):
    """One row in a `display: status_list` companion."""

    title: str
    caption: str | None = None
    state: str | None = None  # e.g. "ok", "pending", "warn"
    icon: str | None = None

    model_config = ConfigDict(frozen=True)


class CompanionStageSpec(BaseModel):
    """One stage in a `display: pipeline_steps` companion."""

    label: str
    caption: str | None = None

    model_config = ConfigDict(frozen=True)


class CompanionSpec(BaseModel):
    """A read-only companion panel rendered alongside a create/edit form.

    Companion regions (#918 Part D, shipped in #923) let create/edit
    surfaces show context that's adjacent to the form — KPI tiles,
    "what this upload creates" job-plan previews, cohort roster snippets.
    They participate in the form layout but never submit to the create
    handler.

    The shape is intentionally a tight subset of `WorkspaceRegion`. For
    v1 we ship the declarative display modes (`summary_row`,
    `status_list`, `pipeline_steps`); source-bound modes
    (`source: Entity` + `filter:`) parse but render as a placeholder
    until the form-renderer pipeline gains workspace-region invocation.

    Attributes:
        name: Companion identifier — referenced from the form template.
        title: Optional headline above the companion content.
        eyebrow: Optional small label above the title.
        display: Display mode (`summary_row`, `status_list`,
            `pipeline_steps`, `list`). None falls back to a bare
            title-only render — useful as a temporary stub during
            authoring.
        position: Where the companion renders. Defaults to BOTTOM.
        section_anchor: When position is BELOW_SECTION, the section
            name to attach to. None for TOP / BOTTOM.
        source: Entity name for source-driven companions
            (`display: list`).
        filter: Filter condition applied when source is set.
        limit: Optional row cap for source-driven companions.
        aggregate: Metric definitions for `display: summary_row`,
            mapping metric name to expression (e.g.
            `{"pages": "max(page_count)"}`).
        entries: Static rows for `display: status_list`.
        stages: Static stages for `display: pipeline_steps`.
    """

    name: str
    title: str | None = None
    eyebrow: str | None = None
    display: str | None = None
    position: CompanionPosition = CompanionPosition.BOTTOM
    section_anchor: str | None = None
    source: str | None = None
    filter: ConditionExpr | None = None
    limit: int | None = None
    aggregate: dict[str, str] = Field(default_factory=dict)
    entries: list[CompanionEntrySpec] = Field(default_factory=list)
    stages: list[CompanionStageSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class SurfaceAccessSpec(BaseModel):
    """
    Access control specification for surfaces.

    Defines authentication and authorization requirements for accessing a surface.
    Used by the E2E test generator to create protected route tests.

    Attributes:
        require_auth: Whether authentication is required
        allow_personas: List of personas that can access (empty = all authenticated)
        deny_personas: List of personas explicitly denied access
        redirect_unauthenticated: Where to redirect unauthenticated users
    """

    require_auth: bool = False
    allow_personas: list[str] = Field(default_factory=list)
    deny_personas: list[str] = Field(default_factory=list)
    redirect_unauthenticated: str = "/"

    model_config = ConfigDict(frozen=True)


class SurfaceSpec(BaseModel):
    """
    Specification for a user-facing surface (screen/form/view).

    Surfaces describe UI entry points and interactions.

    Attributes:
        name: Surface identifier
        title: Human-readable title
        entity_ref: Optional reference to an entity
        mode: Surface mode (view, create, edit, list, custom)
        sections: List of sections containing elements
        actions: List of actions available on this surface
        ux: Optional UX semantic layer specification
        access: Optional access control specification for auth/RBAC
        headless: Surface is intentionally API-only (no rendered form — e.g.
            a client-side widget owns the UI and POSTs directly). When True,
            the "no sections defined" lint warning is suppressed because
            sections are deliberately empty.
    """

    name: str
    title: str | None = None
    entity_ref: str | None = None
    view_ref: str | None = None  # Optional view for list field projection
    mode: SurfaceMode
    sections: list[SurfaceSection] = Field(default_factory=list)
    actions: list[SurfaceAction] = Field(default_factory=list)
    ux: UXSpec | None = None  # UX Semantic Layer extension
    access: SurfaceAccessSpec | None = None  # Auth/RBAC access control
    priority: BusinessPriority = BusinessPriority.MEDIUM
    # v0.34.0: Search configuration for list surfaces
    search_fields: list[str] = Field(default_factory=list)
    # v0.31.0: Source location for error reporting
    source: SourceLocation | None = None
    related_groups: list[RelatedGroup] = Field(default_factory=list)
    headless: bool = False
    # v0.61.88 (#918): layout for create/edit surfaces. "wizard" (default,
    # current behaviour) renders 2+ sections as a multi-step wizard;
    # "single_page" stacks all sections top-to-bottom with one submit
    # button at the end. No effect on view/list/custom modes.
    layout: str = "wizard"
    # v0.61.102 (#923): companion regions on create/edit surfaces.
    # Read-only panels rendered at top, bottom, or below a named
    # section. Empty list = no companions (current behaviour).
    companions: list[CompanionSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


def _rebuild_surface_element() -> None:
    """Rebuild SurfaceElement to resolve forward reference to Expr."""
    from .expressions import Expr

    SurfaceElement.model_rebuild(_types_namespace={"Expr": Expr})


_rebuild_surface_element()
