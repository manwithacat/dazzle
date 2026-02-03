"""
Workspace specification types for UISpec.

Defines workspaces, layouts, and routes.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Layout Specifications
# =============================================================================


class LayoutKind(StrEnum):
    """Layout types for workspaces."""

    SINGLE_COLUMN = "singleColumn"
    TWO_COLUMN_WITH_HEADER = "twoColumnWithHeader"
    APP_SHELL = "appShell"
    CUSTOM = "custom"


class SingleColumnLayout(BaseModel):
    """Single column layout with main content."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["singleColumn"] = "singleColumn"
    main: str = Field(description="Component name for main content")


class TwoColumnWithHeaderLayout(BaseModel):
    """Two column layout with header."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["twoColumnWithHeader"] = "twoColumnWithHeader"
    header: str = Field(description="Component name for header")
    main: str = Field(description="Component name for main content")
    secondary: str = Field(description="Component name for secondary/sidebar")


class AppShellLayout(BaseModel):
    """Application shell with sidebar, header, and main content."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["appShell"] = "appShell"
    sidebar: str = Field(description="Component name for sidebar")
    main: str = Field(description="Component name for main content")
    header: str | None = Field(default=None, description="Component name for header (optional)")
    footer: str | None = Field(default=None, description="Component name for footer (optional)")


class CustomLayout(BaseModel):
    """Custom layout with named regions."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["custom"] = "custom"
    regions: dict[str, str] = Field(description="Map of region name to component name")


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

    model_config = ConfigDict(frozen=True)

    path: str = Field(description="Route path (supports :params)")
    component: str = Field(description="Component name to render")
    title: str | None = Field(default=None, description="Page title")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# =============================================================================
# Access Specifications
# =============================================================================


class WorkspaceAccessLevel(StrEnum):
    """Access levels for workspaces."""

    PUBLIC = "public"  # No authentication required
    AUTHENTICATED = "authenticated"  # Any logged-in user
    PERSONA = "persona"  # Specific personas only


class WorkspaceAccessSpec(BaseModel):
    """
    Access control specification for workspaces.

    Defines authentication and authorization requirements for accessing a workspace.
    Default is deny (authenticated required) when auth is enabled globally.
    """

    model_config = ConfigDict(frozen=True)

    level: WorkspaceAccessLevel = WorkspaceAccessLevel.AUTHENTICATED
    allow_personas: list[str] = Field(default_factory=list)
    deny_personas: list[str] = Field(default_factory=list)
    redirect_unauthenticated: str = "/login"


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
            ],
            access=WorkspaceAccessSpec(level=WorkspaceAccessLevel.PERSONA, allow_personas=["manager"])
        )
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Workspace name")
    label: str | None = Field(default=None, description="Human-readable label")
    description: str | None = Field(default=None, description="Workspace description")
    persona: str | None = Field(default=None, description="Target persona (for persona-aware UIs)")
    layout: LayoutSpec = Field(description="Layout specification")
    routes: list[RouteSpec] = Field(default_factory=list, description="Route definitions")
    state: list[Any] = Field(default_factory=list, description="Workspace-level state declarations")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    access: WorkspaceAccessSpec | None = Field(
        default=None, description="Access control specification"
    )

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
