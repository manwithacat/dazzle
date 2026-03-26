"""Conformance case derivation engine.

Derives a list of ConformanceCase objects from an AppSpec using Cedar-style
three-rule evaluation: FORBID > PERMIT > default-deny.
"""

from typing import Any

from .models import ConformanceCase, ScopeOutcome

OPERATIONS = ["list", "create", "read", "update", "delete"]

# Sentinel values for expected_rows:
#   -1  → all rows (no filter applied)
#   -2  → filtered rows (fixture engine determines count)
_ALL_ROWS = -1
_FILTERED_ROWS = -2


def _op_str(operation: Any) -> str:
    """Normalise an operation field that may be a string or an enum-like with .value."""
    if isinstance(operation, str):
        return operation
    val = getattr(operation, "value", None)
    if val is not None:
        return str(val)
    return str(operation)


def _extract_personas(entities: list[Any]) -> set[str]:
    """Collect all persona names mentioned in access specs across all entities."""
    personas: set[str] = set()
    for entity in entities:
        access = getattr(entity, "access", None)
        if access is None:
            continue
        for rule in getattr(access, "permissions", []):
            for p in getattr(rule, "personas", []):
                if p and p != "*":
                    personas.add(p)
        for rule in getattr(access, "scopes", []):
            for p in getattr(rule, "personas", []):
                if p and p != "*":
                    personas.add(p)
    return personas


def _persona_matches_rule(persona: str, rule_personas: list[str]) -> bool:
    """Return True if persona matches this rule's persona list.

    A rule matches if:
    - personas is empty (any persona)
    - persona is in the personas list
    """
    if not rule_personas:
        return True
    return persona in rule_personas


def _find_scope_rule(
    scopes: list[Any],
    operation: str,
    persona: str,
) -> Any | None:
    """Find first scope rule matching (operation, persona).

    Respects '*' wildcard persona.
    Returns None if no matching scope rule exists.
    """
    for rule in scopes:
        if _op_str(getattr(rule, "operation", "")) != operation:
            continue
        rule_personas = getattr(rule, "personas", [])
        if "*" in rule_personas or _persona_matches_rule(persona, rule_personas):
            return rule
    return None


def _derive_for_entity(
    entity: Any,
    personas: set[str],
    auth_enabled: bool,
) -> list[ConformanceCase]:
    """Derive conformance cases for a single entity."""
    cases: list[ConformanceCase] = []
    entity_name: str = entity.name
    access = getattr(entity, "access", None)

    for persona in personas:
        for operation in OPERATIONS:
            # ------------------------------------------------------------------
            # 1. Unauthenticated persona
            # ------------------------------------------------------------------
            if persona == "unauthenticated":
                if auth_enabled:
                    cases.append(
                        ConformanceCase(
                            entity=entity_name,
                            persona=persona,
                            operation=operation,
                            expected_status=401,
                            scope_type=ScopeOutcome.UNAUTHENTICATED,
                            description=f"{entity_name}.{operation}: unauthenticated → 401",
                        )
                    )
                continue

            # ------------------------------------------------------------------
            # 2. No access spec → unprotected
            # ------------------------------------------------------------------
            if access is None:
                expected_rows = _ALL_ROWS if operation == "list" else None
                cases.append(
                    ConformanceCase(
                        entity=entity_name,
                        persona=persona,
                        operation=operation,
                        expected_status=200,
                        expected_rows=expected_rows,
                        scope_type=ScopeOutcome.UNPROTECTED,
                        description=f"{entity_name}.{operation}: no access spec → unprotected",
                    )
                )
                continue

            permissions: list[Any] = getattr(access, "permissions", [])
            scopes: list[Any] = getattr(access, "scopes", [])

            # ------------------------------------------------------------------
            # 3. Check FORBID rules first (Cedar: forbid > permit)
            # ------------------------------------------------------------------
            forbid_matches = [
                r
                for r in permissions
                if _op_str(getattr(r, "operation", "")) == operation
                and getattr(r, "effect", "permit") == "forbid"
                and _persona_matches_rule(persona, getattr(r, "personas", []))
            ]
            if forbid_matches:
                cases.append(
                    ConformanceCase(
                        entity=entity_name,
                        persona=persona,
                        operation=operation,
                        expected_status=403,
                        scope_type=ScopeOutcome.FORBIDDEN,
                        description=f"{entity_name}.{operation}: forbid rule → 403",
                    )
                )
                continue

            # ------------------------------------------------------------------
            # 4. Check PERMIT rules
            # ------------------------------------------------------------------
            permit_matches = [
                r
                for r in permissions
                if _op_str(getattr(r, "operation", "")) == operation
                and getattr(r, "effect", "permit") == "permit"
                and _persona_matches_rule(persona, getattr(r, "personas", []))
            ]
            if not permit_matches:
                cases.append(
                    ConformanceCase(
                        entity=entity_name,
                        persona=persona,
                        operation=operation,
                        expected_status=403,
                        scope_type=ScopeOutcome.ACCESS_DENIED,
                        description=f"{entity_name}.{operation}: no permit rule → 403",
                    )
                )
                continue

            # ------------------------------------------------------------------
            # 5. Permitted — resolve by operation type
            # ------------------------------------------------------------------
            if operation == "list":
                _derive_list_case(cases, entity_name, persona, scopes)

            elif operation == "create":
                cases.append(
                    ConformanceCase(
                        entity=entity_name,
                        persona=persona,
                        operation=operation,
                        expected_status=201,
                        scope_type=ScopeOutcome.ALL,
                        description=f"{entity_name}.{operation}: permitted → 201",
                    )
                )

            else:
                # read, update, delete — two cases: own-row + other-row
                _derive_row_cases(cases, entity_name, persona, operation, scopes)

    return cases


