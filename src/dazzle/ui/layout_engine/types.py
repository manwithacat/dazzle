"""
Layout engine types.

Re-exports IR types for convenience. All layout types are defined in
src/dazzle/core/ir.py to maintain single source of truth.
"""

from dazzle.core.ir import (
    AttentionSignal,
    AttentionSignalKind,
    LayoutArchetype,
    LayoutPlan,
    LayoutSurface,
    PersonaLayout,
    WorkspaceLayout,
)

__all__ = [
    "AttentionSignal",
    "AttentionSignalKind",
    "LayoutArchetype",
    "LayoutPlan",
    "LayoutSurface",
    "PersonaLayout",
    "WorkspaceLayout",
]
