"""
Model generator - generates Pydantic models from EntitySpec.

This module creates dynamic Pydantic models at runtime from BackendSpec entity definitions.
"""

from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, create_model

from dazzle_dnr_back.specs.entity import (
    EntitySpec,
    FieldSpec,
    FieldType,
    ScalarType,
)

# Try to import relativedelta for months/years arithmetic
try:
    from dateutil.relativedelta import relativedelta

    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False

# =============================================================================
# Type Mapping
# =============================================================================


def _scalar_type_to_python(scalar_type: ScalarType) -> type:
    """Map scalar types to Python types."""
    mapping: dict[ScalarType, type] = {
        ScalarType.STR: str,
        ScalarType.TEXT: str,
        ScalarType.INT: int,
        ScalarType.DECIMAL: Decimal,
        ScalarType.BOOL: bool,
        ScalarType.DATE: date,
        ScalarType.DATETIME: datetime,
        ScalarType.UUID: UUID,
        ScalarType.EMAIL: str,
        ScalarType.URL: str,
        ScalarType.JSON: dict,
    }
    return mapping.get(scalar_type, str)


def _field_type_to_python(field_type: FieldType, entity_models: dict[str, type]) -> type:
    """
    Convert FieldType to Python type.

    Args:
        field_type: The field type specification
        entity_models: Dictionary of already-generated entity models (for refs)

    Returns:
        Python type for Pydantic model
    """
    if field_type.kind == "scalar" and field_type.scalar_type:
        return _scalar_type_to_python(field_type.scalar_type)
    elif field_type.kind == "enum" and field_type.enum_values:
        # Return str for enums - could create Enum class if needed
        return str
    elif field_type.kind == "ref" and field_type.ref_entity:
        # References are stored as UUIDs (foreign keys)
        return UUID
    else:
        return str


def _is_date_expr(default: Any) -> bool:
    """Check if default is a date expression dictionary."""
    return isinstance(default, dict) and "kind" in default


def _create_date_factory(expr: dict[str, Any]) -> Callable[[], date | datetime]:
    """
    Create a factory function for date expression defaults.

    v0.10.2: Supports date arithmetic with all duration units.

    Args:
        expr: Date expression dictionary with keys:
            - kind: "today" or "now"
            - op: "+" or "-" (optional)
            - value: duration value (optional)
            - unit: duration unit (optional)

    Returns:
        Factory function that returns evaluated date/datetime
    """
    kind = expr.get("kind", "today")
    op = expr.get("op")
    value = expr.get("value", 0)
    unit = expr.get("unit", "days")

    def factory() -> date | datetime:
        # Get base value
        if kind == "now":
            base: date | datetime = datetime.now()
        else:  # "today"
            base = date.today()

        # No arithmetic, return base
        if not op:
            return base

        # Calculate duration
        if unit == "minutes":
            delta = timedelta(minutes=value)
        elif unit == "hours":
            delta = timedelta(hours=value)
        elif unit == "days":
            delta = timedelta(days=value)
        elif unit == "weeks":
            delta = timedelta(weeks=value)
        elif unit in ("months", "years"):
            # Use relativedelta for variable-length units
            if HAS_DATEUTIL:
                if unit == "months":
                    delta = relativedelta(months=value)
                else:
                    delta = relativedelta(years=value)
            else:
                # Fallback: approximate months=30 days, years=365 days
                if unit == "months":
                    delta = timedelta(days=value * 30)
                else:
                    delta = timedelta(days=value * 365)
        else:
            delta = timedelta(days=value)

        # Apply operation
        if op == "+":
            return base + delta
        else:  # "-"
            return base - delta

    return factory


def _build_field_info(field: FieldSpec) -> tuple[type, Any]:
    """
    Build Pydantic field tuple for create_model.

    Returns:
        Tuple of (type, default_or_field_info)

    v0.10.2: Supports date expression defaults with default_factory.
    """
    # Get Python type
    python_type = _field_type_to_python(field.type, {})

    # Build Field kwargs
    field_kwargs: dict[str, Any] = {}

    if field.label:
        field_kwargs["description"] = field.label

    # Handle default value
    if field.default is not None:
        # v0.10.2: Check for date expression (dictionary with 'kind')
        if _is_date_expr(field.default):
            field_kwargs["default_factory"] = _create_date_factory(field.default)
        else:
            field_kwargs["default"] = field.default
    elif not field.required:
        field_kwargs["default"] = None
        # Make type Optional
        python_type = python_type | None  # type: ignore

    # Handle string max_length
    if field.type.max_length:
        field_kwargs["max_length"] = field.type.max_length

    # Build the field definition
    if field_kwargs:
        return (python_type, Field(**field_kwargs))
    elif field.required:
        return (python_type, ...)
    else:
        return (python_type | None, None)


