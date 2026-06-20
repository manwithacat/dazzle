"""Flow-level aggregate invariant enforcement (#1318, ADR-0031).

A flow invariant asserts ``<agg_fn>(<entity>.<field> where <filter>) <op> <rhs>``
holds **at commit time**, else the whole atomic flow rolls back. This is the
runtime core (Tasks 6 + 7): the executor calls :func:`enforce_flow_invariants`
inside the flow transaction, AFTER the step loop and BEFORE the commit, so a
violated invariant rolls back every mutation (and the strict-audit rows too).

The enforcement is **fail-closed**: it locks the invariant's anchor row
``FOR UPDATE`` first (gating concurrent writers to the aggregate set), runs one
scope-free aggregate SQL query over the touched set, resolves the RHS bound, and
compares. A violation — or any error during enforcement — propagates an
:class:`AtomicFlowError` (or the underlying DB error) out of the ``with conn``
block, which rolls the transaction back. Nothing is swallowed.

The aggregate query is **deliberately scope-free**: it must see the *full* set of
rows for the anchor (the whole transaction's postings, the whole budget's
allocations) to decide whether the invariant holds — a scope-filtered count would
let a principal satisfy a global balance check against only the rows they can see.
The anchor ``FOR UPDATE`` lock + the per-step ``scope: create:`` enforcement that
already ran are what bound *what the principal may write*; the invariant bounds
*the aggregate over everything*.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from dazzle.core import ir
from dazzle.http.runtime.atomic_flow_executor import AtomicFlowError
from dazzle.http.runtime.query_builder import quote_identifier

logger = logging.getLogger(__name__)


def build_invariant_sql(
    agg_fn: ir.FlowAggregateFn,
    entity: str,
    field: str | None,
    where_terms: list[tuple[str, Any]],
) -> tuple[str, list[Any]]:
    """Build the scope-free aggregate query for one invariant (pure).

    Args:
        agg_fn: SUM or COUNT.
        entity: the aggregate's target entity (the table name).
        field: the summed column (required for SUM; ignored for COUNT).
        where_terms: ``(db_column, value)`` pairs — already FK-resolved by the
            caller — conjoined with ``AND``. An empty list emits no WHERE clause.

    Returns:
        ``(sql, params)``. For SUM, ``COALESCE(SUM(...), 0)`` so an empty set
        yields ``0`` (not NULL). Identifiers go through ``quote_identifier``;
        values are bound via ``%s`` placeholders, never interpolated.
    """
    if agg_fn == ir.FlowAggregateFn.SUM:
        if not field:
            raise ValueError("SUM invariant requires a field")
        select_expr = f"COALESCE(SUM({quote_identifier(field)}), 0)"
    else:  # COUNT
        select_expr = "COUNT(*)"

    sql = f"SELECT {select_expr} FROM {quote_identifier(entity)}"
    params: list[Any] = []
    if where_terms:
        clauses = " AND ".join(f"{quote_identifier(col)} = %s" for col, _ in where_terms)
        sql += f" WHERE {clauses}"
        params = [value for _, value in where_terms]
    return sql, params


def _first_value(row: Any) -> Any:
    """Read the first column from a fetched row, tuple- or dict-row agnostic.

    The atomic flow's connection uses psycopg's ``dict_row`` factory, so
    ``row[0]`` would ``KeyError`` on a single-column aggregate (the key is the
    column name, not ``0``). This reads the sole value regardless of row type.
    """
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _coerce_literal(value: str) -> Any:
    """Coerce a raw_filter literal string to int, then float, else keep str."""
    try:
        return int(value)
    except (ValueError, TypeError):
        pass
    try:
        return float(value)
    except (ValueError, TypeError):
        return value


def _to_decimal(value: Any) -> Decimal:
    """Coerce an aggregate / RHS value to Decimal for a numeric comparison.

    Fail-closed: a non-numeric value (which would make the comparison
    meaningless) raises rather than silently comparing wrong.
    """
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"non-numeric value in invariant comparison: {value!r}") from exc


_COMPARATORS: dict[ir.CompOp, Any] = {
    ir.CompOp.EQ: lambda a, b: a == b,
    ir.CompOp.NEQ: lambda a, b: a != b,
    ir.CompOp.LT: lambda a, b: a < b,
    ir.CompOp.LTE: lambda a, b: a <= b,
    ir.CompOp.GT: lambda a, b: a > b,
    ir.CompOp.GTE: lambda a, b: a >= b,
}


def _resolve_where_terms(
    inv: ir.FlowInvariant,
    inputs: dict[str, Any],
    fk_graph: Any,
) -> list[tuple[str, Any]]:
    """Resolve ``inv.raw_filter`` triples to ``(db_column, value)`` pairs.

    Each ``(column, kind, value)``: the DB column is the FK field name when
    ``column`` is an FK on ``inv.entity`` (resolved via ``fk_graph``), else
    ``column`` verbatim. The value is ``inputs[value]`` when ``kind == "input"``,
    else the literal ``value`` (numeric-coerced).
    """
    where_terms: list[tuple[str, Any]] = []
    for column, kind, value in inv.raw_filter:
        db_column = column
        if fk_graph is not None:
            try:
                db_column, _target = fk_graph.resolve_segment(inv.entity, column)
            except ValueError:
                db_column = column  # not an FK — a plain column
        if kind == "input":
            if value not in inputs:
                raise AtomicFlowError(inv.entity, f"invariant filter input '{value}' not supplied")
            resolved: Any = inputs[value]
        else:  # literal
            resolved = _coerce_literal(value)
        where_terms.append((db_column, resolved))
    return where_terms


def _resolve_rhs(
    inv: ir.FlowInvariant,
    flow: ir.AtomicFlowSpec,
    inputs: dict[str, Any],
    conn: Any,
) -> Any:
    """Resolve the invariant's RHS bound (literal or anchor-row field)."""
    rhs = inv.rhs
    if rhs.literal is not None:
        return rhs.literal

    # Field form: `<op> input.<ref-input>.<field>`. The input is a `ref <Entity>`
    # flow input; read the field off the referenced row by id.
    rhs_input = next((i for i in flow.inputs if i.name == rhs.anchor_input), None)
    if rhs_input is None or rhs_input.type.ref_entity is None:
        raise AtomicFlowError(
            inv.entity,
            f"invariant RHS input '{rhs.anchor_input}' is not a ref input (validator gap?)",
        )
    if rhs.anchor_input not in inputs:
        raise AtomicFlowError(inv.entity, f"invariant RHS input '{rhs.anchor_input}' not supplied")
    rhs_entity = rhs_input.type.ref_entity
    sql = (
        f"SELECT {quote_identifier(rhs.anchor_field or '')} "
        f"FROM {quote_identifier(rhs_entity)} WHERE {quote_identifier('id')} = %s"
    )
    cur = conn.cursor()
    cur.execute(sql, [inputs[rhs.anchor_input]])  # nosemgrep — identifiers quoted, id bound
    row = cur.fetchone()
    if row is None:
        raise AtomicFlowError(
            inv.entity, f"invariant RHS anchor row id={inputs[rhs.anchor_input]!r} not found"
        )
    return _first_value(row)


