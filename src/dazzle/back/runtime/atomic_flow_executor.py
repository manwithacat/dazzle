"""Atomic-flow executor (#1228 Phase 3c slice 3c.ii).

Executes a parsed ``AtomicFlowSpec`` against a live database. All
declared ``create`` blocks run inside a single transaction on a
shared connection — either every create succeeds and the transaction
commits, or any failure rolls everything back.

Reference resolution:

- ``input.<name>`` → looks up ``inputs[name]``
- ``above.<Entity>.id`` → uses the UUID generated for the earlier
  create of that entity within this flow

Public surface:

- :func:`execute_atomic_flow` — the entry point
- :class:`AtomicFlowError` — raised when any create fails; carries
  ``failed_at`` (the entity name that errored) and the original
  exception as ``__cause__``

Not in scope for this slice:

- Pydantic input-schema generation from ``flow.inputs``
- Route registration (``POST /api/atomic/<name>``)
- ``permit:`` enforcement (caller's responsibility for now)
- Per-entity ``state_machine`` initial-state transitions

Those land in 3c.ii.b / 3c.iii.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from dazzle.back.runtime.query_builder import quote_identifier
from dazzle.core import ir


class AtomicFlowError(Exception):
    """Raised when an atomic-flow execution fails partway.

    The transaction has already been rolled back by the time this
    exception is raised. ``failed_at`` names the entity whose create
    triggered the failure; ``__cause__`` carries the original DB or
    constraint error.
    """

    def __init__(self, failed_at: str, message: str) -> None:
        self.failed_at = failed_at
        super().__init__(f"atomic flow failed at create {failed_at}: {message}")


def execute_atomic_flow(
    flow: ir.AtomicFlowSpec,
    inputs: dict[str, Any],
    db_manager: Any,
) -> dict[str, UUID]:
    """Execute one atomic flow.

    Args:
        flow: The parsed ``AtomicFlowSpec`` (validator-clean).
        inputs: User-supplied values keyed by input name. Caller is
            responsible for validating these against ``flow.inputs``
            before calling — the executor does no schema coercion.
        db_manager: Provides ``.placeholder`` and ``.connection()``
            (the connection's __exit__ commits unless rollback was
            called inside).

    Returns:
        Map of ``EntityName → generated UUID``.

    Raises:
        AtomicFlowError: any create failed; transaction already
            rolled back.
    """
    above_ids: dict[str, UUID] = {}
    placeholder = db_manager.placeholder

    # Open one connection for the whole flow. The pool's exit-handler
    # commits on clean exit and rolls back on exception, so re-raising
    # any AtomicFlowError from inside the with-block lets the rollback
    # happen for free.
    with db_manager.connection() as conn:
        cursor = conn.cursor()
        for step in flow.steps:
            if isinstance(step, ir.FlowUpdate):
                # Slice 1a (ADR-0029): `update` steps are parsed + validated
                # but not yet executed. The runtime (in-transaction per-step
                # scope enforcement + audit) lands in slice 1b — see ADR-0029
                # Implementation status. Raising inside the with-block rolls
                # the transaction back; the route maps this to 501.
                raise NotImplementedError(
                    f"atomic `update` step (target entity {step.entity!r}) is "
                    "parsed and validated but not yet executed — the runtime "
                    "lands in #1313 slice 1b (ADR-0029)."
                )
            # FlowCreate
            row_id = uuid4()
            try:
                data = _build_row_data(step, inputs, above_ids, row_id)
            except KeyError as exc:
                raise AtomicFlowError(
                    step.entity,
                    f"unresolved reference {exc!s} (validator gap?)",
                ) from exc
            columns = ", ".join(quote_identifier(k) for k in data.keys())
            placeholders = ", ".join(placeholder for _ in data)
            table = quote_identifier(step.entity)
            sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
            try:
                cursor.execute(sql, list(data.values()))  # nosemgrep
            except Exception as exc:
                raise AtomicFlowError(step.entity, str(exc)) from exc
            above_ids[step.entity] = row_id
    return above_ids


def _build_row_data(
    create: ir.FlowCreate,
    inputs: dict[str, Any],
    above_ids: dict[str, UUID],
    row_id: UUID,
) -> dict[str, Any]:
    """Resolve a create's assignments into a flat INSERT-ready dict.

    The framework always supplies ``id`` (the generated UUID) so the
    flow author doesn't need to declare it as an assignment.
    """
    data: dict[str, Any] = {"id": row_id}
    for field_name, value in create.assignments.items():
        if value.kind == ir.FlowFieldValueKind.LITERAL:
            data[field_name] = value.literal
        elif value.kind == ir.FlowFieldValueKind.INPUT_REF:
            if value.input_name not in inputs:
                raise KeyError(value.input_name or "")
            data[field_name] = inputs[value.input_name]
        elif value.kind == ir.FlowFieldValueKind.ABOVE_REF:
            if value.above_entity not in above_ids:
                raise KeyError(value.above_entity or "")
            # Only .id is supported in this slice (validator enforces).
            data[field_name] = above_ids[value.above_entity]
    return data
