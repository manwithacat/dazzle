"""Tests for surface field when: clause (v0.30.0)."""

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


class TestSurfaceWhenClause:
    """Tests for surface field when: clause parsing."""

    def test_field_without_when(self) -> None:
        """Fields without when: clause have when_expr=None."""
        dsl = """
module test
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title "Title"
"""
        fragment = _parse(dsl)
        surface = fragment.surfaces[0]
        section = surface.sections[0]
        assert len(section.elements) == 1
        assert section.elements[0].field_name == "title"
        assert section.elements[0].when_expr is None

    def test_simple_when_comparison(self) -> None:
        """Field with simple comparison when: clause."""
        dsl = """
module test
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: str(50) required
  notes: text

surface task_detail "Task Detail":
  uses entity Task
  mode: view

  section main:
    field title "Title"
    field notes "Notes" when: status == "pending"
"""
        fragment = _parse(dsl)
        surface = fragment.surfaces[0]
        section = surface.sections[0]

        # title has no when
        assert section.elements[0].when_expr is None

        # notes has when: status == "pending"
        notes = section.elements[1]
        assert notes.field_name == "notes"
        assert notes.when_expr is not None
        assert isinstance(notes.when_expr, BinaryExpr)
        assert notes.when_expr.op == BinaryOp.EQ
        assert isinstance(notes.when_expr.left, FieldRef)
        assert notes.when_expr.left.path == ["status"]
        assert isinstance(notes.when_expr.right, Literal)
        assert notes.when_expr.right.value == "pending"

    def test_when_with_boolean_field(self) -> None:
        """Field with when: referencing a boolean field."""
        dsl = """
module test
app test "Test"

entity User "User":
  id: uuid pk
  name: str(100) required
  is_admin: bool required
  admin_notes: text

surface user_profile "User Profile":
  uses entity User
  mode: view

  section main:
    field name "Name"
    field admin_notes "Admin Notes" when: is_admin == true
"""
        fragment = _parse(dsl)
        surface = fragment.surfaces[0]
        notes = surface.sections[0].elements[1]
        assert notes.when_expr is not None
        assert isinstance(notes.when_expr, BinaryExpr)
        assert isinstance(notes.when_expr.right, Literal)
        assert notes.when_expr.right.value is True

    def test_when_with_logical_operator(self) -> None:
        """Field with when: using AND/OR."""
        dsl = """
module test
app test "Test"

entity Order "Order":
  id: uuid pk
  status: str(50) required
  total: decimal(10,2) required
  discount_info: text

surface order_view "Order":
  uses entity Order
  mode: view

  section main:
    field total "Total"
    field discount_info "Discount" when: status == "confirmed" and total > 100
"""
        fragment = _parse(dsl)
        surface = fragment.surfaces[0]
        discount = surface.sections[0].elements[1]
        assert discount.when_expr is not None
        assert isinstance(discount.when_expr, BinaryExpr)
        assert discount.when_expr.op == BinaryOp.AND

    def test_when_with_label(self) -> None:
        """Field with both label and when: clause."""
        dsl = """
module test
app test "Test"

entity Item "Item":
  id: uuid pk
  name: str(100) required
  archived: bool required
  archive_reason: text

surface item_view "Item":
  uses entity Item
  mode: view

  section main:
    field name "Name"
    field archive_reason "Reason for Archive" when: archived == true
"""
        fragment = _parse(dsl)
        surface = fragment.surfaces[0]
        reason = surface.sections[0].elements[1]
        assert reason.field_name == "archive_reason"
        assert reason.label == "Reason for Archive"
        assert reason.when_expr is not None

    def test_multiple_fields_with_when(self) -> None:
        """Multiple fields can each have their own when: clause."""
        dsl = """
module test
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: str(50) required
  resolution: text
  reopen_reason: text

surface task_detail "Task Detail":
  uses entity Task
  mode: view

  section main:
    field title "Title"
    field resolution "Resolution" when: status == "resolved"
    field reopen_reason "Reopen Reason" when: status == "reopened"
"""
        fragment = _parse(dsl)
        surface = fragment.surfaces[0]
        elements = surface.sections[0].elements

        assert elements[0].when_expr is None
        assert elements[1].when_expr is not None
        assert elements[2].when_expr is not None

        # Both are comparisons with different values
        assert isinstance(elements[1].when_expr, BinaryExpr)
        assert isinstance(elements[1].when_expr.right, Literal)
        assert elements[1].when_expr.right.value == "resolved"

        assert isinstance(elements[2].when_expr, BinaryExpr)
        assert isinstance(elements[2].when_expr.right, Literal)
        assert elements[2].when_expr.right.value == "reopened"

    def test_when_with_function_call(self) -> None:
        """Field with when: using a function call expression."""
        dsl = """
module test
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  due_date: date required
  urgent_note: text

surface task_view "Task":
  uses entity Task
  mode: view

  section main:
    field title "Title"
    field urgent_note "Urgent" when: days_until(due_date) < 3
"""
        fragment = _parse(dsl)
        surface = fragment.surfaces[0]
        urgent = surface.sections[0].elements[1]
        assert urgent.when_expr is not None
        assert isinstance(urgent.when_expr, BinaryExpr)
        assert urgent.when_expr.op == BinaryOp.LT
        assert isinstance(urgent.when_expr.left, FuncCall)
        assert urgent.when_expr.left.name == "days_until"
