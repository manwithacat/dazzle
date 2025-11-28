"""
Surface allocation algorithm.

Assigns attention signals to surfaces based on capacity constraints
and priority rules. This is the core of the layout planning process.
"""

from typing import TypedDict

from dazzle.core.ir import LayoutArchetype, LayoutSignal, LayoutSurface, WorkspaceLayout
from dazzle.ui.layout_engine.archetypes import ArchetypeDefinition


class MutableSurface(TypedDict):
    """Mutable surface tracking structure during allocation."""

    id: str
    capacity: float
    priority: int
    assigned_signals: list[str]


def assign_signals_to_surfaces(
    workspace: WorkspaceLayout, archetype_def: ArchetypeDefinition
) -> tuple[list[LayoutSurface], list[str]]:
    """
    Allocate attention signals to surfaces using capacity management.

    Algorithm:
    1. Sort signals by attention_weight (descending)
    2. Sort surfaces by priority (ascending = higher priority first)
    3. Greedy allocation: assign each signal to first surface with capacity
    4. Track over-budget signals that don't fit

    Args:
        workspace: Workspace with attention signals
        archetype_def: Archetype definition with surfaces

    Returns:
        tuple of:
        - list[LayoutSurface]: Surfaces with assigned signals
        - list[str]: Signal IDs that couldn't fit (over-budget)

    Examples:
        >>> from dazzle.core.ir import LayoutSignal, AttentionSignalKind
        >>> workspace = WorkspaceLayout(
        ...     id="test",
        ...     label="Test",
        ...     attention_signals=[
        ...         LayoutSignal(id="s1", kind=AttentionSignalKind.KPI,
        ...                        label="S1", source="E", attention_weight=0.8),
        ...         LayoutSignal(id="s2", kind=AttentionSignalKind.TABLE,
        ...                        label="S2", source="E", attention_weight=0.6),
        ...     ]
        ... )
        >>> from dazzle.ui.layout_engine.archetypes import FOCUS_METRIC
        >>> surfaces, over_budget = assign_signals_to_surfaces(workspace, FOCUS_METRIC)
        >>> len(surfaces)
        2
        >>> len(over_budget)
        0
    """
    signals = workspace.attention_signals

    if not signals:
        # No signals to allocate, return empty surfaces
        return _create_empty_surfaces(archetype_def), []

    # Step 1: Sort signals by weight (descending)
    sorted_signals = sorted(signals, key=lambda s: s.attention_weight, reverse=True)

    # Step 2: Create surface tracking
    surfaces = _initialize_surfaces(archetype_def)

    # Step 3: Greedy allocation
    over_budget: list[str] = []

    for signal in sorted_signals:
        allocated = False

        # Try to allocate to highest priority surface with capacity
        for surface in surfaces:
            current_load = _calculate_surface_load(surface, sorted_signals)
            remaining_capacity = surface["capacity"] - current_load

            if signal.attention_weight <= remaining_capacity:
                # Allocate to this surface
                surface["assigned_signals"].append(signal.id)
                allocated = True
                break

        if not allocated:
            # Signal couldn't fit anywhere
            over_budget.append(signal.id)

    # Step 4: Convert to immutable LayoutSurface instances
    return _finalize_surfaces(surfaces, archetype_def.archetype), over_budget


def _create_empty_surfaces(archetype_def: ArchetypeDefinition) -> list[LayoutSurface]:
    """Create empty surfaces for archetype."""
    return [
        LayoutSurface(
            id=surface_def.id,
            archetype=archetype_def.archetype,
            capacity=surface_def.capacity,
            priority=surface_def.priority,
            assigned_signals=[],
        )
        for surface_def in archetype_def.surfaces
    ]


def _initialize_surfaces(
    archetype_def: ArchetypeDefinition,
) -> list[MutableSurface]:
    """
    Initialize mutable surface tracking structures.

    Returns list of dicts (mutable) sorted by priority.
    """
    surfaces: list[MutableSurface] = [
        MutableSurface(
            id=surface_def.id,
            capacity=surface_def.capacity,
            priority=surface_def.priority,
            assigned_signals=[],
        )
        for surface_def in archetype_def.surfaces
    ]

    # Sort by priority (1 = highest priority first)
    surfaces.sort(key=lambda s: s["priority"])

    return surfaces


def _calculate_surface_load(
    surface: MutableSurface, all_signals: list[LayoutSignal]
) -> float:
    """
    Calculate current attention weight load on a surface.

    Args:
        surface: Mutable surface dict with assigned_signals
        all_signals: Complete list of LayoutSignal objects

    Returns:
        Total attention weight of assigned signals
    """
    signal_map = {s.id: s for s in all_signals}
    total = 0.0

    for signal_id in surface["assigned_signals"]:
        if signal_id in signal_map:
            total += signal_map[signal_id].attention_weight

    return total


def _finalize_surfaces(
    surfaces: list[MutableSurface], archetype: LayoutArchetype
) -> list[LayoutSurface]:
    """Convert mutable surface dicts to immutable LayoutSurface instances."""
    return [
        LayoutSurface(
            id=s["id"],
            archetype=archetype,
            capacity=s["capacity"],
            priority=s["priority"],
            assigned_signals=s["assigned_signals"],
        )
        for s in surfaces
    ]


__all__ = ["assign_signals_to_surfaces"]
