"""Predicate compiler — translates ScopePredicate trees into parameterised SQL.

The compiled SQL is a WHERE fragment (no leading WHERE keyword).  Parameters
are returned as a plain list; positional ``%s`` placeholders are used
throughout so the result is compatible with any DB-API 2.0 driver.

Two marker types are returned in the params list instead of resolved values:

- :class:`UserAttrRef` — a named attribute on the current user that the route
  handler must resolve at request time (e.g. ``current_user.school_id``).
- :class:`CurrentUserRef` — the authenticated user's entity UUID.

Neither marker is resolved here; the compiler is purely structural.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dazzle.core.ir.fk_graph import FKEdge, FKGraph
from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    ExistsCheck,
    PathCheck,
    ScopePredicate,
    Tautology,
    UserAttrCheck,
    ValueRef,
)
from dazzle_back.runtime.query_builder import quote_identifier

# ---------------------------------------------------------------------------
# Marker types (not resolved by the compiler)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UserAttrRef:
    """Marker: the route handler must resolve this to ``current_user.<attr_name>``."""

    attr_name: str


@dataclass(frozen=True)
class CurrentUserRef:
    """Marker: the route handler must resolve this to the current user's entity UUID."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_fk_edges(fk_graph: FKGraph, entity: str) -> list[FKEdge]:
    """Return the FK edges for *entity* regardless of internal storage format.

    The canonical :class:`FKGraph` stores edges as ``dict[str, dict[str, str]]``
    (entity → {fk_field: target_entity}).  Tests may inject a
    ``dict[str, list[FKEdge]]`` directly for readability.  This helper
    normalises both cases to a list of :class:`FKEdge` instances.
    """
    raw: dict[str, str] | list[FKEdge] = fk_graph._edges.get(entity, [])
    if isinstance(raw, list):
        return raw  # already list[FKEdge]
    # dict[str, str] → list[FKEdge]
    return [FKEdge(from_entity=entity, fk_field=fk, to_entity=target) for fk, target in raw.items()]


def _resolve_segment(fk_graph: FKGraph, entity: str, segment: str) -> tuple[str, str]:
    """Resolve one path segment to ``(fk_field, target_entity)``.

    Accepts both exact FK field names (``manuscript_id``) and relation names
    (``manuscript`` → appends ``_id``).

    Raises:
        ValueError: If *segment* cannot be resolved as an FK on *entity*.
    """
    edges = _resolve_fk_edges(fk_graph, entity)
    edge_map = {e.fk_field: e.to_entity for e in edges}

    # 1. Exact FK field name
    if segment in edge_map:
        return segment, edge_map[segment]

    # 2. Relation name → append _id
    candidate = f"{segment}_id"
    if candidate in edge_map:
        return candidate, edge_map[candidate]

    raise ValueError(
        f"Entity '{entity}' has no FK for segment '{segment}' "
        f"(tried '{segment}' and '{candidate}'). "
        f"Available FKs: {sorted(edge_map.keys()) or 'none'}"
    )


def _compile_value_ref(value: ValueRef) -> tuple[str | None, list[Any]]:
    """Return ``(sql_fragment_or_None, params)`` for a value reference.

    Returns ``None`` for the SQL fragment when the value produces an inline SQL
    token (e.g. NULL) rather than a placeholder.
    """
    if value.literal_null:
        return None, []  # caller emits IS NULL / IS NOT NULL directly
    if value.current_user:
        return "%s", [CurrentUserRef()]
    if value.user_attr is not None:
        return "%s", [UserAttrRef(value.user_attr)]
    # scalar literal (str, int, float, bool, or None-valued literal)
    return "%s", [value.literal]


def _op_to_sql(op: CompOp) -> str:
    """Map a :class:`CompOp` to its SQL operator string."""
    _MAP: dict[CompOp, str] = {
        CompOp.EQ: "=",
        CompOp.NEQ: "!=",
        CompOp.GT: ">",
        CompOp.LT: "<",
        CompOp.GTE: ">=",
        CompOp.LTE: "<=",
        CompOp.IN: "IN",
        CompOp.NOT_IN: "NOT IN",
        CompOp.IS: "IS",
        CompOp.IS_NOT: "IS NOT",
    }
    return _MAP[op]


# ---------------------------------------------------------------------------
# Per-node compilers
# ---------------------------------------------------------------------------


