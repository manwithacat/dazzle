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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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
    PolyPathCheck,
    ScopePredicate,
    Tautology,
    UserAttrCheck,
    ValueRef,
)
from dazzle.http.runtime.query_builder import quote_identifier
from dazzle.http.runtime.rls_schema import HOST_TENANT_GUC, USER_GUC_PREFIX

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
class CurrentTenantRef:
    """Marker: resolve this to the host-resolved tenant's id (#1394).

    Bound from the host tenant context var (``request.state.tenant.id``), NOT
    the RLS row-tenancy ``dazzle.tenant_id`` — the two can diverge. The marker
    resolvers (``scope_filters`` / ``scope_create_eval``) fail closed (deny) when
    no host tenant is set, mirroring an unresolvable user attribute.
    """


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
# Policy-body (param-free) mode (Phase C)
# ---------------------------------------------------------------------------

#: A ``(entity_name, field_name) -> pg_type_name`` resolver. Returns the
#: PostgreSQL type *name* (e.g. ``"uuid"``, ``"text"``) for a column, used to
#: cast a ``current_setting(...)`` GUC read to the column's type. The resolver
#: must raise (any exception) when a type can't be resolved so policy
#: generation fails loudly rather than emitting a wrong-typed policy.
EntityTypeResolver = Callable[[str, str], str]

#: The fixed GUC prefix for per-request user attributes (mirrors Phase B's
#: ``dazzle.tenant_id``). ``current_user`` → ``dazzle.user_id``; a named
#: attribute ``a`` → ``dazzle.user_<a>``. Re-exported from the single source of
#: truth in ``rls_schema`` (next to ``TENANT_GUC``) so the name the policy body
#: READS and the name ``pg_backend`` SETS can never drift (C-2 drift-guard).
_USER_GUC_PREFIX = USER_GUC_PREFIX


@dataclass(frozen=True)
class _PolicyCtx:
    """Threaded through the ``_compile_*`` functions to switch to policy mode.

    When ``None`` is threaded (the default), the compiler emits the
    byte-for-byte unchanged param-mode output (``%s`` + marker params). When a
    ``_PolicyCtx`` is present, value emit points instead inline a self-contained
    SQL token (GUC read + cast, or an escaped literal) and return no params.
    """

    #: Resolves a column to its pg type name for the GUC cast.
    types: EntityTypeResolver


