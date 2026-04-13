"""Progress evaluator — classifies lifecycle transitions as motion vs work.

Consumes lifecycle declarations plus ledger RowChanges and emits
ProgressRecords. A transition is "progress" iff it advances ``order``
AND the evidence predicate holds.

See ``docs/adr/ADR-0020-lifecycle-declarations.md`` for the grammar this
module evaluates.
"""

from __future__ import annotations

from typing import Any

from dazzle.core.ir.lifecycle import LifecycleSpec
from dazzle.fitness.models import (
    FitnessDiff,
    ProgressRecord,
    RowChange,
)


def evaluate_progress(
    lifecycle: LifecycleSpec,
    diff: FitnessDiff,
    entity_state: dict[str, dict[str, Any]],
    entity_name: str,
) -> list[ProgressRecord]:
    """Classify each status change in ``diff`` as progress or motion.

    Args:
        lifecycle: The lifecycle declaration for this entity type.
        diff: The ledger diff for the run.
        entity_state: Map of row_id -> current row dict (post-run state).
            Used to evaluate evidence predicates.
        entity_name: Name of the entity whose lifecycle this is (matched
            case-insensitively against ``RowChange.table``). LifecycleSpec
            in the IR is attached to an EntitySpec rather than carrying the
            entity name itself, so callers pass it explicitly.

    Returns:
        One ProgressRecord per row that had a status change.
    """
    order_map = {s.name: s.order for s in lifecycle.states}
    transition_map = {(t.from_state, t.to_state): t for t in lifecycle.transitions}
    status_col = lifecycle.status_field

    # Group row changes by row_id
    by_row: dict[str, list[RowChange]] = {}
    for rc in diff.updated:
        if rc.table.lower() != entity_name.lower():
            continue
        if status_col not in rc.field_deltas:
            continue
        by_row.setdefault(rc.row_id, []).append(rc)

    records: list[ProgressRecord] = []
    for row_id, changes in by_row.items():
        transitions_observed: list[tuple[str, str]] = []
        evidence_satisfied: list[bool] = []
        current_row = entity_state.get(row_id, {})

        for rc in changes:
            before, after = rc.field_deltas[status_col]
            transitions_observed.append((str(before), str(after)))

            transition = transition_map.get((str(before), str(after)))
            if transition is None:
                evidence_satisfied.append(False)
                continue

            # Transitions with no evidence predicate are always valid
            # (motion counts as work). See ADR-0020.
            if transition.evidence is None:
                evidence_holds = True
            else:
                evidence_holds = _evaluate_evidence(transition.evidence, current_row)
            is_forward = order_map.get(str(after), -1) > order_map.get(str(before), -1)
            evidence_satisfied.append(evidence_holds and is_forward)

        was_progress = any(evidence_satisfied)
        ended_at = transitions_observed[-1][1] if transitions_observed else "unknown"

        records.append(
            ProgressRecord(
                entity=entity_name,
                row_id=row_id,
                transitions_observed=transitions_observed,
                evidence_satisfied=evidence_satisfied,
                ended_at_state=ended_at,
                was_progress=was_progress,
            )
        )
    return records


def _evaluate_evidence(expression: str, row: dict[str, Any]) -> bool:
    """Tiny evaluator for v1 evidence predicates.

    Supported forms (matches the ADR-0020 grammar):
      - ``true``
      - ``false``
      - ``<field> != null``
      - ``<field> = null``
      - ``<field> != ""``
      - ``<field> = ""``
      - ``<expr> AND <expr>``
      - ``<expr> OR <expr>``

    Richer predicate support is deferred to v1.1 when the core predicate
    algebra is linked in directly.
    """
    expr = expression.strip()
    if expr == "true":
        return True
    if expr == "false":
        return False

    if " AND " in expr:
        parts = [p.strip() for p in expr.split(" AND ")]
        return all(_evaluate_evidence(p, row) for p in parts)
    if " OR " in expr:
        parts = [p.strip() for p in expr.split(" OR ")]
        return any(_evaluate_evidence(p, row) for p in parts)

    # <field> <op> <literal>
    for op, fn in (
        ("!= null", lambda v: v is not None),
        ("= null", lambda v: v is None),
        ('!= ""', lambda v: v is not None and v != ""),
        ('= ""', lambda v: v == ""),
    ):
        if op in expr:
            field = expr.split(op)[0].strip()
            return fn(row.get(field))

    # Unknown form - treat as unsatisfied; v1.1 will fail-loud here.
    return False
