"""Tests for computed field parsing using unified expression language."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.expressions import (
    BinaryExpr,
    BinaryOp,
    FieldRef,
    FuncCall,
    Literal,
)


def _parse(dsl: str):
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return fragment


class TestComputedFieldParsing:
    """Tests for parsing entity computed fields."""

    def test_simple_field_reference(self) -> None:
        """Test parsing a computed field that references another field."""
        dsl = """
module test.core
app test_app "Test App"

entity Invoice "Invoice":
  id: uuid pk
  gross_amount: decimal(10, 2)
  net_amount: computed gross_amount
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]
        assert entity.name == "Invoice"
        assert entity.has_computed_fields

        cf = entity.get_computed_field("net_amount")
        assert cf is not None
        assert cf.name == "net_amount"
        assert cf.computed_expr is not None
        assert isinstance(cf.computed_expr, FieldRef)
        assert cf.computed_expr.path == ["gross_amount"]
        assert cf.dependencies == {"gross_amount"}

    def test_simple_aggregate(self) -> None:
        """Test parsing a simple aggregate function call."""
        dsl = """
module test.core
app test_app "Test App"

entity Order "Order":
  id: uuid pk
  line_items: ref LineItem
  total: computed sum(line_items.amount)

entity LineItem "LineItem":
  id: uuid pk
  amount: decimal(10, 2)
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]
        cf = entity.get_computed_field("total")
        assert cf is not None
        assert cf.computed_expr is not None
        assert isinstance(cf.computed_expr, FuncCall)
        assert cf.computed_expr.name == "sum"
        assert len(cf.computed_expr.args) == 1
        arg = cf.computed_expr.args[0]
        assert isinstance(arg, FieldRef)
        assert arg.path == ["line_items", "amount"]

    def test_count_aggregate(self) -> None:
        """Test parsing count aggregate function."""
        dsl = """
module test.core
app test_app "Test App"

entity Order "Order":
  id: uuid pk
  items: ref Item
  item_count: computed count(items)

entity Item "Item":
  id: uuid pk
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]
        cf = entity.get_computed_field("item_count")
        assert cf is not None
        assert cf.computed_expr is not None
        assert isinstance(cf.computed_expr, FuncCall)
        assert cf.computed_expr.name == "count"

    def test_date_aggregates(self) -> None:
        """Test parsing days_since and days_until aggregate functions."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  due_date: date
  created_at: date
  days_until_due: computed days_until(due_date)
  age_days: computed days_since(created_at)
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]

        # days_until
        cf1 = entity.get_computed_field("days_until_due")
        assert cf1 is not None
        assert cf1.computed_expr is not None
        assert isinstance(cf1.computed_expr, FuncCall)
        assert cf1.computed_expr.name == "days_until"

        # days_since
        cf2 = entity.get_computed_field("age_days")
        assert cf2 is not None
        assert cf2.computed_expr is not None
        assert isinstance(cf2.computed_expr, FuncCall)
        assert cf2.computed_expr.name == "days_since"

    def test_all_aggregate_functions(self) -> None:
        """Test parsing all supported aggregate functions."""
        dsl = """
module test.core
app test_app "Test App"

entity Stats "Stats":
  id: uuid pk
  value: decimal(10, 2)
  total: computed sum(value)
  cnt: computed count(value)
  average: computed avg(value)
  minimum: computed min(value)
  maximum: computed max(value)
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]

        funcs = {
            "total": "sum",
            "cnt": "count",
            "average": "avg",
            "minimum": "min",
            "maximum": "max",
        }

        for field_name, expected_func in funcs.items():
            cf = entity.get_computed_field(field_name)
            assert cf is not None, f"Missing computed field: {field_name}"
            assert cf.computed_expr is not None
            assert isinstance(cf.computed_expr, FuncCall)
            assert cf.computed_expr.name == expected_func

    def test_arithmetic_multiplication(self) -> None:
        """Test parsing multiplication in computed fields."""
        dsl = """
module test.core
app test_app "Test App"

entity Invoice "Invoice":
  id: uuid pk
  subtotal: decimal(10, 2)
  tax_rate: decimal(3, 2)
  tax: computed subtotal * tax_rate
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]
        cf = entity.get_computed_field("tax")
        assert cf is not None
        assert cf.computed_expr is not None
        assert isinstance(cf.computed_expr, BinaryExpr)
        assert cf.computed_expr.op == BinaryOp.MUL
        assert isinstance(cf.computed_expr.left, FieldRef)
        assert cf.computed_expr.left.path == ["subtotal"]
        assert isinstance(cf.computed_expr.right, FieldRef)
        assert cf.computed_expr.right.path == ["tax_rate"]

    def test_arithmetic_with_literal(self) -> None:
        """Test parsing arithmetic with numeric literals."""
        dsl = """
module test.core
app test_app "Test App"

entity Invoice "Invoice":
  id: uuid pk
  items: ref LineItem
  tax: computed sum(items.amount) * 0.1

entity LineItem "LineItem":
  id: uuid pk
  amount: decimal(10, 2)
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]
        cf = entity.get_computed_field("tax")
        assert cf is not None
        assert cf.computed_expr is not None
        assert isinstance(cf.computed_expr, BinaryExpr)
        assert cf.computed_expr.op == BinaryOp.MUL
        assert isinstance(cf.computed_expr.left, FuncCall)
        assert isinstance(cf.computed_expr.right, Literal)
        assert cf.computed_expr.right.value == 0.1

    def test_arithmetic_addition(self) -> None:
        """Test parsing addition in computed fields."""
        dsl = """
module test.core
app test_app "Test App"

entity Invoice "Invoice":
  id: uuid pk
  subtotal: decimal(10, 2)
  tax: decimal(10, 2)
  total: computed subtotal + tax
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]
        cf = entity.get_computed_field("total")
        assert cf is not None
        assert cf.computed_expr is not None
        assert isinstance(cf.computed_expr, BinaryExpr)
        assert cf.computed_expr.op == BinaryOp.ADD

    def test_operator_precedence(self) -> None:
        """Test that * and / have higher precedence than + and -."""
        dsl = """
