"""Conformance fixture engine.

Generates deterministic seed data (users, entity rows, expected counts) from an
AppSpec and a list of ConformanceCase objects produced by the derivation engine.

Design constraints:
- All UUIDs are deterministic via conformance_uuid() so test runs are reproducible.
- The engine does NOT evaluate predicate trees. It uses simple heuristics:
    scope:all (condition=None)  → all 4 rows visible
    scope with any condition    → 2 rows visible (rows owned by User A)
    no scope rule               → 0 rows (scope_excluded / default-deny)
- expected_rows sentinels (-1, -2) on ConformanceCase objects are resolved
  in-place so callers see final counts after generate_fixtures() returns.
"""

from __future__ import annotations

from typing import Any

from .models import ConformanceCase, ConformanceFixtures, ScopeOutcome, conformance_uuid

# Sentinel values imported from derivation (duplicated here to avoid circular import)
_ALL_ROWS = -1
_FILTERED_ROWS = -2

# Total rows generated per scoped entity
_TOTAL_ROWS = 4


def _extract_real_personas(cases: list[ConformanceCase]) -> set[str]:
    """Return persona names that are not synthetic (unauthenticated, unmatched_role)."""
    synthetic = {"unauthenticated", "unmatched_role"}
    return {c.persona for c in cases if c.persona not in synthetic}


def _entities_needing_rows(cases: list[ConformanceCase]) -> set[str]:
    """Return entity names that have at least one list case with a non-None expected_rows.

    Unprotected entities produce UNPROTECTED list cases whose expected_rows is -1
    but there is no meaningful scope to test — however, we include them only when
    there are actual domain personas (not just synthetics) with scoped list cases.
    We include an entity when at least one non-synthetic persona has a list case
    with expected_rows != None and scope_type is not UNPROTECTED/UNAUTHENTICATED.
    """
    synthetic = {"unauthenticated", "unmatched_role"}
    scoped_types = {
        ScopeOutcome.ALL,
        ScopeOutcome.FILTERED,
        ScopeOutcome.SCOPE_EXCLUDED,
    }
    entities: set[str] = set()
    for c in cases:
        if c.operation == "list" and c.persona not in synthetic and c.scope_type in scoped_types:
            entities.add(c.entity)
    return entities


def _build_users(
    personas: set[str],
    entity_name: str,
) -> dict[str, dict[str, Any]]:
    """Create user_a and user_b records for each persona.

    Keys are "{persona}.user_a" / "{persona}.user_b".
    """
    users: dict[str, dict[str, Any]] = {}
    for persona in sorted(personas):
        for slot in ("user_a", "user_b"):
            key = f"{persona}.{slot}"
            users[key] = {
                "id": conformance_uuid(entity_name, key),
                "persona": persona,
                "slot": slot,
            }
    return users


def _build_entity_rows(
    entity: Any,
    personas: set[str],
) -> list[dict[str, Any]]:
    """Generate 4 fixture rows for a scoped entity.

    Row layout:
      0 — owned by first persona's user_a, realm = "realm_a"
      1 — owned by first persona's user_b, realm = "realm_b"
      2 — owned by first persona's user_a, realm = "realm_b"  (different realm)
      3 — owned by first persona's user_b, realm = "realm_a"  (cross-realm)

    We use the lexicographically first persona to anchor ownership so the rows
    are deterministic regardless of set ordering.
    """
    entity_name: str = entity.name
    # Use the first persona (sorted) as the primary owner persona
    primary_persona = sorted(personas)[0] if personas else "default"

    user_a_id = conformance_uuid(entity_name, f"{primary_persona}.user_a")
    user_b_id = conformance_uuid(entity_name, f"{primary_persona}.user_b")

    rows: list[dict[str, Any]] = []
    owners = [user_a_id, user_b_id, user_a_id, user_b_id]
    realms = ["realm_a", "realm_b", "realm_b", "realm_a"]

    fields: list[Any] = getattr(entity, "fields", [])
    ref_field_names = [
        f.name for f in fields if getattr(getattr(f, "type", None), "kind", None) == "ref"
    ]

    for i in range(_TOTAL_ROWS):
        row: dict[str, Any] = {
            "id": conformance_uuid(entity_name, f"row.{i}"),
            "realm": realms[i],
            "_owner_id": owners[i],  # internal reference used by ref-field population
        }
        # Populate ref fields with the owning user's UUID
        for ref_name in ref_field_names:
            row[ref_name] = owners[i]
        rows.append(row)

    return rows


def _resolve_count(
    scope_type: ScopeOutcome,
    expected_rows: int | None,
) -> int | None:
    """Convert sentinel expected_rows to a concrete count.

    Returns:
        Concrete integer count, or None if no list count is relevant.
    """
    if expected_rows == _ALL_ROWS:
        return _TOTAL_ROWS
    if expected_rows == _FILTERED_ROWS:
        # Conservative heuristic: 2 rows belong to User A
        return 2
    if expected_rows == 0:
        return 0
    return expected_rows


def generate_fixtures(
    appspec: Any,
    cases: list[ConformanceCase],
) -> ConformanceFixtures:
    """Generate deterministic fixture data from an AppSpec and derived ConformanceCases.

    This function also updates ``expected_rows`` on each ConformanceCase in-place,
    replacing sentinel values (-1, -2) with the concrete row counts determined by
    the fixture heuristics.

    Args:
        appspec: AppSpec (or SimpleNamespace for tests) with a ``domain.entities`` list.
        cases: ConformanceCase objects from ``derive_conformance_cases()``.
               Modified in-place: sentinel expected_rows values are resolved.

    Returns:
        ConformanceFixtures with populated users, entity_rows, and expected_counts.
    """
    fixtures = ConformanceFixtures()

    real_personas = _extract_real_personas(cases)
    entities_with_rows = _entities_needing_rows(cases)

    # Build an entity lookup by name
    domain_entities: list[Any] = list(getattr(getattr(appspec, "domain", None), "entities", []))
    entity_by_name: dict[str, Any] = {e.name: e for e in domain_entities}

    # Generate users per entity (namespaced so UUIDs are entity-scoped)
    for entity_name in sorted(entities_with_rows):
        entity_users = _build_users(real_personas, entity_name)
        fixtures.users.update(entity_users)

    # Generate entity rows
    for entity_name in sorted(entities_with_rows):
        entity = entity_by_name.get(entity_name)
        if entity is None:
            continue
        fixtures.entity_rows[entity_name] = _build_entity_rows(entity, real_personas)

    # Resolve expected counts and update cases in-place
    for case in cases:
        if case.operation != "list":
            continue
        if case.entity not in entities_with_rows:
            continue

        resolved = _resolve_count(case.scope_type, case.expected_rows)
        if resolved is not None:
            case.expected_rows = resolved
            fixtures.expected_counts[(case.persona, case.entity)] = resolved

    return fixtures
