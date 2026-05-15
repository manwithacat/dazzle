"""
Layout engine types.

Re-exports IR types for convenience. All layout types are defined in
src/dazzle/core/ir.py to maintain single source of truth.
"""

from dazzle.core.ir import (
    AttentionSignalKind,
    LayoutPlan,
    LayoutSignal,
    LayoutSurface,
    PersonaLayout,
    Stage,
    WorkspaceLayout,
)

__all__ = [
    "LayoutSignal",
    "AttentionSignalKind",
    "Stage",
    "LayoutPlan",
    "LayoutSurface",
    "PersonaLayout",
    "WorkspaceLayout",
]
