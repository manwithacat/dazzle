"""
DAZZLE Semantic Layout Engine.

Deterministic, compiler-based UI layout planning from workspace specifications.

Key components:
- Archetype selection (select_archetype.py)
- Surface allocation (allocate.py)
- Persona adjustments (adjust.py)
- Layout plan assembly (plan.py)
"""

from dazzle.ui.layout_engine.archetypes import (
    ARCHETYPE_DEFINITIONS,
    ArchetypeDefinition,
)
from dazzle.ui.layout_engine.plan import build_layout_plan
from dazzle.ui.layout_engine.select_archetype import select_archetype
from dazzle.ui.layout_engine.types import (
    AttentionSignal,
    AttentionSignalKind,
    LayoutArchetype,
    LayoutPlan,
    LayoutSurface,
    PersonaLayout,
    WorkspaceLayout,
)

__all__ = [
    # Core functions
    "build_layout_plan",
    "select_archetype",
    # Archetype definitions
    "ARCHETYPE_DEFINITIONS",
    "ArchetypeDefinition",
    # IR types (re-exported for convenience)
    "AttentionSignal",
    "AttentionSignalKind",
    "LayoutArchetype",
    "LayoutPlan",
    "LayoutSurface",
    "PersonaLayout",
    "WorkspaceLayout",
]
