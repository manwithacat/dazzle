"""
UISpec type definitions.

This module exports all UI specification types.
"""

from dazzle.ui.specs.actions import (
    ActionSpec,
    EffectSpec,
    FetchEffect,
    NavigateEffect,
    PatchSpec,
    TransitionSpec,
)
from dazzle.ui.specs.component import (
    ComponentSpec,
    PropFieldSpec,
    PropsSchema,
)
from dazzle.ui.specs.shell import (
    FooterLinkSpec,
    FooterSpec,
    HeaderSpec,
    NavItemSpec,
    ShellNavSpec,
    ShellSpec,
    StaticPageSpec,
)
from dazzle.ui.specs.state import (
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
from dazzle.ui.specs.theme import TextStyle, ThemeSpec, ThemeTokens, VariantSpec
from dazzle.ui.specs.ui_spec import UISpec
from dazzle.ui.specs.view import (
    ConditionalNode,
    ElementNode,
    LoopNode,
    SlotNode,
    TextNode,
    ViewNode,
)
from dazzle.ui.specs.workspace import (
    AppShellLayout,
    CustomLayout,
    LayoutSpec,
    RouteSpec,
    SingleColumnLayout,
    TwoColumnWithHeaderLayout,
    WorkspaceAccessLevel,
    WorkspaceAccessSpec,
    WorkspaceSpec,
)

__all__ = [
    # Shell types
    "ShellSpec",
    "ShellNavSpec",
    "NavItemSpec",
    "HeaderSpec",
    "FooterSpec",
    "FooterLinkSpec",
    "StaticPageSpec",
    # Workspace types
    "WorkspaceSpec",
    "WorkspaceAccessLevel",
    "WorkspaceAccessSpec",
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
