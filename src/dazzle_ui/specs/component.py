"""
Component specification types for UISpec.

Defines component structure and props schemas.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dazzle_ui.specs.actions import ActionSpec
from dazzle_ui.specs.state import StateSpec
from dazzle_ui.specs.view import ViewNode

# =============================================================================
# Props Schema
# =============================================================================


class PropFieldSpec(BaseModel):
    """
    Component prop field specification.

    Example:
        PropFieldSpec(name="title", type="str", required=True)
        PropFieldSpec(name="items", type="list[Client]", required=False, default=[])
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Prop name")
    type: str = Field(description="Prop type (str, int, Client, list[Invoice], etc.)")
    required: bool = Field(default=False, description="Is this prop required?")
    default: Any | None = Field(default=None, description="Default value")
    description: str | None = Field(default=None, description="Prop description")


class PropsSchema(BaseModel):
    """
    Component props schema.

    Example:
        PropsSchema(
            fields=[
                PropFieldSpec(name="title", type="str", required=True),
                PropFieldSpec(name="client", type="Client", required=True),
                PropFieldSpec(name="onSave", type="Action", required=False),
            ]
        )
    """

    model_config = ConfigDict(frozen=True)

    fields: list[PropFieldSpec] = Field(default_factory=list, description="Prop fields")

    def get_field(self, name: str) -> PropFieldSpec | None:
        """Get prop field by name."""
        for field in self.fields:
            if field.name == name:
                return field
        return None


# =============================================================================
# Component Categories and Roles
# =============================================================================


class ComponentCategory(str):
    """Component categories for organization."""

    PRIMITIVE = "primitive"  # Built-in primitive (Page, Card, DataTable, etc.)
    PATTERN = "pattern"  # Built-in pattern (FilterableTable, CRUDPage, etc.)
    CUSTOM = "custom"  # User-defined component


class ComponentRole(str):
    """
    Component roles define behavioral intent (v0.5.0).

    - PRESENTATIONAL: Purely visual, no state management, renders props only
    - CONTAINER: Manages state, fetches data, orchestrates child components
    """

    PRESENTATIONAL = "presentational"  # Pure rendering, no side effects
    CONTAINER = "container"  # State management, data fetching, orchestration


# =============================================================================
# Components
# =============================================================================


class ComponentSpec(BaseModel):
    """
    Component specification.

    A component is a reusable UI element with props, state, view, and actions.

    Example:
        ComponentSpec(
            name="ClientCard",
            category="custom",
            props_schema=PropsSchema(
                fields=[
                    PropFieldSpec(name="client", type="Client", required=True),
                    PropFieldSpec(name="onClick", type="Action"),
                ]
            ),
            view=ElementNode(
                as_="Card",
                props={
                    "title": PropBinding(path="client.name"),
                    "subtitle": PropBinding(path="client.email"),
                },
                children=[...]
            ),
            state=[
                StateSpec(name="isExpanded", scope=StateScope.LOCAL, initial=False)
            ],
            actions=[
                ActionSpec(name="toggle", transitions=[...])
            ]
        )
    """

    kind: str = Field(
        default="component", description="Kind (always 'component' for ComponentSpec)"
    )
    name: str = Field(description="Component name")
    description: str | None = Field(default=None, description="Component description")
    category: str = Field(default=ComponentCategory.CUSTOM, description="Component category")
    role: str | None = Field(
        default=None,
        description="Component role (presentational or container). None means auto-inferred.",
    )
    props_schema: PropsSchema = Field(default_factory=PropsSchema, description="Props schema")
    view: ViewNode | None = Field(default=None, description="View tree (None for primitives)")
    state: list[StateSpec] = Field(default_factory=list, description="Component state declarations")
    actions: list[ActionSpec] = Field(default_factory=list, description="Component actions")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    # Semantic context for DOM contract (data-dazzle-* attributes)
    view_name: str | None = Field(default=None, description="Semantic view name for DOM contract")
    entity_name: str | None = Field(default=None, description="Entity name for DOM contract")

    model_config = ConfigDict(frozen=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure component name is a valid identifier."""
        if not v[0].isupper():
            raise ValueError(f"Component name '{v}' must start with uppercase letter")
        if not v.replace("_", "").isalnum():
            raise ValueError(f"Component name '{v}' must be alphanumeric")
        return v

    @property
    def is_primitive(self) -> bool:
        """Check if this is a primitive component."""
        return self.category == ComponentCategory.PRIMITIVE

    @property
    def is_pattern(self) -> bool:
        """Check if this is a pattern component."""
        return self.category == ComponentCategory.PATTERN

    @property
    def is_custom(self) -> bool:
        """Check if this is a custom component."""
        return self.category == ComponentCategory.CUSTOM

    @property
    def is_presentational(self) -> bool:
        """
        Check if this is a presentational component.

        Returns True if explicitly marked as presentational, or if inferred
        (no state, no impure actions, view-only).
        """
        if self.role == ComponentRole.PRESENTATIONAL:
            return True
        if self.role is None:
            # Auto-infer: presentational if no state and no impure actions
            return len(self.state) == 0 and all(action.effect is None for action in self.actions)
        return False

    @property
    def is_container(self) -> bool:
        """
        Check if this is a container component.

        Returns True if explicitly marked as container, or if inferred
        (has state or impure actions).
        """
        if self.role == ComponentRole.CONTAINER:
            return True
        if self.role is None:
            # Auto-infer: container if has state or impure actions
            return len(self.state) > 0 or any(action.effect is not None for action in self.actions)
        return False

    def get_action(self, name: str) -> ActionSpec | None:
        """Get action by name."""
        for action in self.actions:
            if action.name == name:
                return action
        return None

    def get_state(self, name: str) -> StateSpec | None:
        """Get state by name."""
        for state in self.state:
            if state.name == name:
                return state
        return None