def _compile_column_check(predicate: ColumnCheck) -> tuple[str, list[Any]]:
    col = quote_identifier(predicate.field)
    op_sql = _op_to_sql(predicate.op)
    value = predicate.value

    if value.literal_null:
        # IS NULL / IS NOT NULL — no placeholder
        if predicate.op is CompOp.IS:
            return f"{col} IS NULL", []
        if predicate.op is CompOp.IS_NOT:
            return f"{col} IS NOT NULL", []
        # Fallback for any other op (unusual but safe)
        return f"{col} {op_sql} NULL", []

    _, params = _compile_value_ref(value)
    return f"{col} {op_sql} %s", params


def _compile_user_attr_check(predicate: UserAttrCheck) -> tuple[str, list[Any]]:
    col = quote_identifier(predicate.field)
    op_sql = _op_to_sql(predicate.op)
    return f"{col} {op_sql} %s", [UserAttrRef(predicate.user_attr)]


def _qualify_table(name: str, schema: str | None) -> str:
    """Return a possibly schema-qualified table identifier.

    With schema: ``"tenant_abc"."CompanyContact"``
    Without:     ``"CompanyContact"``
    """
    ident = quote_identifier(name)
    if schema:
        return f"{quote_identifier(schema)}.{ident}"
    return ident


def _compile_path_check(
    predicate: PathCheck,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
) -> tuple[str, list[Any]]:
    """Compile a PathCheck to a nested IN (SELECT …) expression.

    The path is walked inside-out.  For a depth-2 path on entity ``Feedback``
    with path ``["manuscript", "assessment_event", "school_id"]`` the result
    is::

        "manuscript_id" IN (
            SELECT "assessment_event_id" FROM "Manuscript"
            WHERE "assessment_event_id" IN (
                SELECT "school_id" FROM "AssessmentEvent"
                WHERE "school_id" = %s
            )
        )

    Algorithm:
    1. Walk path segments (all but the last) to collect FK hops.
    2. The last segment is the terminal comparison field on the final entity.
    3. Build subqueries from the innermost outward.
    """
    path = predicate.path

    if len(path) < 2:
        raise ValueError(f"PathCheck.path must have at least 2 segments, got {path!r}")

    # Resolve FK hops (all segments except the last)
    # Each hop: (from_entity, fk_field, target_entity)
    hops: list[tuple[str, str, str]] = []
    current_entity = entity_name
    for segment in path[:-1]:
        fk_field, target_entity = _resolve_segment(fk_graph, current_entity, segment)
        hops.append((current_entity, fk_field, target_entity))
        current_entity = target_entity

    # Terminal: last path segment is the comparison field on the final entity
    terminal_segment = path[-1]
    # Try exact field name first, then append _id
    if fk_graph.field_exists(current_entity, terminal_segment):
        terminal_field = terminal_segment
    elif fk_graph.field_exists(current_entity, f"{terminal_segment}_id"):
        terminal_field = f"{terminal_segment}_id"
    else:
        # Accept it as-is (may be on an entity not in the graph, e.g. in tests)
        terminal_field = terminal_segment

    # Compile the value
    _, value_params = _compile_value_ref(predicate.value)
    value_op = _op_to_sql(predicate.op)

    if predicate.value.literal_null:
        if predicate.op is CompOp.IS:
            innermost_condition = f"{quote_identifier(terminal_field)} IS NULL"
        else:
            innermost_condition = f"{quote_identifier(terminal_field)} IS NOT NULL"
        params: list[Any] = []
    else:
        innermost_condition = f"{quote_identifier(terminal_field)} {value_op} %s"
        params = list(value_params)

    # Build subqueries from inside out.
    # The innermost SELECT is on the target entity of the last hop, selecting
    # the terminal comparison field.
    _last_from, last_fk_field, last_target_entity = hops[-1]

    # Innermost: SELECT terminal_field FROM final_entity WHERE <condition>
    inner_sql = (
        f"SELECT {quote_identifier(terminal_field)} "
        f"FROM {_qualify_table(last_target_entity, schema)} "
        f"WHERE {innermost_condition}"
    )
    # The FK column in the preceding entity that we need to match against
    # this subquery is last_fk_field (from the last hop's source entity).
    inner_match_fk = last_fk_field

    # Walk remaining hops outward (second-to-last toward root, reversed)
    for _from_entity, fk_field, target_entity in reversed(hops[:-1]):
        inner_sql = (
            f"SELECT {quote_identifier(fk_field)} "
            f"FROM {_qualify_table(target_entity, schema)} "
            f"WHERE {quote_identifier(inner_match_fk)} IN ({inner_sql})"
        )
        inner_match_fk = fk_field

    # Outermost clause: root fk_field IN (subquery)
    root_fk_field = hops[0][1]
    sql = f"{quote_identifier(root_fk_field)} IN ({inner_sql})"
    return sql, params