def _derive_list_case(
    cases: list[ConformanceCase],
    entity_name: str,
    persona: str,
    scopes: list[Any],
) -> None:
    """Append a single LIST case based on scope rules."""
    scope_rule = _find_scope_rule(scopes, "list", persona)

    if scope_rule is None:
        # No scope rule → SCOPE_EXCLUDED (default-deny for row filtering)
        cases.append(
            ConformanceCase(
                entity=entity_name,
                persona=persona,
                operation="list",
                expected_status=200,
                expected_rows=0,
                scope_type=ScopeOutcome.SCOPE_EXCLUDED,
                description=f"{entity_name}.list: no scope rule → scope_excluded",
            )
        )
        return

    condition = getattr(scope_rule, "condition", None)
    if condition is None:
        # scope: all
        cases.append(
            ConformanceCase(
                entity=entity_name,
                persona=persona,
                operation="list",
                expected_status=200,
                expected_rows=_ALL_ROWS,
                scope_type=ScopeOutcome.ALL,
                description=f"{entity_name}.list: scope all → 200",
            )
        )
    else:
        # scope with condition
        cases.append(
            ConformanceCase(
                entity=entity_name,
                persona=persona,
                operation="list",
                expected_status=200,
                expected_rows=_FILTERED_ROWS,
                scope_type=ScopeOutcome.FILTERED,
                description=f"{entity_name}.list: scope filtered → 200",
            )
        )


def _derive_row_cases(
    cases: list[ConformanceCase],
    entity_name: str,
    persona: str,
    operation: str,
    scopes: list[Any],
) -> None:
    """Append two cases (own-row + other-row) for read/update/delete."""
    scope_rule = _find_scope_rule(scopes, operation, persona)

    # Determine if persona has scope:all (condition=None on a matching scope rule)
    has_scope_all = scope_rule is not None and getattr(scope_rule, "condition", None) is None

    own_status = 200
    other_status = 200 if has_scope_all else 404

    cases.append(
        ConformanceCase(
            entity=entity_name,
            persona=persona,
            operation=operation,
            expected_status=own_status,
            row_target="own",
            scope_type=ScopeOutcome.ALL if has_scope_all else ScopeOutcome.FILTERED,
            description=f"{entity_name}.{operation}: own-row → {own_status}",
        )
    )
    cases.append(
        ConformanceCase(
            entity=entity_name,
            persona=persona,
            operation=operation,
            expected_status=other_status,
            row_target="other",
            scope_type=ScopeOutcome.ALL if has_scope_all else ScopeOutcome.FILTERED,
            description=f"{entity_name}.{operation}: other-row → {other_status}",
        )
    )


def derive_conformance_cases(
    appspec: Any,
    auth_enabled: bool = True,
) -> list[ConformanceCase]:
    """Derive all conformance cases from an AppSpec.

    Implements Cedar three-rule evaluation: FORBID > PERMIT > default-deny.

    Args:
        appspec: AppSpec (or SimpleNamespace for tests) with a ``domain`` attribute
                 containing an ``entities`` list.
        auth_enabled: When True, generates 401 cases for the ``unauthenticated``
                      synthetic persona.

    Returns:
        Flat list of ConformanceCase objects covering every
        (entity × persona × operation) combination.
    """
    entities: list[Any] = list(getattr(getattr(appspec, "domain", None), "entities", []))

    # Build the full persona set from all access specs
    domain_personas: set[str] = _extract_personas(entities)

    # Add synthetic personas
    synthetic: set[str] = {"unmatched_role"}
    if auth_enabled:
        synthetic.add("unauthenticated")

    all_personas: set[str] = domain_personas | synthetic

    cases: list[ConformanceCase] = []
    for entity in entities:
        cases.extend(_derive_for_entity(entity, all_personas, auth_enabled))

    return cases
