"""
Component specification types for UISpec.

Defines component structure and props schemas.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from dazzle_dnr_ui.specs.actions import ActionSpec
from dazzle_dnr_ui.specs.state import StateSpec
from dazzle_dnr_ui.specs.view import ViewNode


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

    name: str = Field(description="Prop name")
    type: str = Field(description="Prop type (str, int, Client, list[Invoice], etc.)")
    required: bool = Field(default=False, description="Is this prop required?")
    default: Any | None = Field(default=None, description="Default value")
    description: str | None = Field(default=None, description="Prop description")

    class Config:
        frozen = True


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

    fields: list[PropFieldSpec] = Field(
        default_factory=list, description="Prop fields"
    )

    class Config:
        frozen = True

    def get_field(self, name: str) -> PropFieldSpec | None:
        """Get prop field by name."""
        for field in self.fields:
            if field.name == name:
                return field
        return None


# =============================================================================
# Component Categories
# =============================================================================


class ComponentCategory(str):
    """Component categories for organization."""

    PRIMITIVE = "primitive"  # Built-in primitive (Page, Card, DataTable, etc.)
    PATTERN = "pattern"  # Built-in pattern (FilterableTable, CRUDPage, etc.)
    CUSTOM = "custom"  # User-defined component


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
    category: str = Field(
        default=ComponentCategory.CUSTOM, description="Component category"
    )
    props_schema: PropsSchema = Field(
        default_factory=PropsSchema, description="Props schema"
    )
    view: ViewNode | None = Field(
        default=None, description="View tree (None for primitives)"
    )
    state: list[StateSpec] = Field(
        default_factory=list, description="Component state declarations"
    )
    actions: list[ActionSpec] = Field(
        default_factory=list, description="Component actions"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    class Config:
        frozen = True

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
