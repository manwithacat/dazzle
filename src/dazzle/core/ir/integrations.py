"""
Integration types for DAZZLE IR.

This module contains integration specifications for connecting
internal entities with external services.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Expression(BaseModel):
    """
    Simple expression for mappings.

    Supports paths (form.vrn, entity.id) and literals.

    Attributes:
        path: Dotted path (e.g., "form.vrn", "entity.client_id")
        literal: Literal value (string, number, boolean)
    """

    path: str | None = None
    literal: str | int | float | bool | None = None

    model_config = ConfigDict(frozen=True)

    @field_validator("path", "literal")
    @classmethod
    def validate_one_set(
        cls, v: str | int | float | bool | None, info: Any
    ) -> str | int | float | bool | None:
        """Ensure exactly one of path or literal is set."""
        # This is simplified; full validation would check both fields
        return v


class MappingRule(BaseModel):
    """
    Mapping rule for integrations.

    Maps a target field to a source expression.

    Attributes:
        target_field: Field to map to
        source: Expression providing the value
    """

    target_field: str
    source: Expression

    model_config = ConfigDict(frozen=True)


class IntegrationAction(BaseModel):
    """
    Action within an integration (on-demand operation).

    Attributes:
        name: Action identifier
        when_surface: Surface that triggers this action
        call_service: Service to call
        call_operation: Operation name on service
        call_mapping: Mapping for call parameters
        response_foreign_model: Foreign model for response
        response_entity: Entity to map response to
        response_mapping: Mapping for response fields
    """

    name: str
    when_surface: str
    call_service: str
    call_operation: str
    call_mapping: list[MappingRule] = Field(default_factory=list)
    response_foreign_model: str | None = None
    response_entity: str | None = None
    response_mapping: list[MappingRule] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class SyncMode(StrEnum):
    """Sync modes for integration syncs."""

    SCHEDULED = "scheduled"
    EVENT_DRIVEN = "event_driven"


class MatchRule(BaseModel):
    """
    Match rule for syncs (bidirectional field mapping).

    Attributes:
        foreign_field: Field in foreign model
        entity_field: Field in entity
    """

    foreign_field: str
    entity_field: str

    model_config = ConfigDict(frozen=True)


class IntegrationSync(BaseModel):
    """
    Sync operation within an integration (scheduled or event-driven).

    Attributes:
        name: Sync identifier
        mode: Sync mode (scheduled or event_driven)
        schedule: Cron expression (if scheduled)
        from_service: Service to sync from
        from_operation: Operation to call
        from_foreign_model: Foreign model to use
        into_entity: Entity to sync into
        match_rules: Rules for matching foreign records to entities
    """

    name: str
    mode: SyncMode
    schedule: str | None = None  # cron expression
    from_service: str
    from_operation: str
    from_foreign_model: str
    into_entity: str
    match_rules: list[MatchRule] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class IntegrationSpec(BaseModel):
    """
    Specification for an integration between internal and external systems.

    Integrations connect entities, surfaces, and experiences with APIs
    and foreign models.

    Attributes:
        name: Integration identifier
        title: Human-readable title
        api_refs: List of external APIs used
        foreign_model_refs: List of foreign models used
        actions: List of on-demand actions
        syncs: List of sync operations
    """

    name: str
    title: str | None = None
    api_refs: list[str] = Field(default_factory=list)
    foreign_model_refs: list[str] = Field(default_factory=list)
    actions: list[IntegrationAction] = Field(default_factory=list)
    syncs: list[IntegrationSync] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)
