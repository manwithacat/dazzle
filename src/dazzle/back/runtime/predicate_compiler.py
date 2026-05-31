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

from dataclasses import dataclass
from typing import Any

from dazzle.back.runtime.query_builder import quote_identifier
from dazzle.core.ir.fk_graph import FKEdge, FKGraph
from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    ColumnRefCheck,
    CompOp,
    Contradiction,
    ExistsCheck,
    PathCheck,
    ScopePredicate,
    Tautology,
    UserAttrCheck,
    ValueRef,
)

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


@dataclass(frozen=True)
class PayloadFieldRef:
    """Marker: resolve to the create payload's value for ``field_name``.

    Used only by the ``scope: create:`` payload-time probe (#1311). At
    create time the root row does not exist yet, so a PathCheck's root FK
    column — or an ExistsCheck binding that references an entity column /
    ``id`` — must bind to the *incoming payload's* value rather than a
    column on a (non-existent) root row. The create-scope walker
    (``scope_create_eval``) substitutes ``payload[field_name]`` (trying the
    relation-name / ``<name>_id`` variants) before executing the probe SQL.
    """

    field_name: str


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


def _compile_column_check(
    predicate: ColumnCheck,
    *,
    entity_name: str = "",
    schema: str | None = None,
    fk_graph: FKGraph | None = None,
) -> tuple[str, list[Any]]:
    col = _qualify_column(predicate.field, entity_name, schema, fk_graph)
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


def _compile_user_attr_check(
    predicate: UserAttrCheck,
    *,
    entity_name: str = "",
    schema: str | None = None,
    fk_graph: FKGraph | None = None,
) -> tuple[str, list[Any]]:
    col = _qualify_column(predicate.field, entity_name, schema, fk_graph)
    op_sql = _op_to_sql(predicate.op)
    return f"{col} {op_sql} %s", [UserAttrRef(predicate.user_attr)]


def _compile_column_ref_check(
    predicate: ColumnRefCheck,
    *,
    entity_name: str = "",
    schema: str | None = None,
    fk_graph: FKGraph | None = None,
) -> tuple[str, list[Any]]:
    """Compile a same-row column-vs-column comparison.

    Both sides are column identifiers — no parameters, no risk of literal
    coercion. Used by reporting aggregate where-clauses (#888); not used
    by RBAC scope rules.
    """
    f1 = _qualify_column(predicate.field, entity_name, schema, fk_graph)
    f2 = _qualify_column(predicate.other_field, entity_name, schema, fk_graph)
    return f"{f1} {_op_to_sql(predicate.op)} {f2}", []


def _qualify_column(
    field: str,
    entity_name: str,
    schema: str | None,
    fk_graph: FKGraph | None = None,
) -> str:
    """Qualify a column reference with the source entity table.

    v0.61.77 (#909): scope predicates that reference entity columns
    (`school = current_user.school`, `status = active`) used to emit
    unqualified column names like `"school" = %s`. When the runtime
    later applies a source-table alias to user filters (because FK
    display joins introduced ambiguity), the scope predicate stayed
    unqualified — so `"school"` could bind to a JOINed table's
    `school` column instead of the source entity's.

    v0.61.78 (#910): pure qualification (`"StudentProfile"."school"`)
    blew up when the DSL author wrote a *relation name* (`school`)
    instead of the FK column (`school_id`) — Postgres errored on the
    missing column. Mirror the PathCheck heuristic: when the bare
    name doesn't exist, try `<field>_id`; if neither exists fall
    back to the bare ref to avoid 500 on legitimate edge cases (the
    column may live on an entity not in the FK graph, e.g. tests).

    Empty entity_name (callers that pre-date the fix) falls back to
    bare column ref for compatibility.
    """
    if not entity_name:
        return quote_identifier(field)

    resolved_field = _resolve_field_on_entity(field, entity_name, fk_graph)
    return f"{_qualify_table(entity_name, schema)}.{quote_identifier(resolved_field)}"


