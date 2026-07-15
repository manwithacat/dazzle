"""Generate seed fixture payloads for UX verification.

Produces deterministic test data for each entity in the AppSpec,
formatted for the /__test__/seed endpoint.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from dazzle.core.ir.appspec import AppSpec
from dazzle.testing.ux.seed_values import realistic_email, realistic_str

# Terminal lifecycle statuses — timestamps like resolved_at only make sense here.
_TERMINAL_STATUSES = frozenset(
    {
        "resolved",
        "closed",
        "completed",
        "done",
        "cancelled",
        "canceled",
        "rejected",
        "archived",
    }
)
_TERMINAL_TS_TOKENS = ("resolved", "closed", "completed", "ended", "finished", "cancelled")
_FUTURE_OK_TOKENS = ("due", "deadline", "expires", "expiry", "scheduled", "starts", "start_")


def _past_datetime_iso(*, days_ago: int, hour: int = 10) -> str:
    """UTC datetime strictly in the past (TR-10: no future seed timestamps)."""
    days_ago = max(1, days_ago)
    dt = datetime.now(UTC) - timedelta(days=days_ago, hours=(hour % 12))
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _past_date_iso(*, days_ago: int) -> str:
    days_ago = max(1, days_ago)
    return (datetime.now(UTC).date() - timedelta(days=days_ago)).isoformat()


def _datetime_for_field(field_name: str, index: int) -> str:
    """Field-aware past (or short-horizon due) datetimes relative to *now*."""
    name = field_name.lower()
    if any(tok in name for tok in _FUTURE_OK_TOKENS):
        # Due dates may be slightly in the future — still bounded.
        days = (index % 14) + 1
        dt = datetime.now(UTC) + timedelta(days=days)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if any(tok in name for tok in _TERMINAL_TS_TOKENS):
        # Resolved/closed: 7–34 days ago (before "now", after typical created).
        return _past_datetime_iso(days_ago=7 + (index % 28), hour=14)
    if "created" in name:
        return _past_datetime_iso(days_ago=45 + index * 3, hour=9)
    if "updated" in name:
        return _past_datetime_iso(days_ago=3 + index, hour=11)
    # Generic datetime: recent past
    return _past_datetime_iso(days_ago=(index % 28) + 1, hour=10)


def _scrub_lifecycle_timestamps(data: dict[str, Any]) -> None:
    """Drop terminal timestamps/resolution on non-terminal rows (TR-10).

    Avoids open tickets with resolved_at in the past (or before created_at when
    created_at is DB auto_add=now), which trials read as broken integrity.
    """
    status = str(data.get("status") or "").lower()
    if status in _TERMINAL_STATUSES:
        return
    for key in list(data.keys()):
        lower = key.lower()
        if any(tok in lower for tok in _TERMINAL_TS_TOKENS) and (
            lower.endswith("_at") or lower in ("resolution", "outcome", "close_reason")
        ):
            data.pop(key, None)
        elif lower == "resolution" and status in {
            "open",
            "in_progress",
            "new",
            "pending",
            "triage",
        }:
            data.pop(key, None)


def _generate_field_value(field_name: str, field_type: str, entity_name: str, index: int) -> Any:
    """Generate a deterministic test value for a field.

    String-valued fields go through :func:`realistic_str` so seed
    fixtures don't look obviously artificial ("Test first_name 1")
    during qualitative evaluation — see #809. Non-string types keep
    their deterministic shape (UUIDs, dates) so fixture ids remain
    reproducible across runs. Datetimes are *relative to now* (TR-10)
    so seeds never look future-dated next to auto_add created_at.
    """
    t = field_type.lower()

    if field_name == "id":
        # Deterministic UUID from entity name + index
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{entity_name}.{index}"))

    # Field-name-aware generation (overrides type-based)
    if field_name == "email" or "email" in field_name:
        return realistic_email(entity_name, index)

    if "str" in t or "text" in t:
        return realistic_str(field_name, index)
    if t == "email":
        return realistic_email(entity_name, index)
    if "int" in t or "decimal" in t or "float" in t:
        return index + 1
    if t == "bool":
        return True
    if "date" in t and "time" not in t:
        name = field_name.lower()
        if any(tok in name for tok in _FUTURE_OK_TOKENS):
            return (datetime.now(UTC).date() + timedelta(days=(index % 14) + 1)).isoformat()
        return _past_date_iso(days_ago=(index % 28) + 7)
    if "datetime" in t:
        return _datetime_for_field(field_name, index)
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

    return realistic_str(field_name, index)


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

    # Seed in FK-dependency order (referenced entities first) so a required
    # FK on a referencing entity resolves to an already-emitted fixture id.
    # In declaration order, an entity whose required FK target appears later
    # gets its ref skipped (target not yet in `first_fixture_id`) → the
    # /__test__/seed insert fails the NOT NULL constraint → that entity's
    # table stays empty → `list_page` contracts spuriously fail with "no
    # clickable rows". Topological ordering fixes FK-chain apps (e.g.
    # acme_billing: Organization ← Project/User ← Invoice/Membership).
    from dazzle.demo_data.loader import topological_sort_entities

    entities_by_name = {e.name: e for e in appspec.domain.entities}
    ordered_names = topological_sort_entities(appspec.domain.entities)

    for entity_name in ordered_names:
        entity = entities_by_name.get(entity_name)
        if entity is None or entity.name not in surfaced_entities:
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

            # TR-10: open/in_progress rows must not carry resolved_at/resolution.
            _scrub_lifecycle_timestamps(data)

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