def _compile_exists_check(
    predicate: ExistsCheck,
    entity_name: str,
    *,
    schema: str | None = None,
) -> tuple[str, list[Any]]:
    """Compile an ExistsCheck to an [NOT] EXISTS (SELECT 1 FROM …) expression."""
    target = _qualify_table(predicate.target_entity, schema)
    conditions: list[str] = []
    params: list[Any] = []

    for binding in predicate.bindings:
        jf = quote_identifier(binding.junction_field)
        op = binding.operator  # "=" or "!="

        target_val = binding.target
        if target_val == "current_user":
            conditions.append(f"{jf} {op} %s")
            params.append(CurrentUserRef())
        elif target_val == "id":
            # Bind to the root entity's primary key
            conditions.append(f"{jf} {op} {quote_identifier(entity_name)}.{quote_identifier('id')}")
        elif target_val == "null":
            if op == "=":
                conditions.append(f"{jf} IS NULL")
            else:
                conditions.append(f"{jf} IS NOT NULL")
        elif target_val.startswith("current_user."):
            attr = target_val[len("current_user.") :]
            conditions.append(f"{jf} {op} %s")
            params.append(UserAttrRef(attr))
        else:
            # Treat as a literal field reference or literal value
            conditions.append(f"{jf} {op} %s")
            params.append(target_val)

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    exists_kw = "NOT EXISTS" if predicate.negated else "EXISTS"
    sql = f"{exists_kw} (SELECT 1 FROM {target} WHERE {where_clause})"
    return sql, params


def _compile_bool_composite(
    predicate: BoolComposite,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
) -> tuple[str, list[Any]]:
    """Compile a BoolComposite (AND / OR / NOT) node."""
    if predicate.op is BoolOp.NOT:
        assert len(predicate.children) == 1
        child_sql, child_params = compile_predicate(
            predicate.children[0], entity_name, fk_graph, schema=schema
        )
        return f"NOT ({child_sql})", child_params

    joiner = " AND " if predicate.op is BoolOp.AND else " OR "
    parts: list[str] = []
    all_params: list[Any] = []
    for child in predicate.children:
        child_sql, child_params = compile_predicate(child, entity_name, fk_graph, schema=schema)
        parts.append(f"({child_sql})")
        all_params.extend(child_params)

    return joiner.join(parts), all_params


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compile_predicate(
    predicate: ScopePredicate,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
) -> tuple[str, list[Any]]:
    """Compile a :class:`ScopePredicate` tree to a parameterised SQL fragment.

    Args:
        predicate: The predicate tree to compile.
        entity_name: The root entity being filtered (used for ExistsCheck
            bindings that reference ``id`` and for PathCheck traversal).
        fk_graph: The FK graph for the current app spec (used for PathCheck
            path resolution).
        schema: Optional schema name for tenant isolation (e.g. ``tenant_abc``).
            When set, all table references in subqueries are schema-qualified.

    Returns:
        A ``(sql, params)`` tuple where *sql* is a WHERE fragment (no leading
        ``WHERE`` keyword) and *params* is a list of positional parameters.
        Marker objects (:class:`UserAttrRef`, :class:`CurrentUserRef`) appear
        in *params* wherever the route handler must substitute a runtime value.
    """
    match predicate:
        case Tautology():
            return "", []

        case Contradiction():
            return "FALSE", []

        case ColumnCheck():
            return _compile_column_check(predicate)

        case UserAttrCheck():
            return _compile_user_attr_check(predicate)

        case PathCheck():
            return _compile_path_check(predicate, entity_name, fk_graph, schema=schema)

        case ExistsCheck():
            return _compile_exists_check(predicate, entity_name, schema=schema)

        case BoolComposite():
            return _compile_bool_composite(predicate, entity_name, fk_graph, schema=schema)

        case _:
            raise TypeError(f"Unknown predicate type: {type(predicate)!r}")
