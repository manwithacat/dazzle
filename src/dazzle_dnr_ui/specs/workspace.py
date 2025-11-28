"""
Workspace specification types for UISpec.

Defines workspaces, layouts, and routes.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# =============================================================================
# Layout Specifications
# =============================================================================


class LayoutKind(str, Enum):
    """Layout types for workspaces."""

    SINGLE_COLUMN = "singleColumn"
    TWO_COLUMN_WITH_HEADER = "twoColumnWithHeader"
    APP_SHELL = "appShell"
    CUSTOM = "custom"


class SingleColumnLayout(BaseModel):
    """Single column layout with main content."""

    kind: Literal["singleColumn"] = "singleColumn"
    main: str = Field(description="Component name for main content")

    class Config:
        frozen = True


class TwoColumnWithHeaderLayout(BaseModel):
    """Two column layout with header."""

    kind: Literal["twoColumnWithHeader"] = "twoColumnWithHeader"
    header: str = Field(description="Component name for header")
    main: str = Field(description="Component name for main content")
    secondary: str = Field(description="Component name for secondary/sidebar")

    class Config:
        frozen = True


class AppShellLayout(BaseModel):
    """Application shell with sidebar, header, and main content."""

    kind: Literal["appShell"] = "appShell"
    sidebar: str = Field(description="Component name for sidebar")
    main: str = Field(description="Component name for main content")
    header: str | None = Field(default=None, description="Component name for header (optional)")
    footer: str | None = Field(default=None, description="Component name for footer (optional)")

    class Config:
        frozen = True


class CustomLayout(BaseModel):
    """Custom layout with named regions."""

    kind: Literal["custom"] = "custom"
    regions: dict[str, str] = Field(description="Map of region name to component name")

    class Config:
        frozen = True


# Union type for all layouts
LayoutSpec = SingleColumnLayout | TwoColumnWithHeaderLayout | AppShellLayout | CustomLayout


# =============================================================================
# Route Specifications
# =============================================================================


class RouteSpec(BaseModel):
    """
    Route specification for workspace navigation.

    Example:
        RouteSpec(path="/clients", component="ClientList")
        RouteSpec(path="/clients/:id", component="ClientDetail")
    """

    path: str = Field(description="Route path (supports :params)")
    component: str = Field(description="Component name to render")
    title: str | None = Field(default=None, description="Page title")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        frozen = True


# =============================================================================
# Workspace Specifications
# =============================================================================


class WorkspaceSpec(BaseModel):
    """
    Workspace specification.

    A workspace represents a logical section of the UI (e.g., dashboard, settings).

    Example:
        WorkspaceSpec(
            name="dashboard",
            persona="manager",
            layout=AppShellLayout(
                sidebar="DashboardNav",
                main="DashboardContent",
                header="DashboardHeader"
            ),
            routes=[
                RouteSpec(path="/", component="Overview"),
                RouteSpec(path="/metrics", component="MetricsView"),
            ]
        )
    """

    name: str = Field(description="Workspace name")
    label: str | None = Field(default=None, description="Human-readable label")
    description: str | None = Field(default=None, description="Workspace description")
    persona: str | None = Field(default=None, description="Target persona (for persona-aware UIs)")
    layout: LayoutSpec = Field(description="Layout specification")
    routes: list[RouteSpec] = Field(default_factory=list, description="Route definitions")
    state: list[Any] = Field(default_factory=list, description="Workspace-level state declarations")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        frozen = True

    def get_route(self, path: str) -> RouteSpec | None:
        """Get route by path."""
        for route in self.routes:
            if route.path == path:
                return route
        return None

    @property
    def layout_kind(self) -> str:
        """Get layout kind."""
        return self.layout.kind
