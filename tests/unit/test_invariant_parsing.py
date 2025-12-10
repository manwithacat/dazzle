"""Tests for entity invariant parsing."""

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl


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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert len(fragment.entities) == 1
        entity = fragment.entities[0]
        assert len(entity.invariants) == 1

        inv = entity.invariants[0]
        assert isinstance(inv.expression, ir.ComparisonExpr)
        assert inv.expression.operator == ir.InvariantComparisonOperator.GT
        assert isinstance(inv.expression.left, ir.InvariantFieldRef)
        assert inv.expression.left.path == ["quantity"]
        assert isinstance(inv.expression.right, ir.InvariantLiteral)
        assert inv.expression.right.value == 0

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        assert len(entity.invariants) == 1

        inv = entity.invariants[0]
        assert isinstance(inv.expression, ir.ComparisonExpr)
        assert inv.expression.operator == ir.InvariantComparisonOperator.EQ
        assert isinstance(inv.expression.right, ir.InvariantLiteral)
        assert inv.expression.right.value == "active"

    def test_comparison_operators(self) -> None:
        """Test parsing all comparison operators."""
        operators = [
            ("==", ir.InvariantComparisonOperator.EQ),
            ("!=", ir.InvariantComparisonOperator.NE),
            (">", ir.InvariantComparisonOperator.GT),
            ("<", ir.InvariantComparisonOperator.LT),
            (">=", ir.InvariantComparisonOperator.GE),
            ("<=", ir.InvariantComparisonOperator.LE),
        ]

        for dsl_op, ir_op in operators:
            dsl = f"""
module test
app test "Test"

entity Item "Item":
  id: uuid pk
  value: int required

  invariant: value {dsl_op} 10
"""
            _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
            entity = fragment.entities[0]
            inv = entity.invariants[0]
            assert isinstance(inv.expression, ir.ComparisonExpr), f"Failed for {dsl_op}"
            assert inv.expression.operator == ir_op, f"Failed for {dsl_op}"


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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        assert len(entity.invariants) == 1

        inv = entity.invariants[0]
        assert isinstance(inv.expression, ir.ComparisonExpr)
        assert isinstance(inv.expression.left, ir.InvariantFieldRef)
        assert inv.expression.left.path == ["end_date"]
        assert isinstance(inv.expression.right, ir.InvariantFieldRef)
        assert inv.expression.right.path == ["start_date"]


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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert isinstance(inv.expression, ir.ComparisonExpr)
        assert isinstance(inv.expression.right, ir.DurationExpr)
        assert inv.expression.right.value == 14
        assert inv.expression.right.unit == ir.DurationUnit.DAYS

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert isinstance(inv.expression.right, ir.DurationExpr)
        assert inv.expression.right.value == 2
        assert inv.expression.right.unit == ir.DurationUnit.HOURS

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert isinstance(inv.expression.right, ir.DurationExpr)
        assert inv.expression.right.value == 30
        assert inv.expression.right.unit == ir.DurationUnit.MINUTES


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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert isinstance(inv.expression, ir.LogicalExpr)
        assert inv.expression.operator == ir.InvariantLogicalOperator.AND
        assert isinstance(inv.expression.left, ir.ComparisonExpr)
        assert isinstance(inv.expression.right, ir.ComparisonExpr)

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert isinstance(inv.expression, ir.LogicalExpr)
        assert inv.expression.operator == ir.InvariantLogicalOperator.OR

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert isinstance(inv.expression, ir.NotExpr)
        assert isinstance(inv.expression.operand, ir.InvariantFieldRef)
        assert inv.expression.operand.path == ["is_deleted"]


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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert isinstance(inv.expression, ir.LogicalExpr)
        assert inv.expression.operator == ir.InvariantLogicalOperator.OR
        # Right side should be the AND expression
        assert isinstance(inv.expression.right, ir.LogicalExpr)
        assert inv.expression.right.operator == ir.InvariantLogicalOperator.AND

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert isinstance(inv.expression, ir.LogicalExpr)
        assert inv.expression.operator == ir.InvariantLogicalOperator.AND
        # Left side should be the OR expression
        assert isinstance(inv.expression.left, ir.LogicalExpr)
        assert inv.expression.left.operator == ir.InvariantLogicalOperator.OR

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert isinstance(inv.expression, ir.ComparisonExpr)
        assert isinstance(inv.expression.right, ir.InvariantLiteral)
        assert inv.expression.right.value is True

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        inv = entity.invariants[0]

        assert isinstance(inv.expression, ir.ComparisonExpr)
        assert inv.expression.operator == ir.InvariantComparisonOperator.NE
        assert isinstance(inv.expression.right, ir.InvariantLiteral)
        assert inv.expression.right.value == "deleted"
