"""
UISpec type definitions.

This module exports all UI specification types.
"""

from dazzle_dnr_ui.specs.workspace import (
    WorkspaceSpec,
    LayoutSpec,
    RouteSpec,
    SingleColumnLayout,
    TwoColumnWithHeaderLayout,
    AppShellLayout,
    CustomLayout,
)
from dazzle_dnr_ui.specs.component import (
    ComponentSpec,
    PropsSchema,
    PropFieldSpec,
)
from dazzle_dnr_ui.specs.view import (
    ViewNode,
    ElementNode,
    ConditionalNode,
    LoopNode,
    SlotNode,
    TextNode,
)
from dazzle_dnr_ui.specs.state import (
    StateSpec,
    StateScope,
    Binding,
    LiteralBinding,
    PropBinding,
    StateBinding,
    WorkspaceStateBinding,
    AppStateBinding,
    DerivedBinding,
)
from dazzle_dnr_ui.specs.actions import ActionSpec, EffectSpec, TransitionSpec, PatchSpec
from dazzle_dnr_ui.specs.theme import ThemeSpec, ThemeTokens, VariantSpec, TextStyle
from dazzle_dnr_ui.specs.ui_spec import UISpec

__all__ = [
    # Workspace types
    "WorkspaceSpec",
    "LayoutSpec",
    "RouteSpec",
    "SingleColumnLayout",
    "TwoColumnWithHeaderLayout",
    "AppShellLayout",
    "CustomLayout",
    # Component types
    "ComponentSpec",
    "PropsSchema",
    "PropFieldSpec",
    # View types
    "ViewNode",
    "ElementNode",
    "ConditionalNode",
    "LoopNode",
    "SlotNode",
    "TextNode",
    # State types
    "StateSpec",
    "StateScope",
    "Binding",
    "LiteralBinding",
    "PropBinding",
    "StateBinding",
    "WorkspaceStateBinding",
    "AppStateBinding",
    "DerivedBinding",
    # Action types
    "ActionSpec",
    "EffectSpec",
    "TransitionSpec",
    "PatchSpec",
    # Theme types
    "ThemeSpec",
    "ThemeTokens",
    "VariantSpec",
    "TextStyle",
    # Main spec
    "UISpec",
]
