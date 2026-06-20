"""L3 aggregate-expression tests (#1152).

Pins the three layers that compose the L3 leg:

1. ``AggregateExpr`` IR — variant validators, exactly-one rule, arity
   checks, dotted-column rejection.
2. Parser — extension of ``parse_aggregate_ref`` to populate
   ``AggregateRef.expression`` when operators / casts / function calls
   appear, with single-entity-prefix invariant.
3. Compiler — ``compile_aggregate_expression`` emits parameterised SQL
   with quoted identifiers; ``build_aggregate_sql`` threads inner
   measure params ahead of WHERE params.

Includes the AegisMark canonical lens
(``avg(MarkingResult.score::float / nullif(MarkingResult.max_score, 0))``)
end-to-end through parser + compiler + build_aggregate_sql.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from dazzle.core.dsl_parser_impl import Parser
from dazzle.core.errors import ParseError
from dazzle.core.ir import AggregateExpr, AggregateRef
from dazzle.core.lexer import tokenize
from dazzle.http.runtime.aggregate import build_aggregate_sql
from dazzle.http.runtime.aggregate_expression import compile_aggregate_expression


def _parse(src: str) -> AggregateRef:
    tokens = tokenize(src + "\n", Path("test.dsl"))
    return Parser(tokens, Path("test.dsl")).parse_aggregate_ref()


# ─────────────── IR — variant validation ───────────────


def test_expr_column_ref_bare() -> None:
    e = AggregateExpr(column_name="score")
    assert e.is_column_ref
    assert not e.is_binary_op


def test_expr_column_ref_with_entity() -> None:
    e = AggregateExpr(column_entity="MarkingResult", column_name="score")
    assert e.is_column_ref
    assert e.column_entity == "MarkingResult"


def test_expr_column_dotted_rejected() -> None:
    with pytest.raises(ValidationError):
        AggregateExpr(column_name="a.b")


def test_expr_no_variant_rejected() -> None:
    with pytest.raises(ValidationError):
        AggregateExpr()


def test_expr_multiple_variants_rejected() -> None:
    with pytest.raises(ValidationError):
        AggregateExpr(column_name="x", number_literal=0)


def test_expr_cast_requires_operand() -> None:
    with pytest.raises(ValidationError):
        AggregateExpr(cast_target="float")


def test_expr_binary_requires_both_sides() -> None:
    with pytest.raises(ValidationError):
        AggregateExpr(binary_op="/", binary_left=AggregateExpr(column_name="a"))


def test_expr_nullif_arity_enforced() -> None:
    with pytest.raises(ValidationError):
        AggregateExpr(
            function_name="nullif",
            function_args=(AggregateExpr(column_name="a"),),
        )


def test_expr_coalesce_variadic_one_arg_ok() -> None:
    e = AggregateExpr(
        function_name="coalesce",
        function_args=(AggregateExpr(column_name="a"),),
    )
    assert e.is_function_call


def test_expr_abs_arity_one() -> None:
    with pytest.raises(ValidationError):
        AggregateExpr(
            function_name="abs",
            function_args=(
                AggregateExpr(column_name="a"),
                AggregateExpr(column_name="b"),
            ),
        )


# ─────────────── IR — AggregateRef + expression rules ───────────────


def test_aggregate_ref_with_expression() -> None:
    ref = AggregateRef(
        func="avg",
        expression=AggregateExpr(column_name="score"),
    )
    assert ref.is_expression
    assert ref.column is None


def test_aggregate_ref_count_rejects_expression() -> None:
    with pytest.raises(ValidationError):
        AggregateRef(
            func="count",
            expression=AggregateExpr(column_name="score"),
        )


def test_aggregate_ref_column_xor_expression() -> None:
    with pytest.raises(ValidationError):
        AggregateRef(
            func="avg",
            column="score",
            expression=AggregateExpr(column_name="score"),
        )


def test_aggregate_ref_scalar_requires_one_of_column_expression() -> None:
    with pytest.raises(ValidationError):
        AggregateRef(func="avg")


# ─────────────── Parser ───────────────


def test_parser_legacy_column_still_uses_column_field() -> None:
    """L3 path must not regress the simple column case."""
    r = _parse("avg(score)")
    assert r.column == "score"
    assert r.expression is None


def test_parser_cross_entity_column_still_uses_column_field() -> None:
    r = _parse("avg(MarkingResult.score)")
    assert r.entity == "MarkingResult"
    assert r.column == "score"
    assert r.expression is None


def test_parser_division_becomes_expression() -> None:
    r = _parse("avg(score / max_score)")
    assert r.column is None
    assert r.expression is not None
    assert r.expression.is_binary_op
    assert r.expression.binary_op == "/"


def test_parser_cast_becomes_expression() -> None:
    r = _parse("avg(score::float)")
    assert r.expression is not None
    assert r.expression.is_cast
    assert r.expression.cast_target == "float"


def test_parser_function_call_becomes_expression() -> None:
    r = _parse("avg(nullif(score, 0))")
    assert r.expression is not None
    assert r.expression.is_function_call
    assert r.expression.function_name == "nullif"


def test_parser_aegismark_canonical() -> None:
    r = _parse("avg(MarkingResult.score::float / nullif(MarkingResult.max_score, 0))")
    assert r.entity == "MarkingResult"
    assert r.expression is not None
    assert r.expression.is_binary_op
    assert r.expression.binary_op == "/"


def test_parser_mixed_entity_prefix_rejected() -> None:
    """All column refs inside an expression must share one entity prefix."""
    with pytest.raises(ParseError):
        _parse("avg(MarkingResult.score / Other.max_score)")


def test_parser_bare_plus_prefixed_rejected() -> None:
    with pytest.raises(ParseError):
        _parse("avg(MarkingResult.score / max_score)")


def test_parser_unknown_function_rejected() -> None:
    with pytest.raises(ParseError):
        _parse("avg(crash(score))")


def test_parser_unknown_cast_target_rejected() -> None:
    with pytest.raises(ParseError):
        _parse("avg(score::bigint)")


def test_parser_precedence_multiplicative_binds_tighter() -> None:
    r = _parse("avg(a + b * c)")
    assert r.expression is not None
    # Top-level should be `+`, not `*`.
    assert r.expression.binary_op == "+"
    assert r.expression.binary_right is not None
    assert r.expression.binary_right.binary_op == "*"


def test_parser_parenthesised_overrides_precedence() -> None:
    r = _parse("avg((a + b) * c)")
    assert r.expression is not None
    assert r.expression.binary_op == "*"


def test_parser_negative_literal() -> None:
    r = _parse("avg(score - -1)")
    assert r.expression is not None
    assert r.expression.binary_op == "-"
    assert r.expression.binary_right is not None
    assert r.expression.binary_right.number_literal == -1


def test_parser_expression_with_where() -> None:
    r = _parse("avg(score / max_score where graded = true)")
    assert r.expression is not None
    assert r.where is not None


# ─────────────── Compiler safety ───────────────


def test_compile_column_ref_quotes_identifier() -> None:
    sql, params = compile_aggregate_expression(AggregateExpr(column_name="score"))
    assert sql == '("score")'
    assert params == []


def test_compile_column_ref_with_alias() -> None:
    sql, params = compile_aggregate_expression(
        AggregateExpr(column_name="score"),
        table_alias="Task",
    )
    assert sql == '("Task"."score")'
    assert params == []


def test_compile_number_literal_bound() -> None:
    sql, params = compile_aggregate_expression(AggregateExpr(number_literal=42))
    assert sql == "(%s)"
    assert params == [42]


def test_compile_cast_target_is_whitelisted() -> None:
    sql, params = compile_aggregate_expression(
        AggregateExpr(
            cast_target="float",
            cast_operand=AggregateExpr(column_name="score"),
        )
    )
    assert "double precision" in sql
    assert "::" in sql


def test_compile_function_call_uppercases() -> None:
    sql, params = compile_aggregate_expression(
        AggregateExpr(
            function_name="nullif",
            function_args=(
                AggregateExpr(column_name="max_score"),
                AggregateExpr(number_literal=0),
            ),
        )
    )
    assert "NULLIF(" in sql
    assert params == [0]


def test_compile_rejects_invalid_column_identifier() -> None:
    """An IR-bypassing caller (e.g. test code) gets blocked at compile time."""
    with pytest.raises(ValueError, match="Invalid SQL"):
        compile_aggregate_expression(AggregateExpr.model_construct(column_name="x; DROP TABLE t"))


def test_compile_full_canonical_example() -> None:
    r = _parse("avg(MarkingResult.score::float / nullif(MarkingResult.max_score, 0))")
    sql, params = compile_aggregate_expression(r.expression, placeholder="%s", table_alias=r.entity)
    assert '"MarkingResult"."score"' in sql
    assert '"MarkingResult"."max_score"' in sql
    assert "NULLIF" in sql
    assert "double precision" in sql
    assert params == [0]


# ─────────────── build_aggregate_sql integration ───────────────


def test_build_aggregate_sql_with_measure_expression() -> None:
    expr_sql, expr_params = compile_aggregate_expression(
        AggregateExpr(
            binary_op="/",
            binary_left=AggregateExpr(column_name="score"),
            binary_right=AggregateExpr(
                function_name="nullif",
                function_args=(
                    AggregateExpr(column_name="max_score"),
                    AggregateExpr(number_literal=0),
                ),
            ),
        )
    )
    sql, params = build_aggregate_sql(
        table_name="marking_result",
        placeholder_style="%s",
        dimensions=[],
        measures={"primary": "avg"},
        filters={"student_id": "abc"},
        measure_expressions={"primary": (expr_sql, expr_params)},
    )
    # Measure params come before WHERE params in the final list.
    assert params == [0, "abc"]
    assert "AVG(" in sql
    assert '"primary"' in sql
    assert "WHERE" in sql


def test_build_aggregate_sql_legacy_path_still_works() -> None:
    """measure_expressions=None should leave the legacy path untouched."""
    sql, params = build_aggregate_sql(
        table_name="task",
        placeholder_style="%s",
        dimensions=[],
        measures={"primary": "avg:score"},
        filters=None,
    )
    assert 'AVG("score")' in sql
    assert params == []
