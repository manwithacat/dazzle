"""#1665: computed aggregates accept where — leftover unfiltered still parses."""

from __future__ import annotations

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.expression_lang.parser import parse_expr
from dazzle.core.ir.expressions import FuncCall
from dazzle.http.converters.entity_converter import _convert_unified_expr_to_computed
from dazzle.http.runtime.computed_evaluator import evaluate_expression


def test_parse_sum_where_skips_failed() -> None:
    expr = parse_expr('sum(attempts.amount where status == "succeeded")')
    assert isinstance(expr, FuncCall)
    assert expr.where is not None
    spec = _convert_unified_expr_to_computed(expr)
    related = {
        "attempts": [
            {"amount": 10, "status": "succeeded"},
            {"amount": 99, "status": "failed"},
            {"amount": 5, "status": "succeeded"},
        ]
    }
    assert evaluate_expression(spec, {}, related) == 15.0


def test_leftover_unfiltered_sum_unchanged() -> None:
    expr = parse_expr("sum(line_items.amount)")
    assert isinstance(expr, FuncCall)
    assert expr.where is None
    spec = _convert_unified_expr_to_computed(expr)
    related = {"line_items": [{"amount": 3}, {"amount": 4}]}
    assert evaluate_expression(spec, {}, related) == 7.0


def test_dsl_computed_where_round_trip() -> None:
    src = """module ops
app t "T"
entity Invoice "Invoice":
  id: uuid pk
  amount: decimal(15,2)
  remainder: computed amount - sum(attempts.amount where status == "succeeded")
"""
    fields = parse_dsl(src, "t.dsl")[5].entities[0].computed_fields
    assert fields[0].name == "remainder"
    assert fields[0].computed_expr is not None


def test_uncompilable_where_fails_closed() -> None:
    expr = parse_expr("sum(attempts.amount where amount > 0)")
    spec = _convert_unified_expr_to_computed(expr)
    related = {"attempts": [{"amount": 10, "status": "failed"}]}
    assert evaluate_expression(spec, {}, related) is None