# =============================================================================
# Model Generation
# =============================================================================


def generate_entity_model(
    entity: EntitySpec,
    entity_models: dict[str, type] | None = None,
) -> type[BaseModel]:
    """
    Generate a Pydantic model from an EntitySpec.

    Args:
        entity: Entity specification
        entity_models: Dictionary of already-generated models (for refs)

    Returns:
        Dynamically created Pydantic model class

    Example:
        >>> entity = EntitySpec(name="Task", fields=[...])
        >>> TaskModel = generate_entity_model(entity)
        >>> task = TaskModel(title="My Task", status="pending")
    """
    entity_models = entity_models or {}

    # Build field definitions
    field_definitions: dict[str, Any] = {}

    # Always add an id field if not present
    has_id = any(f.name == "id" for f in entity.fields)
    if not has_id:
        field_definitions["id"] = (
            UUID | None,
            Field(default=None, description="Unique identifier"),
        )

    # Add fields from spec
    for field in entity.fields:
        field_definitions[field.name] = _build_field_info(field)

    # Create the model
    model = create_model(
        entity.name,
        __doc__=entity.description or f"Generated model for {entity.name}",
        **field_definitions,
    )

    return model


def generate_all_entity_models(
    entities: list[EntitySpec],
) -> dict[str, type[BaseModel]]:
    """
    Generate Pydantic models for all entities.

    Handles dependencies between entities (refs).

    Args:
        entities: List of entity specifications

    Returns:
        Dictionary mapping entity names to generated models
    """
    models: dict[str, type[BaseModel]] = {}

    # Simple two-pass approach:
    # 1. Generate all models without resolving refs
    # 2. Refs are handled as UUID fields (foreign keys)

    for entity in entities:
        models[entity.name] = generate_entity_model(entity, models)

    return models


# =============================================================================
# Create/Update Schemas
# =============================================================================


def generate_create_schema(
    entity: EntitySpec,
    name_suffix: str = "Create",
) -> type[BaseModel]:
    """
    Generate a Pydantic schema for creating an entity.

    Excludes auto-generated fields like id, created_at, updated_at.

    Args:
        entity: Entity specification
        name_suffix: Suffix for the schema name

    Returns:
        Pydantic model for create operations
    """
    # Fields to exclude from create schema
    auto_fields = {"id", "created_at", "updated_at"}

    # Build field definitions
    field_definitions: dict[str, Any] = {}

    for field in entity.fields:
        if field.name in auto_fields:
            continue
        field_definitions[field.name] = _build_field_info(field)

    # Create the model
    model = create_model(
        f"{entity.name}{name_suffix}",
        __doc__=f"Create schema for {entity.name}",
        **field_definitions,
    )

    return model


def generate_update_schema(
    entity: EntitySpec,
    name_suffix: str = "Update",
) -> type[BaseModel]:
    """
    Generate a Pydantic schema for updating an entity.

    All fields are optional to support partial updates.

    Args:
        entity: Entity specification
        name_suffix: Suffix for the schema name

    Returns:
        Pydantic model for update operations
    """
    # Fields to exclude from update schema
    auto_fields = {"id", "created_at", "updated_at"}

    # Build field definitions - all optional for updates
    field_definitions: dict[str, Any] = {}

    for field in entity.fields:
        if field.name in auto_fields:
            continue

        python_type = _field_type_to_python(field.type, {})
        # Make all fields optional for partial updates
        field_definitions[field.name] = (python_type | None, None)

    # Create the model
    model = create_model(
        f"{entity.name}{name_suffix}",
        __doc__=f"Update schema for {entity.name}",
        **field_definitions,
    )

    return model


def generate_list_response_schema(
    entity: EntitySpec,
    entity_model: type[BaseModel],
) -> type[BaseModel]:
    """
    Generate a Pydantic schema for list responses with pagination.

    Args:
        entity: Entity specification
        entity_model: The generated entity model

    Returns:
        Pydantic model for list responses
    """
    field_definitions: dict[str, Any] = {
        "items": (list[entity_model], Field(description=f"List of {entity.name} items")),  # type: ignore
        "total": (int, Field(description="Total number of items")),
        "page": (int, Field(default=1, description="Current page")),
        "page_size": (int, Field(default=20, description="Items per page")),
    }

    model = create_model(
        f"{entity.name}ListResponse",
        __doc__=f"Paginated list response for {entity.name}",
        **field_definitions,
    )

    return model
