"""Generate seed fixture payloads for UX verification.

Produces deterministic test data for each entity in the AppSpec,
formatted for the /__test__/seed endpoint.
"""

from __future__ import annotations

import uuid
from typing import Any

from dazzle.core.ir.appspec import AppSpec


def _generate_field_value(field_name: str, field_type: str, entity_name: str, index: int) -> Any:
    """Generate a deterministic test value for a field."""
    t = field_type.lower()

    if field_name == "id":
        # Deterministic UUID from entity name + index
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{entity_name}.{index}"))

    if "str" in t or "text" in t:
        return f"Test {field_name} {index + 1}"
    if t == "email":
        return f"test{index + 1}@{entity_name.lower()}.test"
    if "int" in t or "decimal" in t or "float" in t:
        return index + 1
    if t == "bool":
        return True
    if "date" in t and "time" not in t:
        return f"2026-01-{(index % 28) + 1:02d}"
    if "datetime" in t:
        return f"2026-01-{(index % 28) + 1:02d}T10:00:00Z"
    if "uuid" in t:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{entity_name}.{field_name}.{index}"))
    if "url" in t:
        return f"https://example.com/{entity_name.lower()}/{index + 1}"
    if "json" in t:
        return {}
    if "money" in t:
        return "100.00"
    if "enum" in t:
        return None  # Will be handled by caller if possible
    if "file" in t:
        return None

    return f"test_{field_name}_{index}"


def _get_field_type_str(field_type: Any) -> str:
    """Extract a string representation of a field type."""
    if hasattr(field_type, "kind"):
        return str(field_type.kind)
    if hasattr(field_type, "base_type"):
        return str(field_type.base_type)
    if hasattr(field_type, "value"):
        return str(field_type.value)
    return str(field_type)


def generate_seed_payload(
    appspec: AppSpec,
    rows_per_entity: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """Generate a seed payload for /__test__/seed.

    Returns:
        Dict with "fixtures" key containing list of fixture dicts.
    """
    fixtures: list[dict[str, Any]] = []
    refs: dict[str, str] = {}  # entity_name -> first fixture ID for FK resolution

    # Generate fixtures for entities that have surfaces (testable via UX)
    surfaced_entities = {s.entity_ref for s in appspec.surfaces if s.entity_ref}

    for entity in appspec.domain.entities:
        if entity.name not in surfaced_entities:
            continue

        for i in range(rows_per_entity):
            fixture_id = f"{entity.name.lower()}_{i}"
            data: dict[str, Any] = {}

            for field in entity.fields:
                # Skip auto-generated fields
                if field.name == "id":
                    continue
                modifiers = (
                    [str(m) for m in (field.modifiers or [])] if hasattr(field, "modifiers") else []
                )

                # Handle FK references
                type_str = _get_field_type_str(field.type)
                if "ref" in type_str.lower() or hasattr(field.type, "ref_entity"):
                    ref_entity = getattr(field.type, "ref_entity", None)
                    if ref_entity and ref_entity in refs:
                        data[field.name] = refs[ref_entity]
                    continue

                # Skip optional fields sometimes
                is_required = "required" in modifiers or "pk" in modifiers
                if not is_required and i > 2:
                    continue

                # For enum types, use first enum value if available
                if "enum" in type_str.lower():
                    enum_values = getattr(field.type, "enum_values", None)
                    if enum_values:
                        data[field.name] = enum_values[0]
                    continue

                value = _generate_field_value(field.name, type_str, entity.name, i)
                if value is not None:
                    data[field.name] = value

            fixture = {
                "id": fixture_id,
                "entity": entity.name,
                "data": data,
            }
            fixtures.append(fixture)

            # Track first fixture ID for FK resolution
            if entity.name not in refs:
                refs[entity.name] = fixture_id

    return {"fixtures": fixtures}
