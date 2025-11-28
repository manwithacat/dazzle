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
from dazzle.ui.layout_engine.cache import LayoutPlanCache, get_layout_cache
from dazzle.ui.layout_engine.converter import (
    convert_workspace_to_layout,
    convert_workspaces_to_layouts,
    enrich_app_spec_with_layouts,
)
from dazzle.ui.layout_engine.plan import build_layout_plan
from dazzle.ui.layout_engine.select_archetype import (
    ArchetypeScore,
    SelectionExplanation,
    explain_archetype_selection,
    select_archetype,
)
from dazzle.ui.layout_engine.types import (
    AttentionSignalKind,
    LayoutArchetype,
    LayoutPlan,
    LayoutSignal,
    LayoutSurface,
    PersonaLayout,
    WorkspaceLayout,
)
from dazzle.ui.layout_engine.variants import (
    VARIANT_CONFIGS,
    EngineVariant,
    VariantConfig,
    get_grid_columns,
    get_variant_config,
    get_variant_for_persona,
)

__all__ = [
    # Core functions
    "build_layout_plan",
    "select_archetype",
    "explain_archetype_selection",
    "SelectionExplanation",
    "ArchetypeScore",
    # DSL conversion
    "convert_workspace_to_layout",
    "convert_workspaces_to_layouts",
    "enrich_app_spec_with_layouts",
    # Caching
    "LayoutPlanCache",
    "get_layout_cache",
    # Archetype definitions
    "ARCHETYPE_DEFINITIONS",
    "ArchetypeDefinition",
    # Engine variants
    "EngineVariant",
    "VariantConfig",
    "VARIANT_CONFIGS",
    "get_variant_config",
    "get_variant_for_persona",
    "get_grid_columns",
    # IR types (re-exported for convenience)
    "LayoutSignal",
    "AttentionSignalKind",
    "LayoutArchetype",
    "LayoutPlan",
    "LayoutSurface",
    "PersonaLayout",
    "WorkspaceLayout",
]
