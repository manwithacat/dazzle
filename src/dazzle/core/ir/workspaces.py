"""
Workspace types for DAZZLE IR.

This module contains workspace specifications for composing related
information needs into cohesive user experiences.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .conditions import ConditionExpr
from .location import SourceLocation
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
    PROGRESS = "progress"  # v0.44.0: Progress bar view
    ACTIVITY_FEED = "activity_feed"  # v0.44.0: Activity feed / timeline display
    TREE = "tree"  # v0.44.0: Tree / hierarchy display


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
    group_by: str | None = None  # Field to group by
    aggregates: dict[str, str] = Field(default_factory=dict)  # metric_name: expr
    # v0.34.0: Date-range filtering
    date_field: str | None = None
    date_range: bool = False  # Enable date picker on this region
    # v0.44.0: Heatmap configuration
    heatmap_rows: str | None = None  # FK field for row grouping
    heatmap_columns: str | None = None  # FK field for column grouping
    heatmap_value: str | None = None  # Expression for cell value
    heatmap_thresholds: list[float] = Field(default_factory=list)  # e.g. [0.4, 0.6] for RAG
    # v0.44.0: Progress bar configuration
    progress_stages: list[str] = Field(default_factory=list)  # ordered status values
    progress_complete_at: str | None = None  # which stage means "done"

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
