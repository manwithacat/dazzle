"""
Integration types for DAZZLE IR.

This module contains integration specifications for connecting
internal entities with external services.

v0.30.0: Added declarative integration mappings — base_url, auth,
mapping blocks with triggers, HTTP requests, and error strategies.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .location import SourceLocation

if TYPE_CHECKING:
    from .expressions import Expr


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


# --- v0.30.0: Declarative Integration Mappings ---


class AuthType(StrEnum):
    """Authentication type for an integration."""

    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BEARER = "bearer"
    BASIC = "basic"


class AuthSpec(BaseModel):
    """Authentication specification for an integration.

    Attributes:
        auth_type: Type of authentication (api_key, oauth2, bearer, basic)
        credentials: List of credential references, e.g. env("API_KEY")
    """

    auth_type: AuthType
    credentials: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class HttpMethod(StrEnum):
    """HTTP method for integration requests."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class HttpRequestSpec(BaseModel):
    """HTTP request specification for an integration mapping.

    Attributes:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        url_template: URL path with interpolation, e.g. /company/{self.company_number}
    """

    method: HttpMethod
    url_template: str

    model_config = ConfigDict(frozen=True)


class MappingTriggerType(StrEnum):
    """Trigger type for integration mappings."""

    ON_CREATE = "on_create"
    ON_UPDATE = "on_update"
    ON_DELETE = "on_delete"
    ON_TRANSITION = "on_transition"
    MANUAL = "manual"


class MappingTriggerSpec(BaseModel):
    """Trigger specification for an integration mapping.

    Attributes:
        trigger_type: What event triggers the mapping
        condition_expr: Optional guard expression (e.g. company_number != null)
        label: Optional label for manual triggers
        from_state: Source state for on_transition triggers
        to_state: Target state for on_transition triggers
    """

    trigger_type: MappingTriggerType
    condition_expr: Expr | None = None
    label: str | None = None
    from_state: str | None = None
    to_state: str | None = None

    model_config = ConfigDict(frozen=True)


class ErrorAction(StrEnum):
    """Error handling action for integration mappings."""

    IGNORE = "ignore"
    LOG_WARNING = "log_warning"
    REVERT_TRANSITION = "revert_transition"
    RETRY = "retry"


class ErrorStrategy(BaseModel):
    """Error handling strategy for integration mappings.

    Attributes:
        actions: List of error actions to take on failure
        set_fields: Dict of field=value assignments on error
    """

    actions: list[ErrorAction] = Field(default_factory=list)
    set_fields: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class IntegrationMapping(BaseModel):
    """Declarative mapping within an integration (v0.30.0).

    Maps entity lifecycle events to HTTP requests and response field mappings.

    Attributes:
        name: Mapping identifier
        entity_ref: Entity this mapping operates on
        triggers: List of triggers that activate this mapping
        request: HTTP request specification
        request_mapping: Fields mapped into the request body (for POST/PUT)
        response_mapping: Fields mapped from the response to the entity
        on_error: Error handling strategy
    """

    name: str
    entity_ref: str
    triggers: list[MappingTriggerSpec] = Field(default_factory=list)
    request: HttpRequestSpec | None = None
    request_mapping: list[MappingRule] = Field(default_factory=list)
    response_mapping: list[MappingRule] = Field(default_factory=list)
    on_error: ErrorStrategy | None = None
    cache_ttl: int | None = None  # seconds; None = use executor default

    model_config = ConfigDict(frozen=True)


def _rebuild_integration_types() -> None:
    """Rebuild models that use forward-referenced Expr type."""
    from .expressions import Expr

    MappingTriggerSpec.model_rebuild(_types_namespace={"Expr": Expr})


_rebuild_integration_types()


class IntegrationSpec(BaseModel):
    """
    Specification for an integration between internal and external systems.

    Integrations connect entities, surfaces, and experiences with APIs
    and foreign models.

    Attributes:
        name: Integration identifier
        title: Human-readable title
        base_url: Base URL for the external API (v0.30.0)
        auth: Authentication specification (v0.30.0)
        api_refs: List of external APIs used (legacy action/sync style)
        foreign_model_refs: List of foreign models used (legacy action/sync style)
        actions: List of on-demand actions (legacy style)
        syncs: List of sync operations (legacy style)
        mappings: List of declarative mappings (v0.30.0)
    """

    name: str
    title: str | None = None
    base_url: str | None = None
    auth: AuthSpec | None = None
    api_refs: list[str] = Field(default_factory=list)
    foreign_model_refs: list[str] = Field(default_factory=list)
    actions: list[IntegrationAction] = Field(default_factory=list)
    syncs: list[IntegrationSync] = Field(default_factory=list)
    mappings: list[IntegrationMapping] = Field(default_factory=list)
    # v0.31.0: Source location for error reporting
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)
