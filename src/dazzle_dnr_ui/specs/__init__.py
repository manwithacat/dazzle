"""
UISpec type definitions.

This module exports all UI specification types.
"""

from dazzle_dnr_ui.specs.workspace import WorkspaceSpec, LayoutSpec, RouteSpec
from dazzle_dnr_ui.specs.component import ComponentSpec
from dazzle_dnr_ui.specs.view import (
    ViewNode,
    ElementNode,
    ConditionalNode,
    LoopNode,
    SlotNode,
)
from dazzle_dnr_ui.specs.state import StateSpec, StateScope, Binding
from dazzle_dnr_ui.specs.actions import ActionSpec, EffectSpec, TransitionSpec, PatchSpec
from dazzle_dnr_ui.specs.theme import ThemeSpec, VariantSpec, TextStyle
from dazzle_dnr_ui.specs.ui_spec import UISpec

__all__ = [
    # Workspace types
    "WorkspaceSpec",
    "LayoutSpec",
    "RouteSpec",
    # Component types
    "ComponentSpec",
    # View types
    "ViewNode",
    "ElementNode",
    "ConditionalNode",
    "LoopNode",
    "SlotNode",
    # State types
    "StateSpec",
    "StateScope",
    "Binding",
    # Action types
    "ActionSpec",
    "EffectSpec",
    "TransitionSpec",
    "PatchSpec",
    # Theme types
    "ThemeSpec",
    "VariantSpec",
    "TextStyle",
    # Main spec
    "UISpec",
]
