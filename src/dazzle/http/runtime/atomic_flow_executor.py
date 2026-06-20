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

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from dazzle.core import ir
from dazzle.http.runtime.query_builder import quote_identifier

logger = logging.getLogger(__name__)

# Dedicated strict-audit side-table (#1317, ADR-0029 invariant 5). Written on the
# flow's OWN connection inside the transaction (so the audit row commits/rolls
# back atomically with the mutation), distinct from the async, hash-chained
# `_dazzle_audit_log`. Deliberately NOT hash-chained — a per-flow in-transaction
# insert into the chained log would race/fork the single async drainer.
_ATOMIC_AUDIT_TABLE = "_dazzle_atomic_audit"


def ensure_atomic_audit_table(conn: Any) -> None:
    """Create the strict-audit side-table if absent (idempotent).

    Called **once at server boot** when an app declares any ``audit: strict``
    flow (``server.py``, atomic-router wiring), on its own connection — NOT per
    request: a per-request ``CREATE TABLE IF NOT EXISTS`` inside the flow
    transaction would let two concurrent first-creations race into a ``pg_type``
    unique violation and roll back a legitimate mutation. The in-transaction
    writer (`_write_strict_atomic_audit`) then assumes the table exists.
    ``CREATE TABLE IF NOT EXISTS`` mirrors how ``_dazzle_audit_log`` self-inits
    (``audit_log.AuditLogger._init_db``) — strict atomic audit needs no Alembic
    migration. Table/index names are fixed framework literals (no interpolation).
    """
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS _dazzle_atomic_audit (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            flow_name TEXT NOT NULL,
            user_id TEXT,
            user_email TEXT,
            user_roles TEXT,
            operation TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            entity_id TEXT,
            decision TEXT NOT NULL,
            matched_policy TEXT
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_atomic_audit_flow "
        "ON _dazzle_atomic_audit(flow_name, timestamp)"
    )