module test.core
app test_app "Test App"

entity Calc "Calc":
  id: uuid pk
  a: decimal(10, 2)
  b: decimal(10, 2)
  c: decimal(10, 2)
  result: computed a + b * c
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]
        cf = entity.get_computed_field("result")
        assert cf is not None
        assert cf.computed_expr is not None

        # Should parse as a + (b * c), not (a + b) * c
        assert isinstance(cf.computed_expr, BinaryExpr)
        assert cf.computed_expr.op == BinaryOp.ADD

        # Left should be 'a'
        assert isinstance(cf.computed_expr.left, FieldRef)
        assert cf.computed_expr.left.path == ["a"]

        # Right should be (b * c)
        assert isinstance(cf.computed_expr.right, BinaryExpr)
        assert cf.computed_expr.right.op == BinaryOp.MUL

    def test_multiple_computed_fields(self) -> None:
        """Test entity with multiple computed fields."""
        dsl = """
module test.core
app test_app "Test App"

entity Order "Order":
  id: uuid pk
  items: ref LineItem
  subtotal: computed sum(items.amount)
  tax: computed sum(items.amount) * 0.1
  shipping: decimal(10, 2)
  total: computed subtotal + tax + shipping

entity LineItem "LineItem":
  id: uuid pk
  amount: decimal(10, 2)
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]
        assert len(entity.computed_fields) == 3

        # Check computed fields list
        names = [cf.name for cf in entity.computed_fields]
        assert names == ["subtotal", "tax", "total"]

    def test_computed_with_nested_path(self) -> None:
        """Test computed fields with multi-level nested paths."""
        dsl = """
module test.core
app test_app "Test App"

entity Project "Project":
  id: uuid pk
  tasks: ref Task
  total_hours: computed sum(tasks.time_entries.hours)

entity Task "Task":
  id: uuid pk
  time_entries: ref TimeEntry

entity TimeEntry "TimeEntry":
  id: uuid pk
  hours: decimal(4, 2)
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]
        cf = entity.get_computed_field("total_hours")
        assert cf is not None
        assert cf.computed_expr is not None
        assert isinstance(cf.computed_expr, FuncCall)
        assert cf.computed_expr.name == "sum"
        arg = cf.computed_expr.args[0]
        assert isinstance(arg, FieldRef)
        assert arg.path == ["tasks", "time_entries", "hours"]

    def test_entity_without_computed_fields(self) -> None:
        """Test that entities without computed fields work correctly."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200)
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]
        assert entity.has_computed_fields is False
        assert len(entity.computed_fields) == 0

    def test_mixed_fields_and_computed(self) -> None:
        """Test that regular fields and computed fields can be mixed."""
        dsl = """
module test.core
app test_app "Test App"

entity Product "Product":
  id: uuid pk
  name: str(200)
  price: decimal(10, 2)
  quantity: int
  total_value: computed price * quantity
  description: text optional
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]

        # Regular fields
        assert len(entity.fields) == 5
        regular_names = [f.name for f in entity.fields]
        assert regular_names == ["id", "name", "price", "quantity", "description"]

        # Computed fields
        assert len(entity.computed_fields) == 1
        assert entity.computed_fields[0].name == "total_value"

    def test_integer_literal(self) -> None:
        """Test parsing integer literals in computed expressions."""
        dsl = """
module test.core
app test_app "Test App"

entity Stats "Stats":
  id: uuid pk
  cnt: int
  doubled: computed cnt * 2
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]
        cf = entity.get_computed_field("doubled")
        assert cf is not None
        assert cf.computed_expr is not None
        assert isinstance(cf.computed_expr, BinaryExpr)
        assert isinstance(cf.computed_expr.right, Literal)
        assert cf.computed_expr.right.value == 2
        assert isinstance(cf.computed_expr.right.value, int)

    def test_dependencies_collection(self) -> None:
        """Test that dependencies are correctly collected from complex expressions."""
        dsl = """
module test.core
app test_app "Test App"

entity Order "Order":
  id: uuid pk
  items: ref LineItem
  discount: decimal(5, 2)
  result: computed sum(items.amount) - discount + sum(items.tax)

entity LineItem "LineItem":
  id: uuid pk
  amount: decimal(10, 2)
  tax: decimal(10, 2)
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]
        cf = entity.get_computed_field("result")
        assert cf is not None

        # Should have dependencies from all three parts
        deps = cf.dependencies
        assert "items.amount" in deps
        assert "discount" in deps
        assert "items.tax" in deps

    def test_computed_field_string_representation(self) -> None:
        """Test that computed field expressions have readable string representation."""
        dsl = """
module test.core
app test_app "Test App"

entity Invoice "Invoice":
  id: uuid pk
  items: ref LineItem
  total: computed sum(items.amount)
  with_tax: computed sum(items.amount) * 1.1

entity LineItem "LineItem":
  id: uuid pk
  amount: decimal(10, 2)
"""
        fragment = _parse(dsl)

        entity = fragment.entities[0]

        cf1 = entity.get_computed_field("total")
        assert cf1 is not None
        assert cf1.computed_expr is not None
        assert "sum" in str(cf1.computed_expr)

        cf2 = entity.get_computed_field("with_tax")
        assert cf2 is not None
        assert cf2.computed_expr is not None
        assert "sum" in str(cf2.computed_expr)
        assert "1.1" in str(cf2.computed_expr)
