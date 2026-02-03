"""
Demo Data Blueprint IR Types.

Defines the schema for Demo Data Blueprints that guide LLM agents
in generating realistic, domain-specific demo data.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FieldStrategy(StrEnum):
    """Strategy for generating field values."""

    STATIC_LIST = "static_list"
    ENUM_WEIGHTED = "enum_weighted"
    PERSON_NAME = "person_name"
    COMPANY_NAME = "company_name"
    EMAIL_FROM_NAME = "email_from_name"
    USERNAME_FROM_NAME = "username_from_name"
    HASHED_PASSWORD_PLACEHOLDER = "hashed_password_placeholder"  # nosec B105
    FREE_TEXT_LOREM = "free_text_lorem"
    NUMERIC_RANGE = "numeric_range"
    CURRENCY_AMOUNT = "currency_amount"
    DATE_RELATIVE = "date_relative"
    BOOLEAN_WEIGHTED = "boolean_weighted"
    FOREIGN_KEY = "foreign_key"
    COMPOSITE = "composite"
    CUSTOM_PROMPT = "custom_prompt"
    UUID_GENERATE = "uuid_generate"


class FieldPattern(BaseModel):
    """Pattern for generating a field's value.

    Attributes:
        field_name: Name of the field in the entity
        strategy: Generation strategy to use
        params: Strategy-specific parameters
    """

    field_name: str
    strategy: FieldStrategy
    params: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class EntityBlueprint(BaseModel):
    """Blueprint for generating demo data for an entity.

    Attributes:
        name: Entity name from DSL
        row_count_default: Number of rows to generate
        notes: Human-readable notes about this entity
        tenant_scoped: Whether entity includes tenant_id
        field_patterns: Patterns for each field
    """

    name: str
    row_count_default: int = 10
    notes: str | None = None
    tenant_scoped: bool = False
    field_patterns: list[FieldPattern] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class TenantBlueprint(BaseModel):
    """Blueprint for a demo tenant.

    Attributes:
        name: Company name (e.g., "Alpha Solar Ltd")
        slug: URL-safe identifier
        notes: Notes about this tenant
    """

    name: str
    slug: str | None = None
    notes: str | None = None

    model_config = ConfigDict(frozen=True)


class PersonaBlueprint(BaseModel):
    """Blueprint for demo users of a persona.

    Attributes:
        persona_name: Name from DSL persona definition
        description: Human-readable description
        default_role: ACL role to assign
        default_user_count: Number of users per tenant
    """

    persona_name: str
    description: str
    default_role: str | None = None
    default_user_count: int = 1

    model_config = ConfigDict(frozen=True)


class DemoDataBlueprint(BaseModel):
    """Complete blueprint for demo data generation.

    This is the top-level schema that defines how to generate
    all demo data for a project, including tenants, users, and
    business entities.

    Attributes:
        project_id: Project identifier
        domain_description: 1-3 sentence domain description
        seed: Random seed for reproducibility
        tenants: Demo tenant definitions
        personas: Demo user persona definitions
        entities: Entity generation blueprints
    """

    project_id: str
    domain_description: str
    seed: int | None = None
    tenants: list[TenantBlueprint] = Field(default_factory=list)
    personas: list[PersonaBlueprint] = Field(default_factory=list)
    entities: list[EntityBlueprint] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class BlueprintContainer(BaseModel):
    """Container for persisting blueprints with version info.

    Attributes:
        version: Schema version
        blueprint: The actual blueprint
    """

    version: str = "1.0"
    blueprint: DemoDataBlueprint

    model_config = ConfigDict(frozen=True)
