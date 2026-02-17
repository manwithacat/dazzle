"""Tests for entity invariant parsing using unified expression language."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.expressions import (
    BinaryExpr,
    BinaryOp,
    DurationLiteral,
    FieldRef,
    Literal,
    UnaryExpr,
    UnaryOp,
)


def _parse(dsl: str):
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return fragment


class TestSimpleInvariantParsing:
    """Tests for parsing simple invariant expressions."""

    def test_simple_comparison_gt(self) -> None:
        """Test parsing a simple greater-than comparison invariant."""
        dsl = """
module test
app test "Test"

entity Item "Item":
  id: uuid pk
  quantity: int required

  invariant: quantity > 0
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert len(entity.invariants) == 1

        inv = entity.invariants[0]
        assert inv.invariant_expr is not None
        expr = inv.invariant_expr
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.GT
        assert isinstance(expr.left, FieldRef)
        assert expr.left.path == ["quantity"]
        assert isinstance(expr.right, Literal)
        assert expr.right.value == 0

    def test_simple_comparison_eq(self) -> None:
        """Test parsing an equality comparison invariant."""
        dsl = """
module test
app test "Test"

entity Task "Task":
  id: uuid pk
  status: str(50) required

  invariant: status == "active"
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert len(entity.invariants) == 1

        inv = entity.invariants[0]
        assert inv.invariant_expr is not None
        expr = inv.invariant_expr
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.EQ
        assert isinstance(expr.right, Literal)
        assert expr.right.value == "active"

    def test_comparison_operators(self) -> None:
        """Test parsing all comparison operators."""
        operators = [
            ("==", BinaryOp.EQ),
            ("!=", BinaryOp.NE),
            (">", BinaryOp.GT),
            ("<", BinaryOp.LT),
            (">=", BinaryOp.GE),
            ("<=", BinaryOp.LE),
        ]

        for dsl_op, expected_op in operators:
            dsl = f"""
module test
app test "Test"

entity Item "Item":
  id: uuid pk
  value: int required

  invariant: value {dsl_op} 10
"""
            fragment = _parse(dsl)
            entity = fragment.entities[0]
            inv = entity.invariants[0]
            assert inv.invariant_expr is not None, f"Failed for {dsl_op}"
            assert isinstance(inv.invariant_expr, BinaryExpr), f"Failed for {dsl_op}"
            assert inv.invariant_expr.op == expected_op, f"Failed for {dsl_op}"


class TestFieldComparisonParsing:
    """Tests for parsing field-to-field comparison invariants."""

    def test_field_comparison(self) -> None:
        """Test parsing a field-to-field comparison."""
        dsl = """
module test
app test "Test"

entity Event "Event":
  id: uuid pk
  start_date: date required
  end_date: date required

  invariant: end_date > start_date
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert len(entity.invariants) == 1

        inv = entity.invariants[0]
        assert inv.invariant_expr is not None
        expr = inv.invariant_expr
        assert isinstance(expr, BinaryExpr)
        assert isinstance(expr.left, FieldRef)
        assert expr.left.path == ["end_date"]
        assert isinstance(expr.right, FieldRef)
        assert expr.right.path == ["start_date"]


class TestDurationParsing:
    """Tests for parsing duration expressions in invariants."""

    def test_duration_days(self) -> None:
        """Test parsing a duration in days."""
        dsl = """
module test
app test "Test"

entity Task "Task":
  id: uuid pk
  due_date: date required

  invariant: due_date > 14 days
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert inv.invariant_expr is not None
        expr = inv.invariant_expr
        assert isinstance(expr, BinaryExpr)
        assert isinstance(expr.right, DurationLiteral)
        assert expr.right.value == 14
        assert expr.right.unit == "d"

    def test_duration_hours(self) -> None:
        """Test parsing a duration in hours."""
        dsl = """
module test
app test "Test"

entity Reminder "Reminder":
  id: uuid pk
  notify_at: datetime required

  invariant: notify_at > 2 hours
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert inv.invariant_expr is not None
        assert isinstance(inv.invariant_expr, BinaryExpr)
        assert isinstance(inv.invariant_expr.right, DurationLiteral)
        assert inv.invariant_expr.right.value == 2
        assert inv.invariant_expr.right.unit == "h"

    def test_duration_minutes(self) -> None:
        """Test parsing a duration in minutes."""
        dsl = """
module test
app test "Test"

entity Alert "Alert":
  id: uuid pk
  trigger_at: datetime required

  invariant: trigger_at > 30 minutes
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert inv.invariant_expr is not None
        assert isinstance(inv.invariant_expr, BinaryExpr)
        assert isinstance(inv.invariant_expr.right, DurationLiteral)
        assert inv.invariant_expr.right.value == 30
        assert inv.invariant_expr.right.unit == "min"


class TestLogicalOperatorParsing:
    """Tests for parsing logical operator expressions."""

    def test_and_operator(self) -> None:
        """Test parsing AND logical operator."""
        dsl = """
