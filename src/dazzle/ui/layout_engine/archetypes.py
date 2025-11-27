"""
Archetype definitions for the layout engine.

Each archetype defines a specific compositional pattern for organizing
attention signals into surfaces. Archetypes are deterministic blueprints
that guide the layout allocation algorithm.
"""

from dataclasses import dataclass

from dazzle.core.ir import LayoutArchetype


@dataclass(frozen=True)
class SurfaceDefinition:
    """Definition of a surface within an archetype."""

    id: str
    capacity: float  # Maximum attention weight
    priority: int  # Allocation priority (1 = highest)
    description: str


@dataclass(frozen=True)
class ArchetypeDefinition:
    """
    Complete definition of a layout archetype.

    Attributes:
        archetype: Archetype enum value
        name: Human-readable name
        description: What this archetype is for
        surfaces: Ordered list of surfaces
        min_signals: Minimum signals needed
        max_signals: Maximum signals recommended
        best_for: Description of ideal use cases
    """

    archetype: LayoutArchetype
    name: str
    description: str
    surfaces: list[SurfaceDefinition]
    min_signals: int
    max_signals: int
    best_for: str


# =============================================================================
# Archetype Definitions
# =============================================================================

FOCUS_METRIC = ArchetypeDefinition(
    archetype=LayoutArchetype.FOCUS_METRIC,
    name="Focus Metric",
    description="Single dominant KPI with supporting context",
    surfaces=[
        SurfaceDefinition(
            id="hero",
            capacity=1.0,
            priority=1,
            description="Large, prominent metric display",
        ),
        SurfaceDefinition(
            id="context",
            capacity=0.3,
            priority=2,
            description="Supporting information and trends",
        ),
    ],
    min_signals=1,
    max_signals=3,
    best_for="Dashboards with a single critical metric (uptime, revenue, alerts)",
)

SCANNER_TABLE = ArchetypeDefinition(
    archetype=LayoutArchetype.SCANNER_TABLE,
    name="Scanner Table",
    description="Table-centric layout with filters and actions",
    surfaces=[
        SurfaceDefinition(
            id="toolbar",
            capacity=0.2,
            priority=3,
            description="Search, filters, and bulk actions",
        ),
        SurfaceDefinition(
            id="table",
            capacity=1.0,
            priority=1,
            description="Primary data table",
        ),
        SurfaceDefinition(
            id="sidebar",
            capacity=0.3,
            priority=2,
            description="Quick stats and filters",
        ),
    ],
    min_signals=1,
    max_signals=5,
    best_for="Data-heavy screens requiring scanning and filtering (admin panels, logs)",
)

DUAL_PANE_FLOW = ArchetypeDefinition(
    archetype=LayoutArchetype.DUAL_PANE_FLOW,
    name="Dual Pane Flow",
    description="Master-detail pattern with list and detail view",
    surfaces=[
        SurfaceDefinition(
            id="list",
            capacity=0.6,
            priority=1,
            description="Master list or navigation",
        ),
        SurfaceDefinition(
            id="detail",
            capacity=0.8,
            priority=2,
            description="Detail view of selected item",
        ),
    ],
    min_signals=2,
    max_signals=4,
    best_for="Workflows with item selection and detailed viewing (email, documents)",
)

MONITOR_WALL = ArchetypeDefinition(
    archetype=LayoutArchetype.MONITOR_WALL,
    name="Monitor Wall",
    description="Multiple moderate-importance signals in grid layout",
    surfaces=[
        SurfaceDefinition(
            id="grid_primary",
            capacity=1.2,
            priority=1,
            description="Primary grid area (2-4 widgets)",
        ),
        SurfaceDefinition(
            id="grid_secondary",
            capacity=0.8,
            priority=2,
            description="Secondary grid area (2-3 widgets)",
        ),
        SurfaceDefinition(
            id="sidebar",
            capacity=0.4,
            priority=3,
            description="Sidebar for alerts or status",
        ),
    ],
    min_signals=3,
    max_signals=8,
    best_for="Operations dashboards with multiple concurrent metrics",
)

COMMAND_CENTER = ArchetypeDefinition(
    archetype=LayoutArchetype.COMMAND_CENTER,
    name="Command Center",
    description="Dense, expert-focused dashboard with many signals",
    surfaces=[
        SurfaceDefinition(
            id="header",
            capacity=0.4,
            priority=3,
            description="Critical alerts and status",
        ),
        SurfaceDefinition(
            id="main_grid",
            capacity=1.5,
            priority=1,
            description="Dense grid of metrics and charts",
        ),
        SurfaceDefinition(
            id="left_rail",
            capacity=0.6,
            priority=2,
            description="Quick actions and navigation",
        ),
        SurfaceDefinition(
            id="right_rail",
            capacity=0.6,
            priority=2,
            description="Contextual information and tools",
        ),
    ],
    min_signals=5,
    max_signals=15,
    best_for="Expert users needing comprehensive system visibility (DevOps, trading)",
)

# Lookup table for all archetypes
ARCHETYPE_DEFINITIONS: dict[LayoutArchetype, ArchetypeDefinition] = {
    LayoutArchetype.FOCUS_METRIC: FOCUS_METRIC,
    LayoutArchetype.SCANNER_TABLE: SCANNER_TABLE,
    LayoutArchetype.DUAL_PANE_FLOW: DUAL_PANE_FLOW,
    LayoutArchetype.MONITOR_WALL: MONITOR_WALL,
    LayoutArchetype.COMMAND_CENTER: COMMAND_CENTER,
}


def get_archetype_definition(archetype: LayoutArchetype) -> ArchetypeDefinition:
    """Get archetype definition by enum value."""
    return ARCHETYPE_DEFINITIONS[archetype]


__all__ = [
    "ArchetypeDefinition",
    "SurfaceDefinition",
    "ARCHETYPE_DEFINITIONS",
    "get_archetype_definition",
    "FOCUS_METRIC",
    "SCANNER_TABLE",
    "DUAL_PANE_FLOW",
    "MONITOR_WALL",
    "COMMAND_CENTER",
]
