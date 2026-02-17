"""Tests for typed expression defaults on entity fields.

Covers:
- DSL parsing of field expression defaults (= expr)
- FieldSpec.default_expr population
- Expression defaults don't break simple literal defaults
- End-to-end: parse DSL → evaluate expression
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.expression_lang import evaluate
from dazzle.core.ir.expressions import BinaryExpr, BinaryOp, FieldRef, FuncCall

_TEST_FILE = Path("test.dsl")


def _parse(dsl: str):
    """Parse DSL and return the fragment."""
    _, _, _, _, _, fragment = parse_dsl(dsl, _TEST_FILE)
    return fragment


class TestExpressionDefaultParsing:
    """DSL parser populates default_expr for expression defaults."""

    def test_arithmetic_default(self) -> None:
        dsl = """
module test_mod

entity VATReturn "VAT Return":
  box1: int
  box2: int
  box3: int = box1 + box2
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        box3 = next(f for f in entity.fields if f.name == "box3")
        assert box3.default_expr is not None
        assert box3.default is None
        assert isinstance(box3.default_expr, BinaryExpr)
        assert box3.default_expr.op == BinaryOp.ADD

    def test_function_call_default(self) -> None:
        dsl = """
module test_mod

entity Task "Task":
  a: int
  b: int
  bigger: int = max(a, b)
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        bigger = next(f for f in entity.fields if f.name == "bigger")
        assert bigger.default_expr is not None
        assert isinstance(bigger.default_expr, FuncCall)
        assert bigger.default_expr.name == "max"

    def test_comparison_default(self) -> None:
        dsl = """
module test_mod

entity Task "Task":
  score: int
  passed: bool = score >= 70
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        passed = next(f for f in entity.fields if f.name == "passed")
        assert passed.default_expr is not None
        assert isinstance(passed.default_expr, BinaryExpr)
        assert passed.default_expr.op == BinaryOp.GE

    def test_dotted_field_ref_default(self) -> None:
        dsl = """
module test_mod

entity Invoice "Invoice":
  customer_name: str(200) = customer.name
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        field = next(f for f in entity.fields if f.name == "customer_name")
        assert field.default_expr is not None
        assert isinstance(field.default_expr, FieldRef)
        assert field.default_expr.path == ["customer", "name"]

    def test_simple_literal_default_still_works(self) -> None:
        dsl = """
module test_mod

entity Task "Task":
  status: str(50)=pending
  priority: int=5
  active: bool=true
  name: str(200)="default name"
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]

        status = next(f for f in entity.fields if f.name == "status")
        assert status.default == "pending"
        assert status.default_expr is None

        priority = next(f for f in entity.fields if f.name == "priority")
        assert priority.default == 5
        assert priority.default_expr is None

        active = next(f for f in entity.fields if f.name == "active")
        assert active.default is True
        assert active.default_expr is None

        name = next(f for f in entity.fields if f.name == "name")
        assert name.default == "default name"
        assert name.default_expr is None

    def test_field_with_modifiers_and_expr(self) -> None:
        dsl = """
module test_mod

entity Order "Order":
  subtotal: int
  tax: int
  total: int required = subtotal + tax
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        total = next(f for f in entity.fields if f.name == "total")
        assert total.default_expr is not None
        assert total.is_required


class TestExpressionDefaultEvaluation:
    """End-to-end: parse DSL expression default then evaluate it."""

    def test_evaluate_arithmetic(self) -> None:
        dsl = """
module test_mod

entity VATReturn "VAT Return":
  box1: int
  box2: int
  box3: int = box1 + box2
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        box3 = next(f for f in entity.fields if f.name == "box3")
        assert box3.default_expr is not None

        value = evaluate(box3.default_expr, {"box1": 1500, "box2": 300})
        assert value == 1800

    def test_evaluate_nested_arithmetic(self) -> None:
        dsl = """
module test_mod

entity Order "Order":
  qty: int
  price: int
  total: int = qty * price
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        total = next(f for f in entity.fields if f.name == "total")
        assert total.default_expr is not None

        value = evaluate(total.default_expr, {"qty": 3, "price": 25})
        assert value == 75

    def test_evaluate_function_default(self) -> None:
        dsl = """
module test_mod

entity Score "Score":
  a: int
  b: int
  best: int = max(a, b)
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        best = next(f for f in entity.fields if f.name == "best")
        assert best.default_expr is not None

        value = evaluate(best.default_expr, {"a": 85, "b": 92})
        assert value == 92
