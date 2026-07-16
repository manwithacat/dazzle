"""
Model generator - generates Pydantic models from EntitySpec.

This module creates dynamic Pydantic models at runtime from BackendSpec entity definitions.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, create_model

from dazzle.http.runtime.slug_validator import validate_slug
from dazzle.http.specs.entity import (
    EntitySpec,
    FieldSpec,
    FieldType,
    ScalarType,
)
from dazzle.i18n.display_locale import calendar_today

# Try to import relativedelta for months/years arithmetic
try:
    from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped,unused-ignore]

    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False

# =============================================================================
# Type Mapping
# =============================================================================


def _scalar_type_to_python(scalar_type: ScalarType) -> type:
    """Map scalar types to Python types.

    Keep this aligned with the runtime ``ScalarType`` enum in
    ``dazzle.http/specs/entity.py``; the silent ``str`` fallback used to
    let new types slip through (#1012 — ``FLOAT`` fields produced models
    typed as ``str``, breaking pydantic validation when the DB returned
    an actual float). Money fields are pre-expanded by the entity
    converter into ``_minor`` (INT) + ``_currency`` (STR), so they
    never reach this mapping directly.
    """
    # SLUG returns Annotated[str, AfterValidator(validate_slug)] so the
    # generated request models enforce the slug rules at the FastAPI
    # boundary — see dazzle.http.runtime.slug_validator (#1288).
    if scalar_type == ScalarType.SLUG:
        return Annotated[str, AfterValidator(validate_slug)]  # type: ignore[return-value]

    mapping: dict[ScalarType, type] = {
        ScalarType.STR: str,
        ScalarType.TEXT: str,
        ScalarType.INT: int,
        ScalarType.DECIMAL: Decimal,
        ScalarType.FLOAT: float,
        ScalarType.BOOL: bool,
        ScalarType.DATE: date,
        ScalarType.DATETIME: datetime,
        ScalarType.UUID: UUID,
        ScalarType.EMAIL: str,
        ScalarType.URL: str,
        ScalarType.JSON: dict,
    }
    return mapping.get(scalar_type, str)


def _make_enum_validator(allowed: list[str], field_name: str) -> Callable[[str], str]:
    """Create a validator function that checks enum values."""

    def _validate(v: str) -> str:
        if v not in allowed:
            raise ValueError(
                f"Invalid value '{v}' for '{field_name}'. Allowed: {', '.join(allowed)}"
            )
        return v

    return _validate


def _field_type_to_python(
    field_type: FieldType, entity_models: dict[str, type], field_name: str = ""
) -> type:
    """
    Convert FieldType to Python type.

    Args:
        field_type: The field type specification
        entity_models: Dictionary of already-generated entity models (for refs)
        field_name: Field name for error messages (used by enum validation)

    Returns:
        Python type for Pydantic model
    """
    if field_type.kind == "scalar" and field_type.scalar_type:
        return _scalar_type_to_python(field_type.scalar_type)
    elif field_type.kind == "enum" and field_type.enum_values:
        return Annotated[
            str, AfterValidator(_make_enum_validator(field_type.enum_values, field_name))
        ]  # type: ignore[return-value]
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
        # Get base value. UTC-aware, matching the auto_add timestamp path
        # (service_generator uses datetime.now(UTC)) and the timestamptz
        # columns these land in — a naive local datetime stores skewed
        # (#1529 review finding; `today` stays a plain local date).
        if kind == "now":
            base: date | datetime = datetime.now(UTC)
        else:  # "today" — tenant-timezone calendar day (#1597 C)
            base = calendar_today()

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
    python_type = _field_type_to_python(field.type, {}, field.name)

    # Build Field kwargs
    field_kwargs: dict[str, Any] = {}

    if field.label:
        field_kwargs["description"] = field.label

    # Handle default value
    if field.default is not None:
        from dazzle.core.ir.params import ParamRef

        raw_default = (
            field.default.default if isinstance(field.default, ParamRef) else field.default
        )
        # v0.10.2: Check for date expression (dictionary with 'kind')
        if raw_default is not None and _is_date_expr(raw_default):
            field_kwargs["default_factory"] = _create_date_factory(raw_default)
        elif raw_default is not None:
            field_kwargs["default"] = raw_default
    elif not field.required:
        field_kwargs["default"] = None
        # Make type Optional
        python_type = python_type | None  # type: ignore[assignment]

    # Handle string max_length
    if field.type.max_length:
        field_kwargs["max_length"] = field.type.max_length

    # Build the field definition
    if field_kwargs:
        return (python_type, Field(**field_kwargs))
    elif field.required:
        return (python_type, ...)
    else:
        return (python_type | None, None)  # type: ignore[return-value]


# =============================================================================
# Model Generation
# =============================================================================


def _create_typed_model(name: str, doc: str, fields: dict[str, Any]) -> type[BaseModel]:
    """Create a Pydantic model from dynamic field definitions."""
    model = create_model(name, __doc__=doc, **fields)
    assert issubclass(model, BaseModel)
    return model  # type: ignore[no-any-return]


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
    return _create_typed_model(
        entity.name,
        entity.description or f"Generated model for {entity.name}",
        field_definitions,
    )


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


def _auto_excluded_fields(
    entity: EntitySpec,
    *,
    partition_key: str | None = None,
    tenant_scoped: bool = False,
) -> frozenset[str]:
    """Return the set of field names that should be excluded from create/update schemas.

    Always excludes 'id', plus any fields marked auto_add or auto_update. auth
    Plan 1d: also excludes the framework-injected partition key for tenant-scoped
    entities — it is server-supplied (the DB default fills it from the bound
    session GUC), never a client input field.
    """
    excluded = {"id"}
    for field in entity.fields:
        if field.auto_add or field.auto_update:
            excluded.add(field.name)
    if tenant_scoped and partition_key:
        excluded.add(partition_key)
    return frozenset(excluded)


def generate_create_schema(
    entity: EntitySpec,
    name_suffix: str = "Create",
    *,
    partition_key: str | None = None,
    tenant_scoped: bool = False,
) -> type[BaseModel]:
    """
    Generate a Pydantic schema for creating an entity.

    Excludes auto-generated fields like id, created_at, updated_at, and (for a
    tenant-scoped entity) the framework-injected partition key (Plan 1d).

    Args:
        entity: Entity specification
        name_suffix: Suffix for the schema name
        partition_key: The tenant discriminator column name (when tenant_scoped)
        tenant_scoped: Whether this entity carries the framework partition key

    Returns:
        Pydantic model for create operations
    """
    # Fields to exclude from create schema: id + any auto_add/auto_update + the
    # framework partition key (when tenant-scoped).
    auto_fields = _auto_excluded_fields(
        entity, partition_key=partition_key, tenant_scoped=tenant_scoped
    )

    # Build field definitions
    field_definitions: dict[str, Any] = {}

    for field in entity.fields:
        if field.name in auto_fields:
            continue
        field_definitions[field.name] = _build_field_info(field)

    # Create the model
    return _create_typed_model(
        f"{entity.name}{name_suffix}",
        f"Create schema for {entity.name}",
        field_definitions,
    )


def generate_update_schema(
    entity: EntitySpec,
    name_suffix: str = "Update",
    *,
    partition_key: str | None = None,
    tenant_scoped: bool = False,
) -> type[BaseModel]:
    """
    Generate a Pydantic schema for updating an entity.

    All fields are optional to support partial updates. The framework partition
    key is excluded for tenant-scoped entities (Plan 1d — server-managed).

    Args:
        entity: Entity specification
        name_suffix: Suffix for the schema name
        partition_key: The tenant discriminator column name (when tenant_scoped)
        tenant_scoped: Whether this entity carries the framework partition key

    Returns:
        Pydantic model for update operations
    """
    # Fields to exclude from update schema: id + any auto_add/auto_update + the
    # framework partition key (when tenant-scoped).
    auto_fields = _auto_excluded_fields(
        entity, partition_key=partition_key, tenant_scoped=tenant_scoped
    )

    # Build field definitions - all optional for updates
    field_definitions: dict[str, Any] = {}

    for field in entity.fields:
        if field.name in auto_fields:
            continue

        python_type = _field_type_to_python(field.type, {}, field.name)
        # Make all fields optional for partial updates
        field_definitions[field.name] = (python_type | None, None)

    # Create the model
    return _create_typed_model(
        f"{entity.name}{name_suffix}",
        f"Update schema for {entity.name}",
        field_definitions,
    )


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
        "items": (list[entity_model], Field(description=f"List of {entity.name} items")),  # type: ignore[valid-type]
        "total": (int, Field(description="Total number of items")),
        "page": (int, Field(default=1, description="Current page")),
        "page_size": (int, Field(default=20, description="Items per page")),
    }

    return _create_typed_model(
        f"{entity.name}ListResponse",
        f"Paginated list response for {entity.name}",
        field_definitions,
    )