def query_atomic_audit(
    conn: Any, *, flow: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Read strict atomic-audit rows (#1317), newest first.

    The read path for the ``_dazzle_atomic_audit`` side-table. ``conn`` should use
    a dict row factory (``psycopg.rows.dict_row``). Optionally filter by
    ``flow`` name. Raises if the table doesn't exist (no strict flow has run);
    callers that want a graceful "no rows yet" should catch that.
    """
    cur = conn.cursor()
    if flow:
        cur.execute(
            "SELECT * FROM _dazzle_atomic_audit WHERE flow_name = %s "
            "ORDER BY timestamp DESC LIMIT %s",
            [flow, limit],
        )
    else:
        cur.execute(
            "SELECT * FROM _dazzle_atomic_audit ORDER BY timestamp DESC LIMIT %s",
            [limit],
        )
    return [dict(r) for r in cur.fetchall()]


def _write_strict_atomic_audit(
    cursor: Any,
    flow_name: str,
    auth_context: Any,
    committed_steps: list[dict[str, str]],
) -> None:
    """Write one ``allow`` audit row per committed step to the side-table.

    Runs on the flow's ``cursor`` *inside the flow transaction* (#1317): the rows
    commit with the mutation, and a denied/rolled-back flow writes nothing (the
    inserts roll back with everything else). ``matched_policy`` is ``atomic:<flow>``,
    mirroring the async path's correlation tag.
    """
    user = getattr(auth_context, "user", None)
    user_id = str(user.id) if user is not None and getattr(user, "id", None) is not None else None
    user_email = getattr(user, "email", None) if user is not None else None
    user_roles = json.dumps(list(getattr(auth_context, "roles", []) or []))
    ts = datetime.now(UTC).isoformat()
    matched_policy = f"atomic:{flow_name}"
    sql = (
        "INSERT INTO _dazzle_atomic_audit "
        "(id, timestamp, flow_name, user_id, user_email, user_roles, operation, "
        "entity_name, entity_id, decision, matched_policy) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    for step in committed_steps:
        cursor.execute(
            sql,
            [
                str(uuid4()),
                ts,
                flow_name,
                user_id,
                user_email,
                user_roles,
                step["operation"],
                step["entity"],
                step.get("entity_id"),
                "allow",
                matched_policy,
            ],
        )


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


def _collect_pathcheck_parent_locks(
    *,
    entity: str,
    payload: dict[str, Any],
    access_specs: dict[str, Any] | None,
    fk_graph: Any,
    operations: tuple[str, ...],
) -> dict[str, set[str]]:
    """Collect ``scope-parent table → payload-referenced pk`` for ``entity``'s
    depth>1 FK-path ``scope:`` predicates (#1316, ADR-0029 invariant 4).

    The scope probe reads the directly-referenced parent row to decide the
    create/update; between that read and the flow's commit a concurrent
    ``UPDATE`` could move the parent out of the principal's scope (a TOCTOU).
    The caller share-locks the rows collected here *before* the probe so the
    parent is pinned for the rest of the transaction.

    Only the **root** FK-target row (the one the payload directly names, via the
    same ``PayloadFieldRef`` the probe binds) is collected — this fully closes
    the race for **depth-2** FK-path scopes (the common case, incl. the
    ``scope_runtime`` fixtures). For depth>2 paths only the root hop is locked;
    deeper intermediate hops, and ``ExistsCheck`` / junction-membership scopes,
    remain a documented, deferred narrowing (the share-lock can't express them).
    Reuses ``_path_check_subquery`` (root table + FK field) and ``_payload_value``
    (the same payload-key resolution the probe uses) so the lock target can't
    drift from what the probe checks.
    """
    spec = access_specs.get(entity) if access_specs else None
    if spec is None or fk_graph is None:
        return {}
    scopes = getattr(spec, "scopes", None) or []
    if not scopes:
        return {}

    # Cross-module private imports: the atomic executor is already tightly
    # coupled to the CRUD scope machinery (it reuses `_enforce_create_scope`),
    # so reusing the compiler's path decomposition + the eval's payload-key
    # resolver keeps the lock target identical to what the probe binds.
    from dazzle.core.ir.predicates import BoolComposite, PathCheck
    from dazzle.http.runtime.predicate_compiler import _path_check_subquery
    from dazzle.http.runtime.scope_create_eval import _payload_value
    from dazzle.http.runtime.tenant_isolation import get_current_tenant_schema

    schema = get_current_tenant_schema()
    locks: dict[str, set[str]] = {}

    def _walk(p: Any) -> None:
        if isinstance(p, PathCheck) and len(p.path) >= 2:
            try:
                root_fk_field, root_target_table, _where, _params = _path_check_subquery(
                    p, entity, fk_graph, schema=schema
                )
            except Exception:
                # A malformed path can't be locked — the probe will fail-close
                # it anyway; don't let lock-collection break the flow.
                logger.debug(
                    "scope-parent lock: skipping unresolvable PathCheck %r on %s",
                    getattr(p, "path", None),
                    entity,
                    exc_info=True,
                )
                return
            value = _payload_value(payload, root_fk_field)
            if value is not None:
                locks.setdefault(root_target_table, set()).add(str(value))
        elif isinstance(p, BoolComposite):
            for child in p.children:
                _walk(child)

    for rule in scopes:
        rule_op = getattr(rule, "operation", None)
        if rule_op is None:
            continue
        rule_op_val = rule_op.value if hasattr(rule_op, "value") else str(rule_op)
        if rule_op_val not in operations:
            continue
        predicate = getattr(rule, "predicate", None)
        if predicate is not None:
            _walk(predicate)
    return locks


def _acquire_scope_parent_share_locks(conn: Any, entity: str, locks: dict[str, set[str]]) -> None:
    """``SELECT … FOR SHARE`` the collected scope-parent rows on the flow's
    connection, in a deterministic ``(table, pk)`` order (#1316).

    A ``FOR SHARE`` row lock blocks a concurrent ``UPDATE`` / ``DELETE`` of that
    parent until this flow commits or rolls back, so the scope check the probe
    is about to run stays true through commit. Tables (and pks within a table)
    are locked in sorted order so two concurrent flows acquire overlapping locks
    in the same global order and cannot deadlock. The locks release with the
    transaction. A lock failure denies fail-closed (``AtomicFlowError`` → the
    whole flow rolls back) rather than 500-ing.
    """
    if not locks:
        return
    try:
        # Deterministic global order: tables sorted, then pks sorted within each
        # table, locked one row at a time. Using the single-value ``"id" = %s``
        # shape (the proven #1311 probe shape) avoids the ``uuid = text[]``
        # operator mismatch a bound ``ANY(%s)`` list of pk strings would hit.
        cur = conn.cursor()
        for table in sorted(locks):
            for pk in sorted(locks[table]):
                # `table` is already schema-qualified + quote_identifier'd by
                # `_path_check_subquery`; `pk` is bound, never interpolated.
                sql = f'SELECT "id" FROM {table} WHERE "id" = %s FOR SHARE'
                cur.execute(sql, [pk])  # nosemgrep — identifier compiler-built; pk bound
    except Exception as exc:
        raise AtomicFlowError(entity, f"scope-parent lock failed: {exc}") from exc


def _enforce_create_step_scope(
    *,
    entity: str,
    data: dict[str, Any],
    auth_context: Any,
    access_specs: dict[str, Any] | None,
    fk_graph: Any,
    probe: Callable[[str, list[Any]], bool] | None,
    conn: Any = None,
) -> None:
    """Route one create step through ``scope: create:`` (#1313 slice 1b).

    Reuses the CRUD enforcer (``route_generator._enforce_create_scope``) — same
    rule-matching + #1311 probe machinery — but with the flow's in-transaction
    probe. Scope keys are derived from ``auth_context`` (never the payload).
    Raises ``HTTPException(403)`` on denial; the caller's transaction rolls back.
    Entities with no access spec are unguarded (matches CRUD behaviour).

    Before the scope probe, the directly-referenced FK-path scope parent is
    share-locked on ``conn`` (#1316) so it can't move out of scope between the
    check and commit.
    """
    spec = access_specs.get(entity) if access_specs else None
    if spec is None:
        return
    from dazzle.http.runtime.scope_filters import _enforce_create_scope

    user = getattr(auth_context, "user", None)
    user_id = str(user.id) if user is not None and getattr(user, "id", None) is not None else None
    user_roles = list(getattr(auth_context, "roles", []) or [])
    # Normalise UUID payload values to str so simple-leaf (`ColumnCheck` /
    # `UserAttrCheck`) comparisons match the create handler's
    # `model_dump(mode="json")` shape. FK-path / EXISTS leaves go through the
    # probe (SQL) and are unaffected by this.
    payload = {k: (str(v) if isinstance(v, UUID) else v) for k, v in data.items()}
    # #1316 — TOCTOU hardening: pin the FK-path create-scope parent under
    # FOR SHARE before the probe reads it. Only when in-transaction enforcement
    # is active (probe + conn present).
    if probe is not None and conn is not None:
        _acquire_scope_parent_share_locks(
            conn,
            entity,
            _collect_pathcheck_parent_locks(
                entity=entity,
                payload=payload,
                access_specs=access_specs,
                fk_graph=fk_graph,
                operations=("create",),
            ),
        )
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
    # Open one connection for the whole flow. The pool's exit-handler commits on
    # clean exit and rolls back on exception, so re-raising any AtomicFlowError
    # (or a scope HTTPException) from inside the with-block rolls back for free.
    with db_manager.connection() as conn:
        return execute_atomic_flow_on_conn(
            flow,
            inputs,
            conn,
            db_manager.placeholder,
            auth_context=auth_context,
            access_specs=access_specs,
            fk_graph=fk_graph,
            audit_sink=audit_sink,
        )


def execute_atomic_flow_on_conn(
    flow: ir.AtomicFlowSpec,
    inputs: dict[str, Any],
    conn: Any,
    placeholder: str,
    *,
    auth_context: Any = None,
    access_specs: dict[str, Any] | None = None,
    fk_graph: Any = None,
    audit_sink: list[dict[str, str]] | None = None,
) -> dict[str, UUID]:
    """Execute an atomic flow on an externally-provided connection (#1319, ADR-0032).

    Identical semantics to :func:`execute_atomic_flow`, but the CALLER owns the
    connection and its transaction boundary (commit/rollback). This lets a
    lifecycle transition (ADR-0032 Slice B) run the flow in the SAME transaction
    as its status write — both commit or both roll back. Any exception raised here
    propagates to the caller, whose ``with``/transaction context rolls back.
    """
    above_ids: dict[str, UUID] = {}
    _enforce = access_specs is not None and auth_context is not None
    # #1317 — `audit: strict` writes the audit side-table in-transaction. It needs
    # the per-step intents regardless of whether the (async) caller passed a sink,
    # so materialise one when strict and none was supplied. The strict write does
    # NOT require a principal — an unauthenticated flow (test/legacy wiring) still
    # records a row with null user fields. `_write_strict_atomic_audit` tolerates a
    # None `auth_context`.
    strict_audit = flow.audit_mode == ir.FlowAuditMode.STRICT
    if strict_audit and audit_sink is None:
        audit_sink = []

    # #1315 — run in FK-derived parent-before-child order for create-DAG flows;
    # `derived_step_order` is None for declared-order flows (updates / cyclic FKs).
    if flow.derived_step_order is not None:
        ordered_steps = [flow.steps[i] for i in flow.derived_step_order]
    else:
        ordered_steps = list(flow.steps)

    cursor = conn.cursor()
    probe = _make_in_txn_probe(conn) if _enforce else None
    for step in ordered_steps:
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
        # Per-step `scope: create:` enforcement (#1313 slice 1b). Routes the create
        # through the SAME guard a standalone create gets (#1124/#1311), but with an
        # in-transaction probe. Scope keys come from the principal, never the
        # payload. Denial raises HTTPException(403) → the whole flow rolls back
        # (fail-closed). Runs BEFORE the INSERT.
        if _enforce:
            _enforce_create_step_scope(
                entity=step.entity,
                data=data,
                auth_context=auth_context,
                access_specs=access_specs,
                fk_graph=fk_graph,
                probe=probe,
                conn=conn,
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

    # #1318 — flow-level aggregate invariants (ADR-0031). Enforced AFTER the step
    # loop and BEFORE the strict-audit write + commit, so a violation rolls back the
    # mutations AND any audit rows. Each invariant locks its anchor FOR UPDATE, runs
    # a scope-free aggregate over the touched set, and compares against the bound; a
    # violation raises AtomicFlowError → the whole flow rolls back (the route maps it
    # to HTTP 400). Fail-closed: any enforcement error also propagates and rolls back.
    if flow.invariants:
        from dazzle.http.runtime.atomic_flow_invariants import enforce_flow_invariants

        enforce_flow_invariants(conn, flow, inputs, fk_graph)

    # #1317 — strict audit: write one row per committed step to the side-table on
    # THIS connection, before commit. The audit rows commit atomically with the
    # mutation; any earlier deny/failure already raised and rolled the whole flow
    # back (this line is unreachable), so a rolled-back flow records nothing. The
    # side-table is created once at boot (see `server.py`, gated on any `audit:
    # strict` flow) — NOT per request.
    if strict_audit and audit_sink:
        _write_strict_atomic_audit(cursor, flow.name, auth_context, audit_sink)
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
            conn=conn,
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
    conn: Any = None,
) -> None:
    """Enforce a ``scope: update:`` step (source + destination) in-transaction.

    Reuses ``route_generator._enforce_update_scope`` with ``also_check_source=True``
    (the executor has no route pre-read to validate the source row) and the
    flow's in-transaction probe. UUID values are normalised to str for
    simple-leaf comparisons (FK-path/EXISTS go through the probe). Raises
    HTTPException(404) on denial; the caller's transaction rolls back.

    Before the scope probe, the would-be-destination FK-path scope parent (the
    parent the update repoints *into*) is share-locked on ``conn`` (#1316) so a
    concurrent move can't slip it out of scope between the check and commit.
    """
    spec = access_specs.get(entity) if access_specs else None
    if spec is None:
        return
    from dazzle.http.runtime.scope_filters import _enforce_update_scope

    user = getattr(auth_context, "user", None)
    user_id = str(user.id) if user is not None and getattr(user, "id", None) is not None else None
    user_roles = list(getattr(auth_context, "roles", []) or [])
    norm_existing = {k: (str(v) if isinstance(v, UUID) else v) for k, v in existing.items()}
    norm_new = {k: (str(v) if isinstance(v, UUID) else v) for k, v in new_values.items()}
    # #1316 — pin the destination FK-path scope parent under FOR SHARE before
    # the probe. Key the lock off the **would-be-final** row
    # (``{**existing, **new_values}``) — the SAME dict ``_enforce_update_scope``
    # binds its destination probe from — so the parent is pinned both when the
    # update *repoints* the scope FK and when it leaves the FK unchanged (a
    # scope-key column the partial update doesn't set keeps its existing value,
    # and the probe still authorizes against that unchanged parent). Source-row
    # pinning + depth>2 hops remain deferred (see `_collect_pathcheck_parent_locks`).
    if probe is not None and conn is not None:
        merged_payload = {**norm_existing, **norm_new}
        _acquire_scope_parent_share_locks(
            conn,
            entity,
            _collect_pathcheck_parent_locks(
                entity=entity,
                payload=merged_payload,
                access_specs=access_specs,
                fk_graph=fk_graph,
                operations=("update",),
            ),
        )
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