def enforce_flow_invariants(
    conn: Any,
    flow: ir.AtomicFlowSpec,
    inputs: dict[str, Any],
    fk_graph: Any,
) -> None:
    """Enforce every invariant on ``flow``, in order, inside the flow transaction.

    For each invariant: lock the anchor row ``FOR UPDATE`` (gating concurrent
    writers to the aggregate set), resolve + run the scope-free aggregate, resolve
    the RHS, compare per ``inv.op``. A violation raises :class:`AtomicFlowError`;
    a DB / resolution error propagates (both roll the flow back). Fail-closed —
    no exception is swallowed.
    """
    for inv in flow.invariants:
        # (a) Lock the anchor FOR UPDATE first. The anchor is the row the
        #     aggregate set hangs off (e.g. the Transaction whose Postings we
        #     sum). FOR UPDATE blocks concurrent flows mutating the same set
        #     until this one commits/rolls back, closing the read-modify TOCTOU.
        if inv.anchor_entity is None or inv.anchor_input is None:
            # The validator rejects unanchored invariants; a None here means a
            # validator gap. Fail closed rather than skip the check.
            raise AtomicFlowError(
                inv.entity, "invariant has no anchor (validator gap?) — refusing to commit"
            )
        if inv.anchor_input not in inputs:
            raise AtomicFlowError(
                inv.entity, f"invariant anchor input '{inv.anchor_input}' not supplied"
            )
        anchor_sql = (
            f"SELECT {quote_identifier('id')} FROM {quote_identifier(inv.anchor_entity)} "
            f"WHERE {quote_identifier('id')} = %s FOR UPDATE"
        )
        try:
            lock_cur = conn.cursor()
            lock_cur.execute(anchor_sql, [inputs[inv.anchor_input]])  # nosemgrep — quoted+bound
            lock_cur.fetchone()
        except AtomicFlowError:
            raise
        except Exception as exc:
            raise AtomicFlowError(inv.entity, f"invariant anchor lock failed: {exc}") from exc

        # (b)+(c) Resolve WHERE terms + run the aggregate.
        try:
            where_terms = _resolve_where_terms(inv, inputs, fk_graph)
            agg_sql, agg_params = build_invariant_sql(
                inv.agg_fn, inv.entity, inv.field, where_terms
            )
            agg_cur = conn.cursor()
            agg_cur.execute(agg_sql, agg_params)  # nosemgrep — identifiers quoted, values bound
            agg_row = agg_cur.fetchone()
            agg_value = _first_value(agg_row) if agg_row is not None else 0
        except AtomicFlowError:
            raise
        except Exception as exc:
            raise AtomicFlowError(inv.entity, f"invariant aggregate query failed: {exc}") from exc

        # (d) Resolve the RHS bound.
        rhs_value = _resolve_rhs(inv, flow, inputs, conn)

        # (e) Compare (both coerced to Decimal). A non-numeric value fails closed.
        try:
            lhs = _to_decimal(agg_value)
            rhs = _to_decimal(rhs_value)
        except ValueError as exc:
            raise AtomicFlowError(inv.entity, f"invariant comparison failed: {exc}") from exc
        comparator = _COMPARATORS[inv.op]
        if not comparator(lhs, rhs):
            raise AtomicFlowError(
                flow.name,
                f"invariant violated: {inv.agg_fn.value}({inv.entity}) "
                f"{inv.op.value} {rhs_value} (was {agg_value})",
            )
