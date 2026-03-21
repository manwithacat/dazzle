"""Stage-by-stage invariant verification for the predicate compilation chain.

Verifies that each transformation in the DSL-to-SQL compilation chain
preserves semantic intent:

    ConditionExpr → ScopePredicate → (sql, params) → resolved SQL

Three verifier functions test each boundary:

1. ``verify_predicate_build`` — ConditionExpr → ScopePredicate
2. ``verify_sql_compilation`` — ScopePredicate → (sql, params)
3. ``verify_marker_resolution`` — (sql, params) → resolved SQL with concrete values

Each verifier returns a ``StageVerification`` result with pass/fail + diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StageVerification:
    """Result of verifying one stage invariant."""

    stage: str
    passed: bool
    predicate_type: str = ""
    expected: str = ""
    actual: str = ""
    error: str | None = None


@dataclass
class InvariantResult:
    """Aggregate result of all stage invariant checks for one scope rule."""

    entity: str
    persona: str
    stages: list[StageVerification] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(s.passed for s in self.stages)


def verify_predicate_build(
    condition: Any,
    entity_name: str,
    fk_graph: Any,
    expected_kind: str | None = None,
) -> StageVerification:
    """Verify that build_scope_predicate produces the expected predicate type.

    Args:
        condition: A ConditionExpr (or None for tautology).
        entity_name: The entity this scope belongs to.
        fk_graph: The FK graph for path resolution.
        expected_kind: Expected predicate ``kind`` value (e.g. "user_attr_check").
            If None, only checks that conversion succeeds without error.

    Returns:
        StageVerification with pass/fail.
    """
    try:
        from dazzle.core.ir.predicate_builder import build_scope_predicate

        predicate = build_scope_predicate(condition, entity_name, fk_graph)
        actual_kind = getattr(predicate, "kind", "unknown")

        if expected_kind is not None and actual_kind != expected_kind:
            return StageVerification(
                stage="predicate_build",
                passed=False,
                predicate_type=actual_kind,
                expected=expected_kind,
                actual=actual_kind,
                error=f"Expected predicate kind '{expected_kind}', got '{actual_kind}'",
            )

        return StageVerification(
            stage="predicate_build",
            passed=True,
            predicate_type=actual_kind,
            expected=expected_kind or actual_kind,
            actual=actual_kind,
        )
    except Exception as exc:
        return StageVerification(
            stage="predicate_build",
            passed=False,
            error=str(exc),
        )


def verify_sql_compilation(
    predicate: Any,
    entity_name: str,
    fk_graph: Any,
    expected_sql_contains: str | None = None,
) -> StageVerification:
    """Verify that compile_predicate produces expected SQL from a ScopePredicate.

    Args:
        predicate: A ScopePredicate tree.
        entity_name: The root entity being filtered.
        fk_graph: The FK graph for path resolution.
        expected_sql_contains: A substring the SQL must contain (e.g. ``"WHERE"``,
            ``"= %s"``). If None, only checks that compilation succeeds.

    Returns:
        StageVerification with pass/fail.
    """
    try:
        from dazzle_back.runtime.predicate_compiler import compile_predicate

        sql, params = compile_predicate(predicate, entity_name, fk_graph)

        predicate_type = getattr(predicate, "kind", "unknown")

        if expected_sql_contains is not None and expected_sql_contains not in sql:
            return StageVerification(
                stage="sql_compilation",
                passed=False,
                predicate_type=predicate_type,
                expected=expected_sql_contains,
                actual=sql,
                error=f"SQL does not contain '{expected_sql_contains}': {sql}",
            )

        return StageVerification(
            stage="sql_compilation",
            passed=True,
            predicate_type=predicate_type,
            expected=expected_sql_contains or "",
            actual=sql,
        )
    except Exception as exc:
        return StageVerification(
            stage="sql_compilation",
            passed=False,
            error=str(exc),
        )


def verify_marker_resolution(
    params: list[Any],
    user_context: dict[str, Any],
    expected_resolved: list[Any] | None = None,
) -> StageVerification:
    """Verify that UserAttrRef/CurrentUserRef markers resolve to expected values.

    Args:
        params: Parameter list from compile_predicate(), may contain marker objects.
        user_context: Dict with user attributes (e.g. ``{"id": "user-uuid", "school_id": "s1"}``).
        expected_resolved: Expected resolved parameter values. If None, only checks
            that resolution succeeds without raising.

    Returns:
        StageVerification with pass/fail.
    """
    try:
        resolved = _resolve_markers(params, user_context)

        if expected_resolved is not None and resolved != expected_resolved:
            return StageVerification(
                stage="marker_resolution",
                passed=False,
                expected=str(expected_resolved),
                actual=str(resolved),
                error=f"Resolved params {resolved} != expected {expected_resolved}",
            )

        return StageVerification(
            stage="marker_resolution",
            passed=True,
            expected=str(expected_resolved or resolved),
            actual=str(resolved),
        )
    except Exception as exc:
        return StageVerification(
            stage="marker_resolution",
            passed=False,
            error=str(exc),
        )


def verify_round_trip(
    condition: Any,
    entity_name: str,
    fk_graph: Any,
    expected_predicate_kind: str | None = None,
    expected_sql_contains: str | None = None,
    user_context: dict[str, Any] | None = None,
    expected_resolved_params: list[Any] | None = None,
) -> InvariantResult:
    """Run all three stage verifications as a round-trip check.

    This is the main entry point for conformance testing. It builds the
    predicate, compiles to SQL, and optionally resolves markers.

    Returns:
        InvariantResult with all stage results.
    """
    result = InvariantResult(entity=entity_name, persona="")
    from dazzle.core.ir.predicate_builder import build_scope_predicate

    # Stage 1: ConditionExpr → ScopePredicate
    stage1 = verify_predicate_build(
        condition, entity_name, fk_graph, expected_kind=expected_predicate_kind
    )
    result.stages.append(stage1)

    if not stage1.passed:
        return result

    # Build the predicate for stages 2 and 3
    predicate = build_scope_predicate(condition, entity_name, fk_graph)

    # Stage 2: ScopePredicate → SQL
    stage2 = verify_sql_compilation(
        predicate, entity_name, fk_graph, expected_sql_contains=expected_sql_contains
    )
    result.stages.append(stage2)

    if not stage2.passed:
        return result

    # Stage 3: Marker resolution (optional)
    if user_context is not None:
        from dazzle_back.runtime.predicate_compiler import compile_predicate

        _sql, params = compile_predicate(predicate, entity_name, fk_graph)
        stage3 = verify_marker_resolution(
            params, user_context, expected_resolved=expected_resolved_params
        )
        result.stages.append(stage3)

    return result


def _resolve_markers(params: list[Any], user_context: dict[str, Any]) -> list[Any]:
    """Resolve UserAttrRef and CurrentUserRef markers to concrete values.

    Args:
        params: Parameter list potentially containing marker objects.
        user_context: Dict with ``"id"`` and any user attributes.

    Returns:
        New list with markers replaced by concrete values.
    """
    from dazzle_back.runtime.predicate_compiler import CurrentUserRef, UserAttrRef

    resolved: list[Any] = []
    for p in params:
        if isinstance(p, UserAttrRef):
            value = user_context.get(p.attr_name)
            if value is None:
                raise ValueError(
                    f"User context missing attribute '{p.attr_name}' "
                    f"(available: {list(user_context.keys())})"
                )
            resolved.append(value)
        elif isinstance(p, CurrentUserRef):
            user_id = user_context.get("id")
            if user_id is None:
                raise ValueError("User context missing 'id'")
            resolved.append(user_id)
        else:
            resolved.append(p)
    return resolved
