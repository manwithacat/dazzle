"""
UISpec type definitions.

This module exports all UI specification types.
"""

from dazzle_dnr_ui.specs.actions import (
    ActionSpec,
    EffectSpec,
    FetchEffect,
    NavigateEffect,
    PatchSpec,
    TransitionSpec,
)
from dazzle_dnr_ui.specs.component import (
    ComponentSpec,
    PropFieldSpec,
    PropsSchema,
)
from dazzle_dnr_ui.specs.shell import (
    FooterLinkSpec,
    FooterSpec,
    HeaderSpec,
    NavItemSpec,
    NavSpec,
    ShellSpec,
    StaticPageSpec,
)
from dazzle_dnr_ui.specs.state import (
    AppStateBinding,
    Binding,
    DerivedBinding,
    LiteralBinding,
    PropBinding,
    StateBinding,
    StateScope,
    StateSpec,
    WorkspaceStateBinding,
)
from dazzle_dnr_ui.specs.theme import TextStyle, ThemeSpec, ThemeTokens, VariantSpec
from dazzle_dnr_ui.specs.ui_spec import UISpec
from dazzle_dnr_ui.specs.view import (
    ConditionalNode,
    ElementNode,
    LoopNode,
    SlotNode,
    TextNode,
    ViewNode,
)
from dazzle_dnr_ui.specs.workspace import (
    AppShellLayout,
    CustomLayout,
    LayoutSpec,
    RouteSpec,
    SingleColumnLayout,
    TwoColumnWithHeaderLayout,
    WorkspaceSpec,
)

__all__ = [
    # Shell types
    "ShellSpec",
    "NavSpec",
    "NavItemSpec",
    "HeaderSpec",
    "FooterSpec",
    "FooterLinkSpec",
    "StaticPageSpec",
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
    "FetchEffect",
    "NavigateEffect",
    # Theme types
    "ThemeSpec",
    "ThemeTokens",
    "VariantSpec",
    "TextStyle",
    # Main spec
    "UISpec",
]
