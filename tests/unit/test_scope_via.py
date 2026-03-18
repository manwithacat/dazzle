"""Tests for scope via clause — junction-table access control (#530)."""

from __future__ import annotations

from dazzle.core.ir.conditions import ConditionExpr, ViaBinding, ViaCondition


class TestViaBindingModel:
    def test_entity_binding(self) -> None:
        b = ViaBinding(junction_field="contact", target="id")
        assert b.junction_field == "contact"
        assert b.target == "id"
        assert b.operator == "="

    def test_user_binding(self) -> None:
        b = ViaBinding(junction_field="agent", target="current_user.contact")
        assert b.target == "current_user.contact"

    def test_literal_filter(self) -> None:
        b = ViaBinding(junction_field="revoked_at", target="null", operator="=")
        assert b.target == "null"

    def test_not_equals_operator(self) -> None:
        b = ViaBinding(junction_field="status", target="null", operator="!=")
        assert b.operator == "!="


class TestViaConditionModel:
    def test_basic_via(self) -> None:
        via = ViaCondition(
            junction_entity="AgentAssignment",
            bindings=[
                ViaBinding(junction_field="agent", target="current_user.contact"),
                ViaBinding(junction_field="contact", target="id"),
            ],
        )
        assert via.junction_entity == "AgentAssignment"
        assert len(via.bindings) == 2

    def test_with_literal_filter(self) -> None:
        via = ViaCondition(
            junction_entity="AgentAssignment",
            bindings=[
                ViaBinding(junction_field="agent", target="current_user.contact"),
                ViaBinding(junction_field="contact", target="id"),
                ViaBinding(junction_field="revoked_at", target="null"),
            ],
        )
        assert len(via.bindings) == 3


class TestConditionExprViaField:
    def test_via_condition_on_condition_expr(self) -> None:
        via = ViaCondition(
            junction_entity="AgentAssignment",
            bindings=[
                ViaBinding(junction_field="agent", target="current_user.contact"),
                ViaBinding(junction_field="contact", target="id"),
            ],
        )
        expr = ConditionExpr(via_condition=via)
        assert expr.via_condition is not None
        assert expr.is_via_check
        assert not expr.is_compound
        assert not expr.is_role_check

    def test_via_condition_none_by_default(self) -> None:
        expr = ConditionExpr()
        assert expr.via_condition is None
        assert not expr.is_via_check
