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

    # Field-name-aware generation (overrides type-based)
    # Use ux-verify prefix to avoid collisions with auth demo users
    if field_name == "email" or "email" in field_name:
        return f"uxv-{index + 1}@{entity_name.lower()}.test"

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
    """Generate a seed payload for ``/__test__/seed``.

    Returns:
        Dict with ``fixtures`` key containing list of fixture dicts.
        FK references use the ``refs`` field so the seed endpoint can
        resolve fixture IDs to real entity UUIDs.
    """
    fixtures: list[dict[str, Any]] = []
    first_fixture_id: dict[str, str] = {}  # entity_name -> first fixture ID

    # Generate fixtures for user-defined entities that have surfaces.
    # Exclude framework-generated entities (platform admin) — they may
    # not have DB tables and aren't the focus of UX verification.
    _FRAMEWORK_ENTITIES = frozenset(
        {
            "AIJob",
            "FeedbackReport",
            "SystemHealth",
            "SystemMetric",
            "DeployHistory",
        }
    )
    surfaced_entities = {
        s.entity_ref
        for s in appspec.surfaces
        if s.entity_ref and s.entity_ref not in _FRAMEWORK_ENTITIES
    }

    for entity in appspec.domain.entities:
        if entity.name not in surfaced_entities:
            continue

        for i in range(rows_per_entity):
            fixture_id = f"{entity.name.lower()}_{i}"
            data: dict[str, Any] = {}
            fixture_refs: dict[str, str] = {}

            for field in entity.fields:
                # Skip auto-generated fields
                if field.name == "id":
                    continue
                modifiers = (
                    [str(m) for m in (field.modifiers or [])] if hasattr(field, "modifiers") else []
                )
                # Skip auto-timestamp fields
                if "auto_add" in modifiers or "auto_update" in modifiers:
                    continue

                # Handle FK references — use refs dict for seed endpoint resolution
                type_str = _get_field_type_str(field.type)
                ref_entity = getattr(field.type, "ref_entity", None)
                if ref_entity is not None or type_str.lower() == "ref":
                    if ref_entity and ref_entity in first_fixture_id:
                        fixture_refs[field.name] = first_fixture_id[ref_entity]
                    continue

                # Skip optional fields sometimes (keep data payload small)
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

            fixture: dict[str, Any] = {
                "id": fixture_id,
                "entity": entity.name,
                "data": data,
            }
            if fixture_refs:
                fixture["refs"] = fixture_refs
            fixtures.append(fixture)

            # Track first fixture ID for FK resolution
            if entity.name not in first_fixture_id:
                first_fixture_id[entity.name] = fixture_id

    return {"fixtures": fixtures}
