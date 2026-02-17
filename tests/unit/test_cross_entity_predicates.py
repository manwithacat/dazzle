"""Tests for cross-entity predicate parsing (v0.29.0).

Covers:
- Guard expression parsing on state transitions
- Inline transition syntax (backwards compat)
- Block transition syntax with guard: expressions
- Guard message parsing
- End-to-end: parse DSL → evaluate guard expression
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.expression_lang import evaluate
from dazzle.core.ir.expressions import BinaryExpr, BinaryOp, FieldRef

_TEST_FILE = Path("test.dsl")


def _parse(dsl: str):
    """Parse DSL and return the fragment."""
    _, _, _, _, _, fragment = parse_dsl(dsl, _TEST_FILE)
    return fragment


class TestInlineTransitionBackwardsCompat:
    """Existing inline transition syntax still works."""

    def test_requires_guard(self) -> None:
        dsl = """
module test_mod

entity Ticket "Ticket":
  id: uuid pk
  status: enum[open,assigned,closed]
  assignee: str(200)

  transitions:
    open -> assigned: requires assignee
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.state_machine is not None
        t = entity.state_machine.transitions[0]
        assert t.from_state == "open"
        assert t.to_state == "assigned"
        assert len(t.guards) == 1
        assert t.guards[0].requires_field == "assignee"

    def test_role_guard(self) -> None:
        dsl = """
module test_mod

entity Ticket "Ticket":
  id: uuid pk
  status: enum[open,closed]

  transitions:
    * -> open: role(admin)
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.state_machine is not None
        t = entity.state_machine.transitions[0]
        assert t.from_state == "*"
        assert t.guards[0].requires_role == "admin"

    def test_auto_transition(self) -> None:
        dsl = """
module test_mod

entity Ticket "Ticket":
  id: uuid pk
  status: enum[resolved,closed]

  transitions:
    resolved -> closed: auto after 7 days or manual
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.state_machine is not None
        t = entity.state_machine.transitions[0]
        assert t.is_auto
        assert t.auto_spec is not None
        assert t.auto_spec.delay_value == 7
        assert t.auto_spec.allow_manual


class TestBlockTransitionGuards:
    """v0.29.0: Block syntax with guard: expressions."""

    def test_simple_guard_expression(self) -> None:
        dsl = """
module test_mod

entity Letter "Letter":
  id: uuid pk
  status: enum[sent,signed]
  aml_status: str(50)

  transitions:
    sent -> signed:
      guard: aml_status == "completed"
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.state_machine is not None
        t = entity.state_machine.transitions[0]
        assert len(t.guards) == 1
        guard = t.guards[0]
        assert guard.is_expr_guard
        assert guard.guard_expr is not None
        assert isinstance(guard.guard_expr, BinaryExpr)
        assert guard.guard_expr.op == BinaryOp.EQ

    def test_cross_entity_arrow_guard(self) -> None:
        dsl = """
module test_mod

entity Letter "Letter":
  id: uuid pk
  status: enum[sent,signed]

  transitions:
    sent -> signed:
      guard: self->signatory->aml_status == "completed"
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.state_machine is not None
        t = entity.state_machine.transitions[0]
        guard = t.guards[0]
        assert guard.guard_expr is not None
        # The left side should be a FieldRef with arrow path
        assert isinstance(guard.guard_expr, BinaryExpr)
        left = guard.guard_expr.left
        assert isinstance(left, FieldRef)
        assert left.path == ["self", "signatory", "aml_status"]

    def test_guard_with_message(self) -> None:
        dsl = """
module test_mod

entity Letter "Letter":
  id: uuid pk
  status: enum[sent,signed]

  transitions:
    sent -> signed:
      guard: aml_status == "completed"
        message: "AML checks must pass before signing"
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.state_machine is not None
        t = entity.state_machine.transitions[0]
        guard = t.guards[0]
        assert guard.guard_expr is not None
        assert guard.guard_message == "AML checks must pass before signing"

    def test_multiple_guards(self) -> None:
        dsl = """
module test_mod

entity Letter "Letter":
  id: uuid pk
  status: enum[sent,signed]
  assignee: str(200)

  transitions:
    sent -> signed:
      guard: aml_status == "completed"
      requires assignee
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.state_machine is not None
        t = entity.state_machine.transitions[0]
        assert len(t.guards) == 2
        assert t.guards[0].is_expr_guard
        assert t.guards[1].is_field_guard
        assert t.guards[1].requires_field == "assignee"

    def test_guard_comparison_operators(self) -> None:
        dsl = """
module test_mod

entity Task "Task":
  id: uuid pk
  status: enum[pending,approved]
  score: int

  transitions:
    pending -> approved:
      guard: score >= 70
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.state_machine is not None
        t = entity.state_machine.transitions[0]
        guard = t.guards[0]
        assert guard.guard_expr is not None
        assert isinstance(guard.guard_expr, BinaryExpr)
        assert guard.guard_expr.op == BinaryOp.GE

    def test_block_with_auto_transition(self) -> None:
        dsl = """
module test_mod

entity Ticket "Ticket":
  id: uuid pk
  status: enum[resolved,closed]

  transitions:
    resolved -> closed:
      auto after 3 days
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.state_machine is not None
        t = entity.state_machine.transitions[0]
        assert t.is_auto
        assert t.auto_spec is not None
        assert t.auto_spec.delay_value == 3

    def test_mixed_guards_and_auto(self) -> None:
        dsl = """
module test_mod

entity Ticket "Ticket":
  id: uuid pk
  status: enum[reviewed,approved]
  reviewer: str(200)

  transitions:
    reviewed -> approved:
      guard: score > 50
      requires reviewer
      auto after 14 days
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.state_machine is not None
        t = entity.state_machine.transitions[0]
        assert len(t.guards) == 2
        assert t.guards[0].is_expr_guard
        assert t.guards[1].requires_field == "reviewer"
        assert t.is_auto
        assert t.auto_spec is not None


class TestGuardExpressionEvaluation:
    """End-to-end: parse DSL guard → evaluate expression."""

    def test_evaluate_simple_guard(self) -> None:
        dsl = """
module test_mod

entity Letter "Letter":
  id: uuid pk
  status: enum[sent,signed]

  transitions:
    sent -> signed:
      guard: aml_status == "completed"
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        guard = entity.state_machine.transitions[0].guards[0]
        assert guard.guard_expr is not None

        result = evaluate(guard.guard_expr, {"aml_status": "completed"})
        assert result is True

        result = evaluate(guard.guard_expr, {"aml_status": "pending"})
        assert result is False

    def test_evaluate_cross_entity_guard(self) -> None:
        dsl = """
module test_mod

entity Letter "Letter":
  id: uuid pk
  status: enum[sent,signed]

  transitions:
    sent -> signed:
      guard: self->signatory->aml_status == "completed"
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        guard = entity.state_machine.transitions[0].guards[0]
        assert guard.guard_expr is not None

        context = {
            "self": {
                "signatory": {
                    "aml_status": "completed",
                },
            },
        }
        result = evaluate(guard.guard_expr, context)
        assert result is True

    def test_evaluate_numeric_guard(self) -> None:
        dsl = """
module test_mod

entity Task "Task":
  id: uuid pk
  status: enum[pending,approved]
  score: int

  transitions:
    pending -> approved:
      guard: score >= 70
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        guard = entity.state_machine.transitions[0].guards[0]

        assert evaluate(guard.guard_expr, {"score": 85}) is True
        assert evaluate(guard.guard_expr, {"score": 50}) is False
