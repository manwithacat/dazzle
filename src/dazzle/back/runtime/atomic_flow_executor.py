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

``scope: create:`` is enforced per step when ``auth_context`` + ``access_specs``
are supplied (#1313 slice 1b, ADR-0029): each create routes through the same
guard a standalone create gets (#1124/#1311), via an in-transaction probe, with
scope keys derived from the principal. ``permit: execute:`` (the role gate) is
enforced at the route. Still pending: ``update`` step execution + audit
(ADR-0029 invariant 5) + per-entity ``state_machine`` initial transitions.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from dazzle.back.runtime.query_builder import quote_identifier
from dazzle.core import ir

logger = logging.getLogger(__name__)


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


def _make_in_txn_probe(conn: Any) -> Callable[[str, list[Any]], bool]:
    """Build a create-scope probe bound to the flow's own connection (#1313).

    Unlike the CRUD path's ``build_create_scope_probe`` (which opens its **own**
    connection), this runs ``SELECT 1 WHERE <expr> LIMIT 1`` on a fresh cursor
    of the *flow's* connection — so FK-path / EXISTS create-scope is resolved
    **inside the flow's transaction** and sees rows created by earlier steps.
    """

    def _probe(sql: str, params: list[Any]) -> bool:
        # `sql` is compiler-built (quote_identifier identifiers + %s params); the
        # caller's values are bound, never interpolated. Same shape as the CRUD
        # probe `build_create_scope_probe`.
        probe_sql = f"SELECT 1 WHERE {sql} LIMIT 1"
        try:
            cur = conn.cursor()
            cur.execute(probe_sql, params)  # nosemgrep
            return cur.fetchone() is not None
        except Exception:
            # Fail closed, matching the CRUD probe (build_create_scope_probe):
            # a malformed/erroring probe denies (→ 403 → whole flow rolls back)
            # rather than 500-ing. The flow transaction is already aborted by
            # the error; the deny + rollback recovers it cleanly.
            logger.warning(
                "atomic create-scope probe failed — denying (fail-closed).", exc_info=True
            )
            return False

    return _probe


def _enforce_create_step_scope(
    *,
    entity: str,
    data: dict[str, Any],
    auth_context: Any,
    access_specs: dict[str, Any] | None,
    fk_graph: Any,
    probe: Callable[[str, list[Any]], bool] | None,
) -> None:
    """Route one create step through ``scope: create:`` (#1313 slice 1b).

    Reuses the CRUD enforcer (``route_generator._enforce_create_scope``) — same
    rule-matching + #1311 probe machinery — but with the flow's in-transaction
    probe. Scope keys are derived from ``auth_context`` (never the payload).
    Raises ``HTTPException(403)`` on denial; the caller's transaction rolls back.
    Entities with no access spec are unguarded (matches CRUD behaviour).
    """
    spec = access_specs.get(entity) if access_specs else None
    if spec is None:
        return
    from dazzle.back.runtime.route_generator import _enforce_create_scope

    user = getattr(auth_context, "user", None)
    user_id = str(user.id) if user is not None and getattr(user, "id", None) is not None else None
    user_roles = list(getattr(auth_context, "roles", []) or [])
    # Normalise UUID payload values to str so simple-leaf (`ColumnCheck` /
    # `UserAttrCheck`) comparisons match the create handler's
    # `model_dump(mode="json")` shape. FK-path / EXISTS leaves go through the
    # probe (SQL) and are unaffected by this.
    payload = {k: (str(v) if isinstance(v, UUID) else v) for k, v in data.items()}
    _enforce_create_scope(
        cedar_access_spec=spec,
        payload=payload,
        user_id=user_id,
        user_roles=user_roles,
        entity_name=entity,
        auth_context=auth_context,
        fk_graph=fk_graph,
        probe=probe,
    )


def execute_atomic_flow(
    flow: ir.AtomicFlowSpec,
    inputs: dict[str, Any],
    db_manager: Any,
    *,
    auth_context: Any = None,
    access_specs: dict[str, Any] | None = None,
    fk_graph: Any = None,
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
        auth_context: the authenticated principal (an ``AuthContext``).
            Required for ``scope: create:`` enforcement; scope keys are
            derived from it, never from the payload (ADR-0029 invariant 1).
        access_specs: ``{entity_name: EntityAccessSpec}`` for per-step
            scope enforcement. When provided (with ``auth_context``), each
            create step is routed through ``scope: create:`` exactly like a
            standalone guarded create (#1313 slice 1b, ADR-0029 invariant 2),
            using an in-transaction probe. When omitted (legacy/test wiring),
            steps run unguarded as before.
        fk_graph: FK graph for FK-path / EXISTS create-scope probe SQL.

    Returns:
        Map of ``EntityName → generated UUID``.

    Raises:
        AtomicFlowError: any create failed; transaction already rolled back.
        HTTPException(403): a step's ``scope: create:`` predicate denied the
            insert — the whole flow transaction is rolled back (fail-closed).
    """
    above_ids: dict[str, UUID] = {}
    placeholder = db_manager.placeholder
    _enforce = access_specs is not None and auth_context is not None

    # Open one connection for the whole flow. The pool's exit-handler
    # commits on clean exit and rolls back on exception, so re-raising
    # any AtomicFlowError (or a scope HTTPException) from inside the
    # with-block lets the rollback happen for free.
    with db_manager.connection() as conn:
        cursor = conn.cursor()
        probe = _make_in_txn_probe(conn) if _enforce else None
        for step in flow.steps:
            if isinstance(step, ir.FlowUpdate):
                # Slice 1a (ADR-0029): `update` steps are parsed + validated
                # but not yet executed. The runtime (in-transaction per-step
                # scope enforcement + audit) lands in a later slice — see
                # ADR-0029 Implementation status. Raising inside the with-block
                # rolls the transaction back; the route maps this to 501.
                raise NotImplementedError(
                    f"atomic `update` step (target entity {step.entity!r}) is "
                    "parsed and validated but not yet executed — the runtime "
                    "lands in #1313 (ADR-0029)."
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
            # Per-step `scope: create:` enforcement (#1313 slice 1b). Routes the
            # create through the SAME guard a standalone create gets (#1124/#1311),
            # but with an in-transaction probe. Scope keys come from the principal,
            # never the payload. Denial raises HTTPException(403) → the whole flow
            # rolls back (fail-closed). Runs BEFORE the INSERT.
            if _enforce:
                _enforce_create_step_scope(
                    entity=step.entity,
                    data=data,
                    auth_context=auth_context,
                    access_specs=access_specs,
                    fk_graph=fk_graph,
                    probe=probe,
                )
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
