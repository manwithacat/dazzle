"""
Entity converter - converts Dazzle IR EntitySpec to DNR BackendSpec EntitySpec.

This module handles the transformation of Dazzle's domain entities into
DNR's framework-agnostic BackendSpec format.
"""

from dazzle.core import ir
from dazzle_dnr_back.specs import (
    EntitySpec,
    FieldSpec,
    FieldType,
    RelationKind,
    RelationSpec,
    ScalarType,
    ValidatorKind,
    ValidatorSpec,
)

# =============================================================================
# Type Mapping
# =============================================================================


def _map_field_type(dazzle_type: ir.FieldType) -> FieldType:
    """
    Map Dazzle IR FieldType to DNR BackendSpec FieldType.

    Handles scalar types, enums, and references.
    """
    kind = dazzle_type.kind

    # Map scalar types
    scalar_map = {
        ir.FieldTypeKind.STR: ScalarType.STR,
        ir.FieldTypeKind.TEXT: ScalarType.TEXT,
        ir.FieldTypeKind.INT: ScalarType.INT,
        ir.FieldTypeKind.DECIMAL: ScalarType.DECIMAL,
        ir.FieldTypeKind.BOOL: ScalarType.BOOL,
        ir.FieldTypeKind.DATE: ScalarType.DATE,
        ir.FieldTypeKind.DATETIME: ScalarType.DATETIME,
        ir.FieldTypeKind.UUID: ScalarType.UUID,
        ir.FieldTypeKind.EMAIL: ScalarType.EMAIL,
    }

    if kind == ir.FieldTypeKind.ENUM:
        # Enum type
        return FieldType(
            kind="enum",
            enum_values=dazzle_type.enum_values or [],
        )
    elif kind == ir.FieldTypeKind.REF:
        # Reference type
        return FieldType(
            kind="ref",
            ref_entity=dazzle_type.ref_entity,
        )
    elif kind in scalar_map:
        # Scalar type
        return FieldType(
            kind="scalar",
            scalar_type=scalar_map[kind],
            max_length=dazzle_type.max_length,
            precision=dazzle_type.precision,
            scale=dazzle_type.scale,
        )
    else:
        # Default to string for unknown types
        return FieldType(kind="scalar", scalar_type=ScalarType.STR)


def _extract_validators(field: ir.FieldSpec) -> list[ValidatorSpec]:
    """
    Extract validators from field modifiers and type constraints.
    """
    validators: list[ValidatorSpec] = []

    # Add validators based on field type
    if field.type.kind == ir.FieldTypeKind.EMAIL:
        validators.append(ValidatorSpec(kind=ValidatorKind.EMAIL))

    # Add max_length validator for string types
    if field.type.max_length:
        validators.append(
            ValidatorSpec(kind=ValidatorKind.MAX_LENGTH, value=field.type.max_length)
        )

    # Add precision/scale for decimal (not validators, but useful metadata)
    # These would be handled by the type itself

    return validators


# =============================================================================
# Field Conversion
# =============================================================================


def convert_field(dazzle_field: ir.FieldSpec) -> FieldSpec:
    """
    Convert a Dazzle IR FieldSpec to DNR BackendSpec FieldSpec.

    Args:
        dazzle_field: Dazzle IR field specification

    Returns:
        DNR BackendSpec field specification
    """
    return FieldSpec(
        name=dazzle_field.name,
        label=dazzle_field.name.replace("_", " ").title(),
        type=_map_field_type(dazzle_field.type),
        required=dazzle_field.is_required or dazzle_field.is_primary_key,
        default=dazzle_field.default,
        validators=_extract_validators(dazzle_field),
        indexed=dazzle_field.is_primary_key,
        unique=dazzle_field.is_unique or dazzle_field.is_primary_key,
    )


# =============================================================================
# Entity Conversion
# =============================================================================


def convert_entity(dazzle_entity: ir.EntitySpec) -> EntitySpec:
    """
    Convert a Dazzle IR EntitySpec to DNR BackendSpec EntitySpec.

    Args:
        dazzle_entity: Dazzle IR entity specification

    Returns:
        DNR BackendSpec entity specification
    """
    # Convert fields
    fields = [convert_field(f) for f in dazzle_entity.fields]

    # Note: Relations are inferred from ref fields
    # In a real implementation, we'd need more sophisticated relation detection
    relations: list[RelationSpec] = []

    # Extract relations from ref fields
    for field in dazzle_entity.fields:
        if field.type.kind == ir.FieldTypeKind.REF and field.type.ref_entity:
            relations.append(
                RelationSpec(
                    name=field.name,
                    from_entity=dazzle_entity.name,
                    to_entity=field.type.ref_entity,
                    kind=RelationKind.MANY_TO_ONE,  # Assume many-to-one for ref fields
                    required=field.is_required,
                )
            )

    return EntitySpec(
        name=dazzle_entity.name,
        label=dazzle_entity.title or dazzle_entity.name,
        description=dazzle_entity.title,
        fields=fields,
        relations=relations,
    )


def convert_entities(
    dazzle_entities: list[ir.EntitySpec],
) -> list[EntitySpec]:
    """
    Convert a list of Dazzle IR entities to DNR BackendSpec entities.

    Args:
        dazzle_entities: List of Dazzle IR entity specifications

    Returns:
        List of DNR BackendSpec entity specifications
    """
    return [convert_entity(e) for e in dazzle_entities]
