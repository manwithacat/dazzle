"""
Surface types for DAZZLE IR.

This module contains surface specifications for UI entry points
including modes, elements, sections, actions, and access control.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from .location import SourceLocation
from .ux import UXSpec

if TYPE_CHECKING:
    from .expressions import Expr


class BusinessPriority(StrEnum):
    """Business priority for surfaces and experiences."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SurfaceMode(StrEnum):
    """Modes that define surface behavior."""

    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    LIST = "list"
    REVIEW = "review"
    CUSTOM = "custom"


class SurfaceTrigger(StrEnum):
    """Triggers for surface actions."""

    SUBMIT = "submit"
    CLICK = "click"
    AUTO = "auto"


class OutcomeKind(StrEnum):
    """Types of outcomes for surface actions."""

    SURFACE = "surface"
    EXPERIENCE = "experience"
    INTEGRATION = "integration"


class Outcome(BaseModel):
    """
    Action outcome specification.

    Defines what happens when a surface action is triggered.
    """

    kind: OutcomeKind
    target: str  # surface name, experience name, or integration name
    step: str | None = None  # for experience outcomes
    action: str | None = None  # for integration outcomes

    model_config = ConfigDict(frozen=True)


class SurfaceElement(BaseModel):
    """
    Element within a surface section (typically a field).

    Attributes:
        field_name: Name of the field from the entity
        label: Human-readable label
        options: Additional options for rendering
        when_expr: Conditional visibility expression (v0.30.0).
            When present, the field is only shown if the expression
            evaluates to true for the current record.
    """

    field_name: str
    label: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    when_expr: Expr | None = None

    model_config = ConfigDict(frozen=True)


class SurfaceSection(BaseModel):
    """
    Section within a surface containing related elements.

    Attributes:
        name: Section identifier
        title: Human-readable title
        elements: List of elements in this section
    """

    name: str
    title: str | None = None
    elements: list[SurfaceElement] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class SurfaceAction(BaseModel):
    """
    Action that can be triggered from a surface.

    Attributes:
        name: Action identifier
        label: Human-readable label
        trigger: When the action is triggered
        outcome: What happens when action fires
    """

    name: str
    label: str | None = None
    trigger: SurfaceTrigger
    outcome: Outcome

    model_config = ConfigDict(frozen=True)


class SurfaceAccessSpec(BaseModel):
    """
    Access control specification for surfaces.

    Defines authentication and authorization requirements for accessing a surface.
    Used by the E2E test generator to create protected route tests.

    Attributes:
        require_auth: Whether authentication is required
        allow_personas: List of personas that can access (empty = all authenticated)
        deny_personas: List of personas explicitly denied access
        redirect_unauthenticated: Where to redirect unauthenticated users
    """

    require_auth: bool = False
    allow_personas: list[str] = Field(default_factory=list)
    deny_personas: list[str] = Field(default_factory=list)
    redirect_unauthenticated: str = "/"

    model_config = ConfigDict(frozen=True)


class SurfaceSpec(BaseModel):
    """
    Specification for a user-facing surface (screen/form/view).

    Surfaces describe UI entry points and interactions.

    Attributes:
        name: Surface identifier
        title: Human-readable title
        entity_ref: Optional reference to an entity
        mode: Surface mode (view, create, edit, list, custom)
        sections: List of sections containing elements
        actions: List of actions available on this surface
        ux: Optional UX semantic layer specification
        access: Optional access control specification for auth/RBAC
    """

    name: str
    title: str | None = None
    entity_ref: str | None = None
    view_ref: str | None = None  # Optional view for list field projection
    mode: SurfaceMode
    sections: list[SurfaceSection] = Field(default_factory=list)
    actions: list[SurfaceAction] = Field(default_factory=list)
    ux: UXSpec | None = None  # UX Semantic Layer extension
    access: SurfaceAccessSpec | None = None  # Auth/RBAC access control
    priority: BusinessPriority = BusinessPriority.MEDIUM
    # v0.34.0: Search configuration for list surfaces
    search_fields: list[str] = Field(default_factory=list)
    # v0.31.0: Source location for error reporting
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)


def _rebuild_surface_element() -> None:
    """Rebuild SurfaceElement to resolve forward reference to Expr."""
    from .expressions import Expr

    SurfaceElement.model_rebuild(_types_namespace={"Expr": Expr})


_rebuild_surface_element()