module test
app test "Test"

entity Order "Order":
  id: uuid pk
  quantity: int required
  price: decimal(10,2) required

  invariant: quantity > 0 and price > 0
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert inv.invariant_expr is not None
        expr = inv.invariant_expr
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.AND
        assert isinstance(expr.left, BinaryExpr)
        assert isinstance(expr.right, BinaryExpr)

    def test_or_operator(self) -> None:
        """Test parsing OR logical operator."""
        dsl = """
module test
app test "Test"

entity User "User":
  id: uuid pk
  is_admin: bool required
  is_owner: bool required

  invariant: is_admin or is_owner
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert inv.invariant_expr is not None
        assert isinstance(inv.invariant_expr, BinaryExpr)
        assert inv.invariant_expr.op == BinaryOp.OR

    def test_not_operator(self) -> None:
        """Test parsing NOT logical operator."""
        dsl = """
module test
app test "Test"

entity Record "Record":
  id: uuid pk
  is_deleted: bool required

  invariant: not is_deleted
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert inv.invariant_expr is not None
        assert isinstance(inv.invariant_expr, UnaryExpr)
        assert inv.invariant_expr.op == UnaryOp.NOT
        assert isinstance(inv.invariant_expr.operand, FieldRef)
        assert inv.invariant_expr.operand.path == ["is_deleted"]


class TestComplexInvariantParsing:
    """Tests for parsing complex invariant expressions."""

    def test_and_or_precedence(self) -> None:
        """Test that AND has higher precedence than OR."""
        dsl = """
module test
app test "Test"

entity Item "Item":
  id: uuid pk
  a: bool required
  b: bool required
  c: bool required

  invariant: a or b and c
"""
        # Should parse as: a or (b and c)
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert inv.invariant_expr is not None
        expr = inv.invariant_expr
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.OR
        # Right side should be the AND expression
        assert isinstance(expr.right, BinaryExpr)
        assert expr.right.op == BinaryOp.AND

    def test_parentheses_override_precedence(self) -> None:
        """Test that parentheses override operator precedence."""
        dsl = """
module test
app test "Test"

entity Item "Item":
  id: uuid pk
  a: bool required
  b: bool required
  c: bool required

  invariant: (a or b) and c
"""
        # Should parse as: (a or b) and c
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert inv.invariant_expr is not None
        expr = inv.invariant_expr
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.AND
        # Left side should be the OR expression
        assert isinstance(expr.left, BinaryExpr)
        assert expr.left.op == BinaryOp.OR

    def test_multiple_invariants(self) -> None:
        """Test parsing multiple invariants in one entity."""
        dsl = """
module test
app test "Test"

entity Order "Order":
  id: uuid pk
  quantity: int required
  price: decimal(10,2) required
  discount: decimal(5,2) required

  invariant: quantity > 0
  invariant: price >= 0
  invariant: discount >= 0
  invariant: discount <= price
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert len(entity.invariants) == 4

    def test_boolean_literals(self) -> None:
        """Test parsing boolean literals in invariants."""
        dsl = """
module test
app test "Test"

entity Setting "Setting":
  id: uuid pk
  enabled: bool required

  invariant: enabled == true
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert inv.invariant_expr is not None
        assert isinstance(inv.invariant_expr, BinaryExpr)
        assert isinstance(inv.invariant_expr.right, Literal)
        assert inv.invariant_expr.right.value is True

    def test_string_literal_in_comparison(self) -> None:
        """Test parsing string literal in comparison."""
        dsl = """
module test
app test "Test"

entity Status "Status":
  id: uuid pk
  value: str(50) required

  invariant: value != "deleted"
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert inv.invariant_expr is not None
        assert isinstance(inv.invariant_expr, BinaryExpr)
        assert inv.invariant_expr.op == BinaryOp.NE
        assert isinstance(inv.invariant_expr.right, Literal)
        assert inv.invariant_expr.right.value == "deleted"
