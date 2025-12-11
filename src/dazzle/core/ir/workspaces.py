"""
Workspace types for DAZZLE IR.

This module contains workspace specifications for composing related
information needs into cohesive user experiences.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .conditions import ConditionExpr
from .ux import SortSpec, UXSpec


class DisplayMode(str, Enum):
    """Display modes for workspace regions."""

    LIST = "list"
    GRID = "grid"
    TIMELINE = "timeline"
    MAP = "map"
    DETAIL = "detail"  # v0.3.1: Single item detail view
    SUMMARY = "summary"  # v0.9.5: Metrics/KPI summary cards
    METRICS = "metrics"  # v0.9.5: Alias for summary


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
    filter: ConditionExpr | None = None
    sort: list[SortSpec] = Field(default_factory=list)
    limit: int | None = Field(None, ge=1, le=1000)
    display: DisplayMode = DisplayMode.LIST
    action: str | None = None  # Surface reference
    empty_message: str | None = None
    group_by: str | None = None  # Field to group by
    aggregates: dict[str, str] = Field(default_factory=dict)  # metric_name: expr

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
    """

    name: str
    title: str | None = None
    purpose: str | None = None
    stage: str | None = None  # v0.8.0: Layout stage (formerly engine_hint)
    regions: list[WorkspaceRegion] = Field(default_factory=list)
    ux: UXSpec | None = None  # Workspace-level UX (e.g., persona variants)

    model_config = ConfigDict(frozen=True)

    def get_region(self, name: str) -> WorkspaceRegion | None:
        """Get region by name."""
        for region in self.regions:
            if region.name == name:
                return region
        return None
