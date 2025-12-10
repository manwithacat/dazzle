"""Tests for computed field parsing (v0.7.0)."""

from pathlib import Path

from dazzle.core.dsl_parser import parse_dsl
from dazzle.core.ir import (
    AggregateCall,
    AggregateFunction,
    ArithmeticExpr,
    ArithmeticOperator,
    FieldReference,
    LiteralValue,
)


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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        assert entity.name == "Invoice"
        assert entity.has_computed_fields

        cf = entity.get_computed_field("net_amount")
        assert cf is not None
        assert cf.name == "net_amount"
        assert isinstance(cf.expression, FieldReference)
        assert cf.expression.path == ["gross_amount"]
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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        cf = entity.get_computed_field("total")
        assert cf is not None

        assert isinstance(cf.expression, AggregateCall)
        assert cf.expression.function == AggregateFunction.SUM
        assert cf.expression.field.path == ["line_items", "amount"]
        assert cf.dependencies == {"line_items.amount"}

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        cf = entity.get_computed_field("item_count")
        assert cf is not None

        assert isinstance(cf.expression, AggregateCall)
        assert cf.expression.function == AggregateFunction.COUNT
        assert cf.expression.field.path == ["items"]
        assert cf.dependencies == {"items"}

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]

        # days_until
        cf1 = entity.get_computed_field("days_until_due")
        assert cf1 is not None
        assert isinstance(cf1.expression, AggregateCall)
        assert cf1.expression.function == AggregateFunction.DAYS_UNTIL
        assert cf1.expression.field.path == ["due_date"]

        # days_since
        cf2 = entity.get_computed_field("age_days")
        assert cf2 is not None
        assert isinstance(cf2.expression, AggregateCall)
        assert cf2.expression.function == AggregateFunction.DAYS_SINCE
        assert cf2.expression.field.path == ["created_at"]

    def test_all_aggregate_functions(self) -> None:
        """Test parsing all supported aggregate functions."""
        dsl = """
module test.core
app test_app "Test App"

entity Stats "Stats":
  id: uuid pk
  value: decimal(10, 2)
  total: computed sum(value)
  count: computed count(value)
  average: computed avg(value)
  minimum: computed min(value)
  maximum: computed max(value)
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]

        funcs = {
            "total": AggregateFunction.SUM,
            "count": AggregateFunction.COUNT,
            "average": AggregateFunction.AVG,
            "minimum": AggregateFunction.MIN,
            "maximum": AggregateFunction.MAX,
        }

        for field_name, expected_func in funcs.items():
            cf = entity.get_computed_field(field_name)
            assert cf is not None, f"Missing computed field: {field_name}"
            assert isinstance(cf.expression, AggregateCall)
            assert cf.expression.function == expected_func

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        cf = entity.get_computed_field("tax")
        assert cf is not None

        assert isinstance(cf.expression, ArithmeticExpr)
        assert cf.expression.operator == ArithmeticOperator.MULTIPLY
        assert isinstance(cf.expression.left, FieldReference)
        assert cf.expression.left.path == ["subtotal"]
        assert isinstance(cf.expression.right, FieldReference)
        assert cf.expression.right.path == ["tax_rate"]

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        cf = entity.get_computed_field("tax")
        assert cf is not None

        assert isinstance(cf.expression, ArithmeticExpr)
        assert cf.expression.operator == ArithmeticOperator.MULTIPLY
        assert isinstance(cf.expression.left, AggregateCall)
        assert isinstance(cf.expression.right, LiteralValue)
        assert cf.expression.right.value == 0.1

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        cf = entity.get_computed_field("total")
        assert cf is not None

        assert isinstance(cf.expression, ArithmeticExpr)
        assert cf.expression.operator == ArithmeticOperator.ADD

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        cf = entity.get_computed_field("result")
        assert cf is not None

        # Should parse as a + (b * c), not (a + b) * c
        assert isinstance(cf.expression, ArithmeticExpr)
        assert cf.expression.operator == ArithmeticOperator.ADD

        # Left should be 'a'
        assert isinstance(cf.expression.left, FieldReference)
        assert cf.expression.left.path == ["a"]

        # Right should be (b * c)
        assert isinstance(cf.expression.right, ArithmeticExpr)
        assert cf.expression.right.operator == ArithmeticOperator.MULTIPLY

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        cf = entity.get_computed_field("total_hours")
        assert cf is not None

        assert isinstance(cf.expression, AggregateCall)
        assert cf.expression.field.path == ["tasks", "time_entries", "hours"]
        assert cf.dependencies == {"tasks.time_entries.hours"}

    def test_entity_without_computed_fields(self) -> None:
        """Test that entities without computed fields work correctly."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200)
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

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
  count: int
  doubled: computed count * 2
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        cf = entity.get_computed_field("doubled")
        assert cf is not None

        assert isinstance(cf.expression, ArithmeticExpr)
        assert isinstance(cf.expression.right, LiteralValue)
        assert cf.expression.right.value == 2
        assert isinstance(cf.expression.right.value, int)

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]

        cf1 = entity.get_computed_field("total")
        assert cf1 is not None
        assert str(cf1.expression) == "sum(items.amount)"

        cf2 = entity.get_computed_field("with_tax")
        assert cf2 is not None
        assert str(cf2.expression) == "(sum(items.amount) * 1.1)"
