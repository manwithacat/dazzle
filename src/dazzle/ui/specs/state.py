"""
State specification types for UISpec.

Defines state scopes and data bindings.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# State Scopes
# =============================================================================


class StateScope(StrEnum):
    """State scopes for UI state management."""

    LOCAL = "local"  # Component-local state
    WORKSPACE = "workspace"  # Workspace-level state
    APP = "app"  # Application-global state
    SESSION = "session"  # Session state (persists across page loads)


# =============================================================================
# State Specifications
# =============================================================================


class StateSpec(BaseModel):
    """
    State declaration.

    Example:
        StateSpec(name="selectedClient", scope=StateScope.WORKSPACE, initial=None)
        StateSpec(name="isLoading", scope=StateScope.LOCAL, initial=False)
        StateSpec(name="theme", scope=StateScope.APP, initial="light", persistent=True)
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="State variable name")
    scope: StateScope = Field(description="State scope")
    initial: Any = Field(description="Initial value")
    persistent: bool = Field(
        default=False,
        description="Persist state across sessions (localStorage/sessionStorage)",
    )
    description: str | None = Field(default=None, description="State description")


# =============================================================================
# Bindings
# =============================================================================


class LiteralBinding(BaseModel):
    """Literal value binding."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["literal"] = "literal"
    value: Any = Field(description="Literal value")


class PropBinding(BaseModel):
    """Component prop binding."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["prop"] = "prop"
    path: str = Field(description="Prop path (e.g., 'client.name')")


class StateBinding(BaseModel):
    """Local state binding."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["state"] = "state"
    path: str = Field(description="State path (e.g., 'isLoading')")


class WorkspaceStateBinding(BaseModel):
    """Workspace state binding."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["workspaceState"] = "workspaceState"
    path: str = Field(description="Workspace state path (e.g., 'selectedClient.id')")


class AppStateBinding(BaseModel):
    """App state binding."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["appState"] = "appState"
    path: str = Field(description="App state path (e.g., 'currentUser.name')")


class DerivedBinding(BaseModel):
    """Derived/computed binding."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["derived"] = "derived"
    expr: str = Field(description="Expression to evaluate (e.g., 'count > 0')")


# Union type for all bindings
Binding = (
    LiteralBinding
    | PropBinding
    | StateBinding
    | WorkspaceStateBinding
    | AppStateBinding
    | DerivedBinding
)
