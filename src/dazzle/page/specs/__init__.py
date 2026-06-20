"""
UISpec type definitions.

This module exports all UI specification types.
"""

from dazzle.page.specs.actions import (
    ActionSpec,
    EffectSpec,
    FetchEffect,
    NavigateEffect,
    PatchSpec,
    TransitionSpec,
)
from dazzle.page.specs.component import (
    ComponentSpec,
    PropFieldSpec,
    PropsSchema,
)
from dazzle.page.specs.shell import (
    FooterLinkSpec,
    FooterSpec,
    HeaderSpec,
    NavItemSpec,
    ShellNavSpec,
    ShellSpec,
    StaticPageSpec,
)
from dazzle.page.specs.state import (
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
from dazzle.page.specs.theme import TextStyle, ThemeSpec, ThemeTokens, VariantSpec
from dazzle.page.specs.ui_spec import UISpec
from dazzle.page.specs.view import (
    ConditionalNode,
    ElementNode,
    LoopNode,
    SlotNode,
    TextNode,
    ViewNode,
)
from dazzle.page.specs.workspace import (
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
