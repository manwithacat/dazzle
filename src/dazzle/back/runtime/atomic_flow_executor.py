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

Per-step scope is enforced when ``auth_context`` + ``access_specs`` are supplied
(#1313, ADR-0029): each ``create`` routes through ``scope: create:`` (#1124/#1311)
and each ``update`` through ``scope: update:`` source + destination (#1312), via
an **in-transaction probe**, with scope keys derived from the principal.
``permit: execute:`` (the role gate) is enforced at the route. Still pending:
the in-transaction audit fact (ADR-0029 invariant 5), the analysis-IR projection
(matrix/conformance/specs visibility), and per-entity ``state_machine`` initial
transitions.
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
    audit_sink: list[dict[str, str]] | None = None,
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
        audit_sink: if provided, the executor appends one
            ``{"entity", "operation", "entity_id"}`` dict per *committed* step
            (#1313, ADR-0029 invariant 5). The caller logs them after the flow
            commits — a denied/rolled-back flow leaves the sink unchanged for
            its denied step (nothing happened ⇒ nothing to record).

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
                _execute_update_step(
                    step,
                    inputs,
                    above_ids,
                    conn,
                    cursor,
                    placeholder,
                    enforce=_enforce,
                    auth_context=auth_context,
                    access_specs=access_specs,
                    fk_graph=fk_graph,
                    probe=probe,
                    audit_sink=audit_sink,
                )
                continue
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
            if audit_sink is not None:
                audit_sink.append(
                    {"entity": step.entity, "operation": "create", "entity_id": str(row_id)}
                )
    return above_ids


def _resolve_value(
    value: ir.FlowFieldValue,
    inputs: dict[str, Any],
    above_ids: dict[str, UUID],
) -> Any:
    """Resolve one flow value (literal / input.<name> / above.<Entity>.id).

    Raises KeyError on an unresolvable input/above reference (a validator gap).
    """
    if value.kind == ir.FlowFieldValueKind.LITERAL:
        return value.literal
    if value.kind == ir.FlowFieldValueKind.INPUT_REF:
        if value.input_name not in inputs:
            raise KeyError(value.input_name or "")
        return inputs[value.input_name]
    # ABOVE_REF — only .id is supported (validator enforces).
    if value.above_entity not in above_ids:
        raise KeyError(value.above_entity or "")
    return above_ids[value.above_entity]


def _resolve_assignments(
    assignments: dict[str, ir.FlowFieldValue],
    inputs: dict[str, Any],
    above_ids: dict[str, UUID],
) -> dict[str, Any]:
    """Resolve a step's field assignments to a flat dict of column → value."""
    return {
        field_name: _resolve_value(value, inputs, above_ids)
        for field_name, value in assignments.items()
    }


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
    return {"id": row_id, **_resolve_assignments(create.assignments, inputs, above_ids)}


def _read_row_in_txn(conn: Any, entity: str, row_id: Any) -> dict[str, Any] | None:
    """Read a row by id on the flow's connection (in-transaction).

    Returns the row as a dict (the runtime connection uses a dict row factory),
    or None if absent. Used to fetch an update step's *source* row for scope
    enforcement + the would-be-final merge.
    """
    cur = conn.cursor()
    sql = f"SELECT * FROM {quote_identifier(entity)} WHERE {quote_identifier('id')} = %s"
    cur.execute(sql, [row_id])  # nosemgrep — entity identifier is a DSL constant; id is a param
    row = cur.fetchone()
    return dict(row) if row is not None else None


def _execute_update_step(
    step: ir.FlowUpdate,
    inputs: dict[str, Any],
    above_ids: dict[str, UUID],
    conn: Any,
    cursor: Any,
    placeholder: str,
    *,
    enforce: bool,
    auth_context: Any,
    access_specs: dict[str, Any] | None,
    fk_graph: Any,
    probe: Callable[[str, list[Any]], bool] | None,
    audit_sink: list[dict[str, str]] | None = None,
) -> None:
    """Execute one ``update`` step (#1313): resolve the target row, enforce
    ``scope: update:`` (source + destination) in-transaction, then UPDATE.

    "End-dating" a row is just an update that sets the entity's temporal end
    column (the single-`update`-kind grammar). Scope denial raises
    HTTPException(404) → the whole flow rolls back (fail-closed, IDOR-shaped).
    """
    try:
        target_id = _resolve_value(step.target, inputs, above_ids)
        new_values = _resolve_assignments(step.assignments, inputs, above_ids)
    except KeyError as exc:
        raise AtomicFlowError(
            step.entity, f"unresolved reference {exc!s} (validator gap?)"
        ) from exc

    existing = _read_row_in_txn(conn, step.entity, target_id)
    if existing is None:
        if enforce:
            # IDOR-shaped: when scope is enforced, a missing target must be
            # indistinguishable from a scope-denied one (both 404), matching the
            # CRUD update contract — otherwise a 400-vs-404 split would leak
            # whether a foreign id exists. The flow rolls back.
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not found")
        raise AtomicFlowError(step.entity, f"update target id={target_id!r} not found")

    if enforce:
        _enforce_update_step_scope(
            entity=step.entity,
            existing=existing,
            new_values=new_values,
            auth_context=auth_context,
            access_specs=access_specs,
            fk_graph=fk_graph,
            probe=probe,
        )

    if not new_values:
        return  # nothing to set (degenerate update)
    set_clause = ", ".join(f"{quote_identifier(k)} = {placeholder}" for k in new_values)
    table = quote_identifier(step.entity)
    sql = f"UPDATE {table} SET {set_clause} WHERE {quote_identifier('id')} = {placeholder}"
    try:
        cursor.execute(sql, [*new_values.values(), target_id])  # nosemgrep
    except Exception as exc:
        raise AtomicFlowError(step.entity, str(exc)) from exc
    if audit_sink is not None:
        audit_sink.append(
            {"entity": step.entity, "operation": "update", "entity_id": str(target_id)}
        )


def _enforce_update_step_scope(
    *,
    entity: str,
    existing: dict[str, Any],
    new_values: dict[str, Any],
    auth_context: Any,
    access_specs: dict[str, Any] | None,
    fk_graph: Any,
    probe: Callable[[str, list[Any]], bool] | None,
) -> None:
    """Enforce a ``scope: update:`` step (source + destination) in-transaction.

    Reuses ``route_generator._enforce_update_scope`` with ``also_check_source=True``
    (the executor has no route pre-read to validate the source row) and the
    flow's in-transaction probe. UUID values are normalised to str for
    simple-leaf comparisons (FK-path/EXISTS go through the probe). Raises
    HTTPException(404) on denial; the caller's transaction rolls back.
    """
    spec = access_specs.get(entity) if access_specs else None
    if spec is None:
        return
    from dazzle.back.runtime.route_generator import _enforce_update_scope

    user = getattr(auth_context, "user", None)
    user_id = str(user.id) if user is not None and getattr(user, "id", None) is not None else None
    user_roles = list(getattr(auth_context, "roles", []) or [])
    norm_existing = {k: (str(v) if isinstance(v, UUID) else v) for k, v in existing.items()}
    norm_new = {k: (str(v) if isinstance(v, UUID) else v) for k, v in new_values.items()}
    _enforce_update_scope(
        cedar_access_spec=spec,
        existing=norm_existing,
        new_values=norm_new,
        user_id=user_id,
        user_roles=user_roles,
        entity_name=entity,
        auth_context=auth_context,
        fk_graph=fk_graph,
        probe=probe,
        also_check_source=True,
    )
