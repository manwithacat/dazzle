"""
UX semantic layer types for DAZZLE IR.

This module contains attention signals, persona variants, sort/filter specs,
and other UX-related specifications.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .conditions import ConditionExpr


class SignalLevel(str, Enum):
    """Levels for attention signals indicating urgency."""

    CRITICAL = "critical"
    WARNING = "warning"
    NOTICE = "notice"
    INFO = "info"


class AttentionSignal(BaseModel):
    """
    Data-driven attention signal for prioritization.

    Defines conditions that should draw user attention and optional actions.

    Attributes:
        level: Severity level (critical, warning, notice, info)
        condition: Condition expression that triggers this signal
        message: Human-readable message to display
        action: Optional surface reference for quick action
    """

    level: SignalLevel
    condition: ConditionExpr
    message: str
    action: str | None = None  # Surface reference

    model_config = ConfigDict(frozen=True)

    @property
    def css_class(self) -> str:
        """Map signal level to CSS class name."""
        return {
            SignalLevel.CRITICAL: "danger",
            SignalLevel.WARNING: "warning",
            SignalLevel.NOTICE: "info",
            SignalLevel.INFO: "secondary",
        }[self.level]


class PersonaVariant(BaseModel):
    """
    Role-specific surface adaptation.

    Defines how a surface should be customized for different user personas.

    Attributes:
        persona: Persona identifier (e.g., "volunteer", "coordinator")
        scope: Filter expression limiting data visibility, or "all"
        purpose: Persona-specific purpose description
        show: Fields to explicitly show (overrides base)
        hide: Fields to hide from base
        show_aggregate: Aggregate metrics to display (e.g., critical_count)
        action_primary: Primary action surface for this persona
        read_only: Whether mutations are disabled
        defaults: Default field values for forms (e.g., {"assigned_to": "current_user"})
        focus: Workspace regions to emphasize for this persona
    """

    persona: str
    scope: ConditionExpr | None = None  # None means "all"
    scope_all: bool = False  # True if "scope: all" was specified
    purpose: str | None = None
    show: list[str] = Field(default_factory=list)
    hide: list[str] = Field(default_factory=list)
    show_aggregate: list[str] = Field(default_factory=list)
    action_primary: str | None = None  # Surface reference
    read_only: bool = False
    defaults: dict[str, Any] = Field(default_factory=dict)  # Field default values
    focus: list[str] = Field(default_factory=list)  # Workspace regions to emphasize

    model_config = ConfigDict(frozen=True)

    def applies_to_user(self, user_context: dict[str, Any]) -> bool:
        """Check if persona applies to given user context."""
        return user_context.get("persona") == self.persona


class SortSpec(BaseModel):
    """
    Sort specification for a field.

    Attributes:
        field: Field name to sort by
        direction: Sort direction (asc or desc)
    """

    field: str
    direction: str = "asc"  # "asc" or "desc"

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"{self.field} {self.direction}"


class UXSpec(BaseModel):
    """
    Complete UX specification for a surface.

    Captures semantic intent about how users interact with data.

    Attributes:
        purpose: Why this surface exists
        show: Fields to display (overrides section fields if present)
        sort: Default sort order
        filter: Fields available for filtering
        search: Fields available for full-text search
        empty_message: Message shown when no data
        attention_signals: Data-driven priority indicators
        persona_variants: Role-specific adaptations
    """

    purpose: str | None = None
    show: list[str] = Field(default_factory=list)
    sort: list[SortSpec] = Field(default_factory=list)
    filter: list[str] = Field(default_factory=list)
    search: list[str] = Field(default_factory=list)
    empty_message: str | None = None
    attention_signals: list[AttentionSignal] = Field(default_factory=list)
    persona_variants: list[PersonaVariant] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    def get_persona_variant(self, user_context: dict[str, Any]) -> PersonaVariant | None:
        """Get applicable persona variant for user context."""
        for variant in self.persona_variants:
            if variant.applies_to_user(user_context):
                return variant
        return None

    @property
    def has_attention_signals(self) -> bool:
        """Check if any attention signals are defined."""
        return len(self.attention_signals) > 0