def _inline_sql_literal(value: str | int | float | bool | None) -> str:
    """Render a scalar to a safe, self-contained SQL literal token.

    - ``None`` → ``NULL``
    - ``bool`` → ``true`` / ``false`` (checked before ``int`` — ``bool`` is an
      ``int`` subclass)
    - ``str`` → single-quoted with SQL-standard ``'`` → ``''`` escaping
    - ``int`` / ``float`` → ``str(value)``

    Scope-rule literals are author/IR-controlled, but every value is rendered
    safely regardless (no raw value ever reaches the policy string).
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # str — SQL-standard single-quote escaping.
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


# Map a DSL scalar type → the PostgreSQL type *name* used in a ``::<type>``
# cast. Mirrors ``sa_schema._scalar_type_to_sa`` but yields a name string
# rather than a SQLAlchemy type instance.
# Scalars are mapped explicitly where the pg type is *not* text; everything
# else (str/text/email/url/slug/timezone/file/image/richtext/…) falls back to
# ``text`` in :func:`_field_type_to_pg` — exactly mirroring
# ``sa_schema._scalar_type_to_sa``'s ``.get(scalar_type, sa.Text())`` default.
_SCALAR_TO_PG_NAME: dict[str, str] = {
    "int": "integer",
    "decimal": "numeric",
    "float": "double precision",
    "bool": "boolean",
    "date": "date",
    "datetime": "timestamptz",
    "uuid": "uuid",
    "json": "jsonb",
}


def _field_type_to_pg(field_type: Any) -> str:
    """Map a DSL ``FieldType`` to a PostgreSQL type-name string for a cast.

    Mirrors ``sa_schema._field_type_to_sa`` (incl. its Text fallback for any
    unlisted scalar) but returns a name (``"uuid"``, ``"text"``, ``"integer"``,
    ``"boolean"``, ``"numeric"``, ``"timestamptz"``, …) suitable for
    ``current_setting(...)::<name>``.

    - ``kind="ref"`` → ``uuid`` (FK columns are uuid)
    - ``kind="enum"`` → ``text`` (enums are stored as TEXT)
    - ``kind="scalar"`` → :data:`_SCALAR_TO_PG_NAME`, else ``text`` (so
      ``str``/``email``/``url``/``slug``/``timezone``/``file``/``image``/
      ``richtext``/… all resolve to ``text``, matching the SA bridge).

    Raises:
        ValueError: only when the *kind* itself is unrecognised (a malformed
            FieldType) — a genuinely-unmappable shape, not a text-ish scalar.
    """
    kind = getattr(field_type, "kind", None)
    if kind == "ref":
        return "uuid"
    if kind == "enum":
        return "text"
    if kind == "scalar":
        scalar = field_type.scalar_type
        scalar_val = scalar.value if hasattr(scalar, "value") else str(scalar)
        # Non-text scalars are mapped explicitly; everything else → text.
        return _SCALAR_TO_PG_NAME.get(scalar_val, "text")
    raise ValueError(f"No pg cast type for field type kind {kind!r}")


def build_entity_type_resolver(entities: list[Any]) -> EntityTypeResolver:
    """Build a lazy :data:`EntityTypeResolver` from a list of ``EntitySpec``.

    Resolution is **on demand**: a column's pg type is computed (via
    :func:`_field_type_to_pg`) only when a scope policy actually references it,
    then cached. A column never referenced in a scope comparison never triggers
    :func:`_field_type_to_pg`, so an app with (say) a ``richtext`` field on an
    unscoped entity can't break resolver construction.

    The callable raises ``ValueError`` for an unknown ``(entity, field)`` pair
    so policy generation fails loudly when a *referenced* column truly has no
    type.
    """
    # (entity, field) -> FieldType, built without computing any pg type.
    field_types: dict[tuple[str, str], Any] = {}
    for entity in entities:
        ename = entity.name
        for field in entity.fields:
            field_types[(ename, field.name)] = field.type

    cache: dict[tuple[str, str], str] = {}

    def resolver(entity_name: str, field_name: str) -> str:
        key = (entity_name, field_name)
        if key in cache:
            return cache[key]
        try:
            field_type = field_types[key]
        except KeyError:
            raise ValueError(
                f"No pg type for column {entity_name}.{field_name} "
                f"(cannot cast its GUC in an RLS policy body)"
            ) from None
        pg = _field_type_to_pg(field_type)  # lazy — only for referenced columns
        cache[key] = pg
        return pg

    return resolver


def _guc_read(name: str, pg_type: str) -> str:
    """Render a ``current_setting('dazzle.user_<name>', true)::<type>`` token.

    The ``true`` (missing-ok) argument is always passed so an unset GUC reads
    NULL → the predicate fails closed rather than erroring.
    """
    # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query
    # Closed templated DDL over IR-controlled values: `name` is an IR field/attr
    # identifier and `pg_type` comes from the closed `_SCALAR_TO_PG_NAME` map —
    # neither is request data. The literal channel uses `_inline_sql_literal`.
    return f"current_setting('{_USER_GUC_PREFIX}{name}', true)::{pg_type}"


def _guc_read_host_tenant(pg_type: str) -> str:
    """Render a fail-closed ``dazzle.host_tenant_id`` GUC read cast to ``pg_type`` (#1394).

    The host-tenant GUC is distinct from the RLS ``dazzle.tenant_id`` (see
    ``HOST_TENANT_GUC``). Two reset states must both fail closed (deny), never
    error or leak:
      * never set on this connection → ``current_setting(.., true)`` is NULL;
      * set ``LOCAL`` by a prior request and reverted on a *pooled* connection →
        the placeholder reverts to the empty string ``''``, and a bare
        ``''::uuid`` would RAISE rather than deny.
    ``NULLIF(.., '')`` collapses the empty-string case to NULL so ``col = NULL``
    simply matches no rows. The host GUC is not set on every request (None for
    non-tenant / apex), so unlike the always-set RLS fence it is genuinely
    exposed to the pooled-empty-string state — hence the belt-and-suspenders.
    """
    # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query
    # Closed templated DDL: the GUC name is the fixed framework constant and
    # `pg_type` comes from the closed `_SCALAR_TO_PG_NAME` map — neither is request data.
    return f"NULLIF(current_setting('{HOST_TENANT_GUC}', true), '')::{pg_type}"


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


def _compile_value_ref(
    value: ValueRef,
    *,
    policy: _PolicyCtx | None = None,
    pg_type: str | None = None,
) -> tuple[str | None, list[Any]]:
    """Return ``(sql_fragment_or_None, params)`` for a value reference.

    Returns ``None`` for the SQL fragment when the value produces an inline SQL
    token (e.g. NULL) rather than a placeholder.

    Default (``policy is None``) — **param mode**, byte-for-byte unchanged:
    ``current_user`` → ``("%s", [CurrentUserRef()])``, ``user_attr`` →
    ``("%s", [UserAttrRef(...)])``, literal → ``("%s", [value.literal])``.

    Policy mode (``policy`` set) — **param-free**: ``current_user`` →
    ``(current_setting('dazzle.user_id', true)::<pg_type>, [])``, ``user_attr a``
    → ``(current_setting('dazzle.user_a', true)::<pg_type>, [])``, literal →
    ``(_inline_sql_literal(value.literal), [])``. ``pg_type`` is the GUC cast
    type (the *column's* pg type) and is required for ``current_user`` /
    ``user_attr`` in policy mode (raises ``ValueError`` if missing).
    """
    if value.literal_null:
        return None, []  # caller emits IS NULL / IS NOT NULL directly

    if policy is None:
        if value.current_user:
            return "%s", [CurrentUserRef()]
        if value.current_tenant:
            return "%s", [CurrentTenantRef()]
        if value.user_attr is not None:
            return "%s", [UserAttrRef(value.user_attr)]
        # scalar literal (str, int, float, bool, or None-valued literal)
        return "%s", [value.literal]

    # --- policy mode: inline self-contained tokens, no params ---
    if value.current_user:
        if pg_type is None:
            raise ValueError("policy mode: cannot cast a current_user GUC without a column pg type")
        return _guc_read("id", pg_type), []
    if value.current_tenant:
        if pg_type is None:
            raise ValueError(
                "policy mode: cannot cast a current_tenant GUC without a column pg type"
            )
        return _guc_read_host_tenant(pg_type), []
    if value.user_attr is not None:
        if pg_type is None:
            raise ValueError(
                f"policy mode: cannot cast user attr {value.user_attr!r} "
                "GUC without a column pg type"
            )
        return _guc_read(value.user_attr, pg_type), []
    return _inline_sql_literal(value.literal), []


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
    policy: _PolicyCtx | None = None,
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

    pg_type = (
        _resolve_column_pg_type(predicate.field, entity_name, fk_graph, policy)
        if policy is not None
        else None
    )
    token, params = _compile_value_ref(value, policy=policy, pg_type=pg_type)
    rhs = token if policy is not None else "%s"
    return f"{col} {op_sql} {rhs}", params


def _compile_user_attr_check(
    predicate: UserAttrCheck,
    *,
    entity_name: str = "",
    schema: str | None = None,
    fk_graph: FKGraph | None = None,
    policy: _PolicyCtx | None = None,
) -> tuple[str, list[Any]]:
    col = _qualify_column(predicate.field, entity_name, schema, fk_graph)
    op_sql = _op_to_sql(predicate.op)
    if policy is None:
        return f"{col} {op_sql} %s", [UserAttrRef(predicate.user_attr)]
    pg_type = _resolve_column_pg_type(predicate.field, entity_name, fk_graph, policy)
    return f"{col} {op_sql} {_guc_read(predicate.user_attr, pg_type)}", []


def _resolve_column_pg_type(
    field: str,
    entity_name: str,
    fk_graph: FKGraph | None,
    policy: _PolicyCtx,
) -> str:
    """Resolve the pg cast type for a column in policy mode.

    Mirrors :func:`_resolve_field_on_entity` so the type is looked up against
    the *same* column name the SQL references (bare name, else ``<field>_id``).
    Delegates to the ``policy.types`` resolver, which raises ``ValueError`` when
    the type can't be resolved — propagated so policy generation fails loudly.
    """
    resolved_field = _resolve_field_on_entity(field, entity_name, fk_graph)
    return policy.types(entity_name, resolved_field)


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
    # #1386: qualify the root entity's own column to the BARE table, never the
    # tenant ``schema``. The FROM clause is emitted unqualified (resolved via
    # ``search_path``), so a schema-qualified WHERE ref (``"tenant_x"."E"."col"``)
    # diverges from it and 500s with UndefinedTable when the tenant schema lacks
    # the table. An unqualified ``"E"."col"`` resolves through ``search_path``
    # identically to FROM (both single-tenant-from-public and schema-per-tenant).
    # ``schema`` is kept in the signature for the column-ref caller's contract.
    _ = schema  # intentionally not schema-qualified for root columns (see above)
    return f"{_qualify_table(entity_name, None)}.{quote_identifier(resolved_field)}"


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
    policy: _PolicyCtx | None = None,
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

    # Compile the value. In policy mode the GUC cast type is the *terminal*
    # column's type (resolved against the final entity in the path). Only
    # resolved when a value token is actually needed (not for IS NULL).
    pg_type = (
        policy.types(current_entity, terminal_field)
        if policy is not None and not predicate.value.literal_null
        else None
    )
    value_token, value_params = _compile_value_ref(predicate.value, policy=policy, pg_type=pg_type)
    value_op = _op_to_sql(predicate.op)

    if predicate.value.literal_null:
        if predicate.op is CompOp.IS:
            innermost_condition = f"{quote_identifier(terminal_field)} IS NULL"
        else:
            innermost_condition = f"{quote_identifier(terminal_field)} IS NOT NULL"
        params: list[Any] = []
    else:
        rhs = value_token if policy is not None else "%s"
        innermost_condition = f"{quote_identifier(terminal_field)} {value_op} {rhs}"
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


def _compile_poly_path_check(
    predicate: PolyPathCheck,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
    policy: _PolicyCtx | None = None,
) -> tuple[str, list[Any]]:
    """Compile a PolyPathCheck (#1448): type-guard AND uuid ``IN (SELECT …)``.

    Param mode::

        "target_type" = %s AND "target_id" IN (SELECT "id" FROM <target> WHERE <sub>)

    Policy mode inlines the discriminator literal and emits the sub in policy
    form. If the sub isn't policy-expressible the recursive call raises
    ``ValueError`` → the verb degrades to the app layer via the #1447 path
    (``build_rls_scope_policy_ddl``). ``target_id`` is a real ``uuid`` column,
    so there is no cast anywhere.
    """
    target_table = _qualify_table(predicate.target_entity, schema)
    # #1449/#1448: in PARAM mode (app-layer list/read) TABLE-qualify the poly
    # columns so a same-named column on an FK-display LEFT JOIN target can't make
    # the reference ambiguous (target_type/target_id are common poly column names).
    # Policy mode (RLS USING/WITH CHECK) has no joins → bare, byte-for-byte as before.
    if predicate.field and policy is None and entity_name:
        prefix = f"{_qualify_table(entity_name, None)}."
        type_col = f"{prefix}{quote_identifier(predicate.type_field)}"
        id_col = f"{prefix}{quote_identifier(predicate.id_field)}"
    else:
        type_col = quote_identifier(predicate.type_field)
        id_col = quote_identifier(predicate.id_field)

    sub_sql, sub_params = _compile_predicate_impl(
        predicate.sub, predicate.target_entity, fk_graph, schema=schema, policy=policy
    )
    sub_where = sub_sql if sub_sql else "true"

    if policy is not None:
        type_guard = f"{type_col} = {_inline_sql_literal(predicate.type_value)}"
        sql = f'{type_guard} AND {id_col} IN (SELECT "id" FROM {target_table} WHERE {sub_where})'
        return sql, []

    type_guard = f"{type_col} = %s"
    sql = f'{type_guard} AND {id_col} IN (SELECT "id" FROM {target_table} WHERE {sub_where})'
    params: list[Any] = [predicate.type_value, *sub_params]
    return sql, params


def _compile_path_check(
    predicate: PathCheck,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
    policy: _PolicyCtx | None = None,
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

    In policy mode the structure is unchanged; only the terminal value token
    differs (an inlined literal or a ``current_setting(...)::<type>`` GUC read).
    """
    root_fk_field, root_target_table, where_body, params = _path_check_subquery(
        predicate, entity_name, fk_graph, schema=schema, policy=policy
    )
    inner_sql = f'SELECT "id" FROM {root_target_table} WHERE {where_body}'
    # #1449: in PARAM mode (the app-layer list/read query) TABLE-qualify the outer
    # root FK column with the source entity table so it can't collide with a same-named
    # column on an FK-display LEFT JOIN target — e.g. a list region that joins
    # `Manuscript` for display, which also carries an `ingestion_batch` column, makes
    # bare `"ingestion_batch"` ambiguous. TABLE-, not SCHEMA-qualified (schema=None):
    # the ref must match the search_path-resolved FROM table, never a tenant-schema
    # prefix (#1386). Policy mode (RLS USING/WITH CHECK) has no joins → left unqualified
    # (byte-for-byte unchanged). Empty entity_name (legacy callers) → bare column,
    # mirroring `_qualify_column`.
    outer_col = (
        f"{_qualify_table(entity_name, None)}.{quote_identifier(root_fk_field)}"
        if entity_name and policy is None
        else quote_identifier(root_fk_field)
    )
    return f"{outer_col} IN ({inner_sql})", params


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


def compile_poly_path_check_probe(
    predicate: PolyPathCheck,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    schema: str | None = None,
) -> tuple[str, list[Any]]:
    """Compile a PolyPathCheck into a create-scope probe expression (#1455).

    At create time the poly row doesn't exist yet — its discriminator + id come
    from the payload. The discriminator (``{field}_type``) is checked in pure
    Python by the walker; this probe handles the **sub**: does the target row the
    payload's ``{field}_id`` points at satisfy the sub-predicate? It matches the
    payload id against the target's ``id`` (the type-coercion-safe shape, like
    :func:`compile_path_check_probe`)::

        EXISTS (SELECT 1 FROM "Cohort" WHERE "id" = %s AND ("uploaded_by" = %s))

    ``params[0]`` is a :class:`PayloadFieldRef` for ``{field}_id``; the rest are
    the sub-predicate's value markers (``CurrentUserRef`` / ``UserAttrRef`` /
    literals), in order.
    """
    target_table = _qualify_table(predicate.target_entity, schema)
    sub_sql, sub_params = _compile_predicate_impl(
        predicate.sub, predicate.target_entity, fk_graph, schema=schema
    )
    sub_where = sub_sql if sub_sql else "true"
    sql = f'EXISTS (SELECT 1 FROM {target_table} WHERE "id" = %s AND ({sub_where}))'
    return sql, [PayloadFieldRef(predicate.id_field), *sub_params]


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


def _exists_binding_pg_type(
    predicate: ExistsCheck,
    junction_field: str,
    policy: _PolicyCtx,
) -> str:
    """Resolve the GUC cast type for an ExistsCheck binding in policy mode.

    The binding compares ``junction_field`` (a column on the junction
    ``target_entity``) to a GUC value, so the cast type is the junction
    column's pg type. Raises ``ValueError`` (via the resolver) if unresolvable.
    """
    return policy.types(predicate.target_entity, junction_field)


def _compile_exists_check(
    predicate: ExistsCheck,
    entity_name: str,
    fk_graph: FKGraph | None = None,
    *,
    schema: str | None = None,
    payload_mode: bool = False,
    policy: _PolicyCtx | None = None,
) -> tuple[str, list[Any]]:
    """Compile an ExistsCheck to an [NOT] EXISTS (SELECT 1 FROM …) expression.

    ``payload_mode`` (#1311): when True, bindings whose target is an entity
    column or ``id`` resolve to a :class:`PayloadFieldRef` placeholder rather
    than a ``"<entity>"."<col>"`` reference. This is the create-scope probe
    form — at create time the root row does not exist, so entity-side values
    come from the incoming payload. ``current_user`` / ``current_user.<attr>``
    / ``null`` targets are unaffected.

    ``policy`` (Phase C): policy-body mode. ``current_user`` /
    ``current_user.<attr>`` bindings emit a ``current_setting(...)::<type>`` GUC
    read instead of ``%s`` + marker; the cast type is the junction column's
    pg type. Mutually exclusive with ``payload_mode``. Dotted junction-field
    bindings are not yet supported in policy mode (raise ``ValueError``).
    """
    target = _qualify_table(predicate.target_entity, schema)
    conditions: list[str] = []
    params: list[Any] = []

    for binding in predicate.bindings:
        is_dotted = "." in binding.junction_field
        jf = quote_identifier(binding.junction_field) if not is_dotted else ""
        op = binding.operator  # "=" or "!="

        target_val = binding.target

        if policy is not None and is_dotted:
            raise ValueError(
                "policy mode does not support dotted junction-field bindings "
                f"('{binding.junction_field}') yet"
            )

        # Resolve right-hand value first — shared between dotted and flat paths.
        value_sql: str | None = None
        extra_params: list[Any] = []
        if target_val == "current_user":
            if policy is not None:
                value_sql = _guc_read(
                    "id", _exists_binding_pg_type(predicate, binding.junction_field, policy)
                )
            else:
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
            if policy is not None:
                value_sql = _guc_read(
                    attr, _exists_binding_pg_type(predicate, binding.junction_field, policy)
                )
            else:
                value_sql = "%s"
                extra_params.append(UserAttrRef(attr))
        elif payload_mode:
            # Entity column referenced from a not-yet-existent root row →
            # bind to the create payload's value (#1311).
            value_sql = "%s"
            extra_params.append(PayloadFieldRef(target_val))
        elif policy is not None:
            # Policy mode (Phase C): the EXISTS subquery body is standalone DDL,
            # so the root entity is NOT in scope — a `"<entity>"."<col>"`
            # reference would resolve wrongly / error at policy-eval time. Fail
            # loud at generation time (mirrors the dotted-junction guard above),
            # caught by _apply_rls_policies' loud halt rather than emitting a
            # broken policy. (Param mode below is correct — the route handler
            # supplies the root row — and is intentionally unchanged.)
            raise ValueError(
                "policy mode does not support entity-column ExistsCheck binding "
                f"targets (junction_field='{binding.junction_field}', "
                f"target='{target_val}'); use current_user, current_user.<attr>, "
                "id, null, or a literal"
            )
        else:
            # #1469: the entity-column binding (e.g. `student = student_profile`)
            # must resolve through the same bare⇄`<field>_id` heuristic the rest
            # of the compiler uses (_qualify_column / _compile_path_check). Emitting
            # `target_val` raw only produced valid SQL when the source entity's FK
            # column was named exactly as written; for entities whose column carries
            # the `_id` suffix the EXISTS body referenced a non-existent column → the
            # query raised → fetch_region_items swallowed it fail-closed → the region
            # rendered empty (inconsistent population across source entities). When
            # fk_graph is None this returns target_val unchanged (no behaviour change).
            resolved_target = _resolve_field_on_entity(target_val, entity_name, fk_graph)
            value_sql = f"{quote_identifier(entity_name)}.{quote_identifier(resolved_target)}"

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
    policy: _PolicyCtx | None = None,
) -> tuple[str, list[Any]]:
    """Compile a BoolComposite (AND / OR / NOT) node.

    In param mode (``policy is None``) children are compiled via the public
    :func:`compile_predicate` (unchanged — each gets its own perf span). In
    policy mode children route through :func:`_compile_predicate_impl` with the
    policy context threaded, so the whole tree renders param-free.
    """

    def _child(child: ScopePredicate) -> tuple[str, list[Any]]:
        if policy is None:
            return compile_predicate(child, entity_name, fk_graph, schema=schema)
        return _compile_predicate_impl(child, entity_name, fk_graph, schema=schema, policy=policy)

    if predicate.op is BoolOp.NOT:
        assert len(predicate.children) == 1
        child_sql, child_params = _child(predicate.children[0])
        return f"NOT ({child_sql})", child_params

    joiner = " AND " if predicate.op is BoolOp.AND else " OR "
    parts: list[str] = []
    all_params: list[Any] = []
    for child in predicate.children:
        child_sql, child_params = _child(child)
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
    policy: _PolicyCtx | None = None,
) -> tuple[str, list[Any]]:
    match predicate:
        case Tautology():
            # Policy bodies need a self-contained boolean; param mode keeps the
            # empty fragment (callers omit the WHERE).
            return ("true", []) if policy is not None else ("", [])

        case Contradiction():
            return ("false", []) if policy is not None else ("FALSE", [])

        case ColumnCheck():
            return _compile_column_check(
                predicate,
                entity_name=entity_name,
                schema=schema,
                fk_graph=fk_graph,
                policy=policy,
            )

        case ColumnRefCheck():
            # Column-vs-column — param-free in both modes (not used by RBAC).
            return _compile_column_ref_check(
                predicate, entity_name=entity_name, schema=schema, fk_graph=fk_graph
            )

        case UserAttrCheck():
            return _compile_user_attr_check(
                predicate,
                entity_name=entity_name,
                schema=schema,
                fk_graph=fk_graph,
                policy=policy,
            )

        case PathCheck():
            return _compile_path_check(
                predicate, entity_name, fk_graph, schema=schema, policy=policy
            )

        case ExistsCheck():
            return _compile_exists_check(
                predicate, entity_name, fk_graph, schema=schema, policy=policy
            )

        case PolyPathCheck():
            return _compile_poly_path_check(
                predicate, entity_name, fk_graph, schema=schema, policy=policy
            )

        case BoolComposite():
            return _compile_bool_composite(
                predicate, entity_name, fk_graph, schema=schema, policy=policy
            )

        case _:
            raise TypeError(f"Unknown predicate type: {type(predicate)!r}")


# ---------------------------------------------------------------------------
# Policy-body public API (Phase C)
# ---------------------------------------------------------------------------


def compile_predicate_policy(
    predicate: ScopePredicate,
    entity_name: str,
    fk_graph: FKGraph,
    *,
    entity_types: EntityTypeResolver,
    schema: str | None = None,
) -> str:
    """Compile a :class:`ScopePredicate` to a param-free RLS policy-body fragment.

    Same algebra and SQL shapes as :func:`compile_predicate`, but every value
    token is self-contained: ``current_user`` →
    ``current_setting('dazzle.user_id', true)::<col-type>``, ``current_user.<a>``
    → ``current_setting('dazzle.user_<a>', true)::<col-type>``, literals are
    inlined via :func:`_inline_sql_literal`. ``Tautology`` → ``"true"``,
    ``Contradiction`` → ``"false"``.

    Args:
        predicate: The predicate tree to compile.
        entity_name: The root entity being filtered.
        fk_graph: The FK graph (PathCheck / ExistsCheck path resolution).
        entity_types: A ``(entity, field) -> pg_type_name`` resolver for GUC
            casts (see :func:`build_entity_type_resolver`). Must raise when a
            type can't be resolved — propagated so policy generation fails loud.
        schema: Optional schema name (subquery table-qualification), as in
            :func:`compile_predicate`.

    Returns:
        A self-contained SQL WHERE fragment (no leading ``WHERE``, no ``%s``,
        no bind params) suitable for an RLS ``CREATE POLICY`` body.

    Raises:
        ValueError: If a needed GUC cast type can't be resolved.
    """
    ctx = _PolicyCtx(types=entity_types)
    sql, params = _compile_predicate_impl(
        predicate, entity_name, fk_graph, schema=schema, policy=ctx
    )
    # Always-on guard (NOT `assert` — stripped under -O/-OO). A future compiler
    # bug emitting %s/params in policy mode would otherwise silently produce a
    # broken policy body (literal "%s" → Postgres compares against the string
    # "%s" → silent total-deny, very hard to debug).
    if params:
        raise AssertionError(
            f"policy mode produced bind params (predicate compiler bug): {params!r}"
        )
    return sql


# ---------------------------------------------------------------------------
# current_user attribute collection (Phase C)
# ---------------------------------------------------------------------------


def collect_user_attr_refs(predicate: ScopePredicate) -> set[str]:
    """Return every ``current_user.<attr>`` name referenced in *predicate*.

    Walks the predicate tree (mirroring ``scope_create_eval._walk``) collecting:

    - ``ColumnCheck`` / ``PathCheck`` value refs: ``current_user`` → ``"id"``,
      ``current_user.<attr>`` → ``<attr>``.
    - ``UserAttrCheck``: its ``user_attr``.
    - ``ExistsCheck`` bindings: ``current_user`` → ``"id"``,
      ``current_user.<attr>`` → ``<attr>``.

    The union of these across all of an app's scope rules is the set of
    ``dazzle.user_<attr>`` GUCs the runtime must set per request (Phase C
    Task 3).
    """
    refs: set[str] = set()
    _collect_user_attr_refs(predicate, refs)
    return refs


def _value_ref_user_attr(value: ValueRef) -> str | None:
    """The ``current_user`` attr name a value ref carries, or ``None``."""
    if value.current_user:
        return "id"
    if value.user_attr is not None:
        return value.user_attr
    return None


def _collect_user_attr_refs(predicate: ScopePredicate, refs: set[str]) -> None:
    match predicate:
        case Tautology() | Contradiction() | ColumnRefCheck():
            return
        case ColumnCheck() | PathCheck():
            attr = _value_ref_user_attr(predicate.value)
            if attr is not None:
                refs.add(attr)
        case UserAttrCheck():
            refs.add(predicate.user_attr)
        case ExistsCheck():
            for binding in predicate.bindings:
                target = binding.target
                if target == "current_user":
                    refs.add("id")
                elif target.startswith("current_user."):
                    refs.add(target[len("current_user.") :])
        case PolyPathCheck():
            # #1448: the user-attr refs live in the sub-predicate (rooted on the
            # poly target). Recurse so shared-schema RLS registers the GUCs.
            _collect_user_attr_refs(predicate.sub, refs)
        case BoolComposite():
            for child in predicate.children:
                _collect_user_attr_refs(child, refs)
        case _:
            raise TypeError(f"Unknown predicate type: {type(predicate)!r}")
