"""Compile L3 :class:`AggregateExpr` IR to safe parameterised SQL (#1152).

Closes the L3 leg of the AggregateRef refactor (ADR-0024 / brainstorm
``dev_docs/2026-05-19-aggregate-ref-ir-brainstorm.md``). Where the
parser produces nested expression IR for shapes like
``avg(MarkingResult.score::float / nullif(MarkingResult.max_score, 0))``,
this module turns that IR into ``(sql_fragment, params)`` ready to be
embedded inside an aggregate measure SELECT clause.

Safety contract:

- Every column identifier is wrapped in
  :func:`dazzle.http.runtime.query_builder.quote_identifier`. The
  identifier validator catches injection attempts before the column
  ever reaches the cursor.
- Every numeric literal is rendered as a placeholder and bound as a
  query parameter. The IR cannot represent string literals; the
  compiler does not accept them either.
- The cast target and function name are taken from closed Literal-typed
  enums on the IR. The compiler maps each whitelist member to a fixed
  SQL emission — there is no path where caller-controlled text reaches
  the SQL string verbatim.
- Binary operators are likewise drawn from a closed whitelist and
  rendered as fixed punctuation.

The compiler always returns the expression wrapped in parentheses so
the caller can splice it into a measure clause (``AVG(<expr>)``)
without re-considering operator precedence.
"""

from __future__ import annotations

from typing import Any

from dazzle.core.ir import AggregateExpr
from dazzle.http.runtime.query_builder import quote_identifier, validate_sql_identifier

# Each cast target maps to a fixed Postgres type name. The IR validator
# rejects anything outside this set; this dict is the runtime ground
# truth for what SQL gets emitted.
_CAST_SQL: dict[str, str] = {
    "float": "double precision",
    "int": "integer",
    "numeric": "numeric",
    "text": "text",
}

# Each whitelisted function maps to a fixed SQL function name.
_FUNCTION_SQL: dict[str, str] = {
    "nullif": "NULLIF",
    "coalesce": "COALESCE",
    "abs": "ABS",
}

# Whitelisted binary operators rendered verbatim.
_BINARY_OP_SQL: frozenset[str] = frozenset({"+", "-", "*", "/"})


def compile_aggregate_expression(
    expr: AggregateExpr,
    *,
    placeholder: str = "%s",
    table_alias: str | None = None,
) -> tuple[str, list[Any]]:
    """Compile an :class:`AggregateExpr` to ``(sql, params)``.

    Args:
        expr: The expression IR. Typically the ``expression`` field on
            an :class:`AggregateRef`.
        placeholder: Parameter placeholder style. Mirrors the
            ``QueryBuilder`` convention — ``%s`` for psycopg, ``?`` for
            SQLite. Defaults to psycopg style since the production
            runtime is PostgreSQL-only (ADR-0008).
        table_alias: Optional unquoted table name to prefix bare column
            refs (e.g. ``MarkingResult``). When set, column refs that
            do not carry an explicit ``column_entity`` are qualified
            as ``<alias>.<col>``. When ``None``, column refs are
            unqualified — appropriate when the SQL surrounding the
            measure clause already has a single source table in scope.

    Returns:
        ``(sql_fragment, params)``. ``sql_fragment`` is always wrapped
        in outer parentheses so the caller can interpolate it into
        ``<func>(<sql_fragment>)`` regardless of internal precedence.
        ``params`` is the ordered list of placeholder bindings.
    """
    from dazzle.perf.tracer import dazzle_span

    with dazzle_span(
        "aggregate.expression.compile",
        placeholder=placeholder,
        table_alias=table_alias,
        expr=expr,
    ):
        params: list[Any] = []
        sql = _compile(expr, params, placeholder, table_alias)
        return f"({sql})", params


def _compile(
    expr: AggregateExpr,
    params: list[Any],
    placeholder: str,
    table_alias: str | None,
) -> str:
    if expr.is_column_ref:
        return _compile_column_ref(expr, table_alias)
    if expr.is_number_literal:
        params.append(expr.number_literal)
        return placeholder
    if expr.is_cast:
        assert expr.cast_operand is not None
        assert expr.cast_target is not None
        inner = _compile(expr.cast_operand, params, placeholder, table_alias)
        target_sql = _CAST_SQL[expr.cast_target]
        return f"({inner})::{target_sql}"
    if expr.is_binary_op:
        assert expr.binary_left is not None
        assert expr.binary_right is not None
        assert expr.binary_op is not None
        if expr.binary_op not in _BINARY_OP_SQL:
            raise ValueError(f"unsupported binary operator {expr.binary_op!r}")
        left = _compile(expr.binary_left, params, placeholder, table_alias)
        right = _compile(expr.binary_right, params, placeholder, table_alias)
        return f"({left}) {expr.binary_op} ({right})"
    if expr.is_function_call:
        assert expr.function_name is not None
        assert expr.function_args is not None
        fn_sql = _FUNCTION_SQL[expr.function_name]
        compiled_args = [
            _compile(arg, params, placeholder, table_alias) for arg in expr.function_args
        ]
        return f"{fn_sql}({', '.join(compiled_args)})"
    raise ValueError(f"AggregateExpr has no populated variant; cannot compile: {expr!r}")


def _compile_column_ref(expr: AggregateExpr, table_alias: str | None) -> str:
    assert expr.column_name is not None
    validate_sql_identifier(expr.column_name, "aggregate-expression column")
    col_sql = quote_identifier(expr.column_name)
    if expr.column_entity is not None:
        # Cross-entity prefix. At runtime the aggregate is dispatched to
        # the entity's own repository, so the table is identified by
        # bare name (the prefix is verified consistent at parse time —
        # all column refs share one entity). Qualify the column with
        # the entity name so a future multi-table FROM clause can still
        # disambiguate.
        validate_sql_identifier(expr.column_entity, "aggregate-expression entity prefix")
        return f"{quote_identifier(expr.column_entity)}.{col_sql}"
    if table_alias is not None:
        validate_sql_identifier(table_alias, "aggregate-expression table alias")
        return f"{quote_identifier(table_alias)}.{col_sql}"
    return col_sql