def _resolve_field_on_entity(
    field: str,
    entity_name: str,
    fk_graph: FKGraph | None,
) -> str:
    """Resolve `field` to the actual column name on `entity_name`.

    Heuristic mirrored from `_compile_path_check`: if `field` exists
    as-is on the entity use it; otherwise try `<field>_id` (DSL
    authors often write the relation name, not the FK column);
    otherwise fall back to the bare name (the column may live on an
    entity not in the FK graph — fall through and let SQL surface
    any genuine schema error rather than fabricating a column name).
    """
    if fk_graph is None:
        return field
    if fk_graph.field_exists(entity_name, field):
        return field
    candidate = f"{field}_id"
    if fk_graph.field_exists(entity_name, candidate):
        return candidate
    return field


def _qualify_table(name: str, schema: str | None) -> str:
    """Return a possibly schema-qualified table identifier.

    With schema: ``"tenant_abc"."CompanyContact"``
    Without:     ``"CompanyContact"``
    """
    ident = quote_identifier(name)
    if schema:
        return f"{quote_identifier(schema)}.{ident}"
    return ident


def _path_check_subquery(
    predicate: PathCheck,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
) -> tuple[str, str, str, list[Any]]:
    """Decompose a PathCheck into the pieces both compile forms need.

    Returns ``(root_fk_field, root_target_table, where_body, params)`` where
    ``root_target_table`` is the (schema-qualified) table the root FK points
    at, and ``where_body`` is the WHERE condition that lives on that table —
    the terminal comparison for a 1-hop path, or a nested ``"fk" IN (SELECT
    "id" FROM … )`` for deeper paths. The full existing-row subquery is then
    ``SELECT "id" FROM <root_target_table> WHERE <where_body>``.

    For a depth-3 path on ``Feedback`` with
    ``["manuscript", "assessment_event", "school_id"]`` the pieces are
    ``root_fk_field="manuscript_id"``, ``root_target_table='"Manuscript"'``,
    ``where_body='"assessment_event_id" IN (SELECT "id" FROM "AssessmentEvent"
    WHERE "school_id" = %s)'``.
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

    # Walk hops from the deepest toward the root, accumulating the WHERE body
    # that lives on each successive entity's *target* table. The innermost
    # body is the terminal condition on the final entity.
    _last_from, last_fk_field, last_target_entity = hops[-1]
    from_table = _qualify_table(last_target_entity, schema)
    where_body = innermost_condition
    # FK on the preceding entity that points into `from_table`.
    match_fk = last_fk_field

    for _from_entity, fk_field, target_entity in reversed(hops[:-1]):
        inner_select = f'SELECT "id" FROM {from_table} WHERE {where_body}'
        from_table = _qualify_table(target_entity, schema)
        where_body = f"{quote_identifier(match_fk)} IN ({inner_select})"
        match_fk = fk_field

    root_fk_field = hops[0][1]
    return root_fk_field, from_table, where_body, params


def _compile_path_check(
    predicate: PathCheck,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
) -> tuple[str, list[Any]]:
    """Compile a PathCheck to a nested ``"<root_fk>" IN (SELECT …)`` expression.

    Filters an *existing* root row. For a depth-3 path on ``Feedback`` with
    ``["manuscript", "assessment_event", "school_id"]`` the result is::

        "manuscript_id" IN (
            SELECT "id" FROM "Manuscript"
            WHERE "assessment_event_id" IN (
                SELECT "id" FROM "AssessmentEvent" WHERE "school_id" = %s
            )
        )
    """
    root_fk_field, root_target_table, where_body, params = _path_check_subquery(
        predicate, entity_name, fk_graph, schema=schema
    )
    inner_sql = f'SELECT "id" FROM {root_target_table} WHERE {where_body}'
    return f"{quote_identifier(root_fk_field)} IN ({inner_sql})", params


def compile_path_check_probe(
    predicate: PathCheck,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
) -> tuple[str, list[Any]]:
    """Compile a depth>1 PathCheck into a create-scope probe expression (#1311).

    Unlike :func:`_compile_path_check` (which binds the root FK *column* of an
    existing row), the create-scope probe has no root row yet — so it matches
    the *payload's* root FK value against the target table's ``id``. The
    returned SQL is a boolean expression suitable for ``SELECT 1 WHERE <sql>``::

        EXISTS (SELECT 1 FROM "TeachingGroup" WHERE "id" = %s AND ("department" = %s))

    The payload FK is bound as ``"id" = %s`` (uuid column on the left, param on
    the right — the type-coercion-safe shape, matching the existing
    ``"<col>" = current_user`` enforcement). ``params[0]`` is a
    :class:`PayloadFieldRef` for the root FK column (the walker substitutes the
    payload's value); the remaining params are the terminal-condition value
    markers (``CurrentUserRef`` / ``UserAttrRef`` / literals), in order.
    """
    root_fk_field, root_target_table, where_body, params = _path_check_subquery(
        predicate, entity_name, fk_graph, schema=schema
    )
    sql = f'EXISTS (SELECT 1 FROM {root_target_table} WHERE "id" = %s AND ({where_body}))'
    return sql, [PayloadFieldRef(root_fk_field), *params]


def _compile_dotted_junction_predicate(
    junction_entity: str,
    path: list[str],
    op: str,
    value_sql: str,
    value_params: list[Any],
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
) -> str:
    """Expand a dotted junction-field predicate into nested IN (SELECT ...) (#858).

    Given ``junction_field = teaching_group.teacher.user`` on junction
    ``ClassEnrolment`` comparing against some ``value_sql``, walk the path
    segment-by-segment via the FK graph and emit the fully nested subquery.

    The *last* segment is the column on the tail entity that holds the
    comparison value; all prior segments must resolve to FK fields.
    """
    assert len(path) >= 2, "dotted path must have at least one hop + final column"
    *hop_segments, final_col = path

    # Resolve each hop to (fk_field, next_entity) starting from the junction.
    current_entity = junction_entity
    hops: list[tuple[str, str]] = []  # list of (fk_field, target_entity)
    for segment in hop_segments:
        fk_field, next_entity = _resolve_segment(fk_graph, current_entity, segment)
        hops.append((fk_field, next_entity))
        current_entity = next_entity

    # Build innermost WHERE first: on the entity that *owns* final_col,
    # which is hops[-1].to_entity (or the junction if there are no hops).
    tail_table = _qualify_table(current_entity, schema)
    inner_sql = (
        f"SELECT {quote_identifier('id')} FROM {tail_table} "
        f"WHERE {quote_identifier(final_col)} {op} {value_sql}"
    )

    # Wrap tail→head. For each intermediate hop, the FK lives on the
    # previous hop's target entity (or the junction for hop 0). So the
    # SELECT in each wrap is FROM the entity that *owns* this hop's FK.
    for i in range(len(hops) - 1, 0, -1):
        fk_field = hops[i][0]
        owner_entity = hops[i - 1][1]
        owner_table = _qualify_table(owner_entity, schema)
        inner_sql = (
            f"SELECT {quote_identifier('id')} FROM {owner_table} "
            f"WHERE {quote_identifier(fk_field)} IN ({inner_sql})"
        )

    # Outer binding: the first hop's fk_field IN (inner_sql) — bound against
    # the junction table via the enclosing EXISTS WHERE clause.
    root_fk = hops[0][0]
    return f"{quote_identifier(root_fk)} IN ({inner_sql})"


def _compile_exists_check(
    predicate: ExistsCheck,
    entity_name: str,
    fk_graph: FKGraph | None = None,
    *,
    schema: str | None = None,
    payload_mode: bool = False,
) -> tuple[str, list[Any]]:
    """Compile an ExistsCheck to an [NOT] EXISTS (SELECT 1 FROM …) expression.

    ``payload_mode`` (#1311): when True, bindings whose target is an entity
    column or ``id`` resolve to a :class:`PayloadFieldRef` placeholder rather
    than a ``"<entity>"."<col>"`` reference. This is the create-scope probe
    form — at create time the root row does not exist, so entity-side values
    come from the incoming payload. ``current_user`` / ``current_user.<attr>``
    / ``null`` targets are unaffected.
    """
    target = _qualify_table(predicate.target_entity, schema)
    conditions: list[str] = []
    params: list[Any] = []

    for binding in predicate.bindings:
        is_dotted = "." in binding.junction_field
        jf = quote_identifier(binding.junction_field) if not is_dotted else ""
        op = binding.operator  # "=" or "!="

        target_val = binding.target

        # Resolve right-hand value first — shared between dotted and flat paths.
        value_sql: str | None = None
        extra_params: list[Any] = []
        if target_val == "current_user":
            value_sql = "%s"
            extra_params.append(CurrentUserRef())
        elif target_val == "id":
            if payload_mode:
                value_sql = "%s"
                extra_params.append(PayloadFieldRef("id"))
            else:
                value_sql = f"{quote_identifier(entity_name)}.{quote_identifier('id')}"
        elif target_val == "null":
            pass  # handled specially below
        elif target_val.startswith("current_user."):
            attr = target_val[len("current_user.") :]
            value_sql = "%s"
            extra_params.append(UserAttrRef(attr))
        elif payload_mode:
            # Entity column referenced from a not-yet-existent root row →
            # bind to the create payload's value (#1311).
            value_sql = "%s"
            extra_params.append(PayloadFieldRef(target_val))
        else:
            value_sql = f"{quote_identifier(entity_name)}.{quote_identifier(target_val)}"

        if is_dotted:
            # Dotted junction-field (#858): expand via FK graph into nested
            # IN (SELECT …). NULL targets are not supported on dotted paths.
            if target_val == "null" or fk_graph is None or value_sql is None:
                raise ValueError(
                    f"Dotted via-binding '{binding.junction_field}' requires a "
                    f"non-null target value and the FK graph context"
                )
            path = binding.junction_field.split(".")
            clause = _compile_dotted_junction_predicate(
                predicate.target_entity,
                path,
                op,
                value_sql,
                extra_params,
                fk_graph,
                schema=schema,
            )
            conditions.append(clause)
            params.extend(extra_params)
            continue

        if target_val == "null":
            if op == "=":
                conditions.append(f"{jf} IS NULL")
            else:
                conditions.append(f"{jf} IS NOT NULL")
        else:
            assert value_sql is not None
            conditions.append(f"{jf} {op} {value_sql}")
            params.extend(extra_params)

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    exists_kw = "NOT EXISTS" if predicate.negated else "EXISTS"
    sql = f"{exists_kw} (SELECT 1 FROM {target} WHERE {where_clause})"
    return sql, params


def compile_exists_check_probe(
    predicate: ExistsCheck,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
) -> tuple[str, list[Any]]:
    """Compile an ExistsCheck into a create-scope probe expression (#1311).

    Like :func:`_compile_exists_check` but entity-column / ``id`` bindings
    resolve to :class:`PayloadFieldRef` markers (the root row does not exist
    yet at create time). The returned SQL is an ``[NOT] EXISTS (…)`` boolean
    expression suitable for ``SELECT 1 WHERE <sql>``.

    Note: a binding whose target is the root entity's own ``id`` is
    effectively unsatisfiable at create time — the row's id isn't in the
    payload yet, so it resolves to NULL → no match → deny. That's fail-closed
    and correct, but such a binding is almost never what an author wants on a
    *create* rule (the common shape references a payload FK column, e.g.
    ``via M(user = current_user, team = team)``).
    """
    return _compile_exists_check(predicate, entity_name, fk_graph, schema=schema, payload_mode=True)


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
    from dazzle.perf.tracer import dazzle_span

    with dazzle_span("predicate.compile", source_entity=entity_name):
        return _compile_predicate_impl(predicate, entity_name, fk_graph, schema=schema)


def _compile_predicate_impl(
    predicate: ScopePredicate,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
) -> tuple[str, list[Any]]:
    match predicate:
        case Tautology():
            return "", []

        case Contradiction():
            return "FALSE", []

        case ColumnCheck():
            return _compile_column_check(
                predicate, entity_name=entity_name, schema=schema, fk_graph=fk_graph
            )

        case ColumnRefCheck():
            return _compile_column_ref_check(
                predicate, entity_name=entity_name, schema=schema, fk_graph=fk_graph
            )

        case UserAttrCheck():
            return _compile_user_attr_check(
                predicate, entity_name=entity_name, schema=schema, fk_graph=fk_graph
            )

        case PathCheck():
            return _compile_path_check(predicate, entity_name, fk_graph, schema=schema)

        case ExistsCheck():
            return _compile_exists_check(predicate, entity_name, fk_graph, schema=schema)

        case BoolComposite():
            return _compile_bool_composite(predicate, entity_name, fk_graph, schema=schema)

        case _:
            raise TypeError(f"Unknown predicate type: {type(predicate)!r}")
