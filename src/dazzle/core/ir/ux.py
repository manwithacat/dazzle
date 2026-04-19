"""
UX semantic layer types for DAZZLE IR.

This module contains attention signals, persona variants, sort/filter specs,
and other UX-related specifications.
"""

from __future__ import annotations  # required: forward reference

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .conditions import ConditionExpr


class SignalLevel(StrEnum):
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
        empty_message: Persona-specific empty-state copy. When present,
            overrides the surface-level ``empty:`` string at render time
            for this persona only. Added in cycle 240 (closes EX-046) so
            DSL authors can write action-oriented copy for creating
            personas ("Add your first task") and read-only-friendly copy
            for viewing personas ("No tasks yet") without two separate
            surfaces.
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
    empty_message: str | None = None  # Per-persona empty-state copy override

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


class BulkActionSpec(BaseModel):
    """
    Bulk action declaration on a list surface (#785).

    Binds an action name to a single-field transition that will be
    applied to every entity id supplied in a ``POST /api/{plural}/bulk``
    request.

    Example DSL:
        ux:
          bulk_actions:
            accept: status -> active
            reject: status -> rejected

    Attributes:
        name: Action name sent in the request body (e.g. ``"accept"``).
        field: Entity field the action mutates (e.g. ``"status"``).
        target_value: Value to assign to ``field`` for every selected id.
    """

    name: str
    field: str
    target_value: str

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"{self.name}: {self.field} -> {self.target_value}"


class EmptyMessages(BaseModel):
    """Typed empty-state messages for a list surface (#807).

    The framework has always had a single ``empty_message`` string —
    shown whenever the list query returned zero rows. But *why* the
    list is empty is a signal users need: a brand-new collection
    warrants *"No X yet. [Create one](create)"*; a filter that matched
    nothing warrants *"No X match the current filters. [Clear](clear)"*;
    a permission denial warrants a different message still.

    This type carries the per-case copy. Each field is optional — if
    unset, the framework falls back to a sensible default from
    ``fragments/empty_state.html``. Authors who want to customise pick
    the cases they care about:

    .. code-block:: dsl

        surface device_list "Devices":
          mode: list
          ...
          empty:
            collection: "No devices registered. Register one to begin."
            filtered: "No devices match the current filters."

    Attributes:
        collection: Copy when the underlying query has zero rows
            *unfiltered* — the collection is genuinely empty.
        filtered: Copy when filters are active and reduced the result
            to zero. Shown alongside a "Clear filters" affordance.
        forbidden: Copy when the user's row-scope predicate zeroed
            the result. Reserved for future use — the API envelope
            needs to carry an ``unscoped_total`` counter for the
            framework to detect this case; not wired yet.
    """

    collection: str | None = None
    filtered: str | None = None
    forbidden: str | None = None

    model_config = ConfigDict(frozen=True)


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
        empty_message: Message shown when no data. Two shapes supported
            (#807): a single ``str`` (legacy — used for every empty
            case) or an ``EmptyMessages`` struct with per-case copy
            (``collection``, ``filtered``, ``forbidden``).
        attention_signals: Data-driven priority indicators
        persona_variants: Role-specific adaptations
        bulk_actions: Named field transitions exposed as
            ``POST /api/{plural}/bulk`` endpoints (#785).
    """

    purpose: str | None = None
    show: list[str] = Field(default_factory=list)
    sort: list[SortSpec] = Field(default_factory=list)
    filter: list[str] = Field(default_factory=list)
    search: list[str] = Field(default_factory=list)
    empty_message: str | EmptyMessages | None = None
    search_first: bool = False
    attention_signals: list[AttentionSignal] = Field(default_factory=list)
    persona_variants: list[PersonaVariant] = Field(default_factory=list)
    bulk_actions: list[BulkActionSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    def empty_for(self, kind: str) -> str | None:
        """Resolve the empty-state message for a given ``kind``.

        Args:
            kind: One of ``"collection"``, ``"filtered"``,
                ``"forbidden"``. Anything else falls back to the
                legacy single-string behaviour.

        Returns:
            The typed message if present, otherwise the legacy string
            if ``empty_message`` is a plain ``str``, otherwise ``None``
            (the template then picks a framework default).
        """
        em = self.empty_message
        if isinstance(em, EmptyMessages):
            case = getattr(em, kind, None)
            if case is not None:
                return case
            # Fall through to None — template default.
            return None
        if isinstance(em, str):
            return em
        return None

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
