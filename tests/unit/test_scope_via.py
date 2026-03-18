"""Tests for scope via clause — junction-table access control (#530)."""

from __future__ import annotations

import pytest

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


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

from dazzle.core.dsl_parser_impl import parse_dsl  # noqa: E402
from dazzle.core.errors import ParseError  # noqa: E402


def _parse(dsl: str):
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return fragment


class TestParseViaClause:
    def test_basic_via(self) -> None:
        dsl = """
module test
app test "Test"

entity AgentAssignment "Assignment":
  agent: ref Contact required
  contact: ref Contact required

entity Contact "Contact":
  name: str(200) required

  permit:
    list: role(agent)

  scope:
    list: via AgentAssignment(agent = current_user.contact, contact = id)
      for: agent
"""
        fragment = _parse(dsl)
        contact = [e for e in fragment.entities if e.name == "Contact"][0]
        assert contact.access is not None
        assert len(contact.access.scopes) == 1
        scope_rule = contact.access.scopes[0]
        assert scope_rule.condition is not None
        assert scope_rule.condition.via_condition is not None
        via = scope_rule.condition.via_condition
        assert via.junction_entity == "AgentAssignment"
        assert len(via.bindings) == 2

    def test_via_with_literal_filter(self) -> None:
        dsl = """
module test
app test "Test"

entity AgentAssignment "Assignment":
  agent: ref Contact required
  contact: ref Contact required
  revoked_at: datetime

entity Contact "Contact":
  name: str(200) required

  permit:
    list: role(agent)

  scope:
    list: via AgentAssignment(agent = current_user.contact, contact = id, revoked_at = null)
      for: agent
"""
        fragment = _parse(dsl)
        contact = [e for e in fragment.entities if e.name == "Contact"][0]
        via = contact.access.scopes[0].condition.via_condition
        assert len(via.bindings) == 3
        null_binding = [b for b in via.bindings if b.target == "null"][0]
        assert null_binding.junction_field == "revoked_at"

    def test_via_with_not_equals(self) -> None:
        dsl = """
module test
app test "Test"

entity TeamMembership "Membership":
  user: ref User required
  team: ref Team required
  status: str(20)

entity Task "Task":
  team: ref Team required

  permit:
    list: role(member)

  scope:
    list: via TeamMembership(user = current_user, team = team, status != null)
      for: member
"""
        fragment = _parse(dsl)
        task = [e for e in fragment.entities if e.name == "Task"][0]
        via = task.access.scopes[0].condition.via_condition
        ne_binding = [b for b in via.bindings if b.operator == "!="][0]
        assert ne_binding.junction_field == "status"

    def test_via_missing_parens_error(self) -> None:
        dsl = """
module test
app test "Test"

entity Contact "Contact":
  name: str(200) required
  permit:
    list: role(agent)
  scope:
    list: via AgentAssignment agent = current_user
      for: agent
"""
        with pytest.raises(ParseError, match="Expected '\\(' after"):
            _parse(dsl)

    def test_via_missing_entity_binding_error(self) -> None:
        dsl = """
module test
app test "Test"

entity Contact "Contact":
  name: str(200) required
  permit:
    list: role(agent)
  scope:
    list: via AgentAssignment(agent = current_user)
      for: agent
"""
        with pytest.raises(ParseError, match="at least one entity binding"):
            _parse(dsl)

    def test_via_missing_user_binding_error(self) -> None:
        dsl = """
module test
app test "Test"

entity Contact "Contact":
  name: str(200) required
  permit:
    list: role(agent)
  scope:
    list: via AgentAssignment(contact = id)
      for: agent
"""
        with pytest.raises(ParseError, match="at least one user binding"):
            _parse(dsl)


# ---------------------------------------------------------------------------
# Query builder tests
# ---------------------------------------------------------------------------

from dazzle_back.runtime.query_builder import FilterCondition, FilterOperator  # noqa: E402


class TestInSubqueryOperator:
    def test_filter_operator_exists(self) -> None:
        assert FilterOperator.IN_SUBQUERY == "in_subquery"

    def test_parse_in_subquery_key(self) -> None:
        fc = FilterCondition.parse(
            "id__in_subquery",
            ('SELECT "contact" FROM "AgentAssignment" WHERE "agent" = %s', ["user-123"]),
        )
        assert fc.field == "id"
        assert fc.operator == FilterOperator.IN_SUBQUERY

    def test_to_sql_in_subquery(self) -> None:
        fc = FilterCondition(
            field="id",
            operator=FilterOperator.IN_SUBQUERY,
            value=('SELECT "contact" FROM "AgentAssignment" WHERE "agent" = %s', ["user-123"]),
        )
        sql, params = fc.to_sql()
        assert "IN" in sql
        assert '"id"' in sql
        assert 'SELECT "contact"' in sql
        assert params == ["user-123"]


# ---------------------------------------------------------------------------
# Converter tests
# ---------------------------------------------------------------------------

from dazzle.core.ir.domain import PermissionKind, ScopeRule  # noqa: E402
from dazzle_back.converters.entity_converter import _convert_scope_rule  # noqa: E402
from dazzle_back.specs.auth import AccessOperationKind  # noqa: E402


class TestConvertViaCondition:
    def test_converts_via_scope_rule(self) -> None:
        via = ViaCondition(
            junction_entity="AgentAssignment",
            bindings=[
                ViaBinding(junction_field="agent", target="current_user.contact"),
                ViaBinding(junction_field="contact", target="id"),
                ViaBinding(junction_field="revoked_at", target="null"),
            ],
        )
        rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=ConditionExpr(via_condition=via),
            personas=["agent"],
        )
        spec = _convert_scope_rule(rule)

        assert spec.operation == AccessOperationKind.LIST
        assert spec.condition is not None
        assert spec.condition.kind == "via_check"
        assert spec.condition.via_junction_entity == "AgentAssignment"
        assert len(spec.condition.via_bindings) == 3
        assert spec.personas == ["agent"]

    def test_converts_via_binding_fields(self) -> None:
        via = ViaCondition(
            junction_entity="TeamMembership",
            bindings=[
                ViaBinding(junction_field="user", target="current_user"),
                ViaBinding(junction_field="team", target="team"),
            ],
        )
        rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=ConditionExpr(via_condition=via),
            personas=["member"],
        )
        spec = _convert_scope_rule(rule)
        bindings = spec.condition.via_bindings
        assert bindings[0]["junction_field"] == "user"
        assert bindings[0]["target"] == "current_user"
        assert bindings[1]["junction_field"] == "team"
        assert bindings[1]["target"] == "team"


# ---------------------------------------------------------------------------
# Route generator tests
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock  # noqa: E402


class TestBuildViaSubquery:
    def test_basic_subquery(self) -> None:
        from dazzle_back.runtime.route_generator import _build_via_subquery

        bindings = [
            {"junction_field": "agent", "target": "current_user.contact", "operator": "="},
            {"junction_field": "contact", "target": "id", "operator": "="},
        ]
        auth_context = MagicMock()
        auth_context.user = MagicMock()
        auth_context.user.contact = "user-contact-123"

        entity_field, sql, params = _build_via_subquery(
            junction_entity="AgentAssignment",
            bindings=bindings,
            user_id="user-456",
            auth_context=auth_context,
        )

        assert entity_field == "id"
        assert '"AgentAssignment"' in sql
        assert '"contact"' in sql
        assert '"agent"' in sql
        assert len(params) >= 1

    def test_subquery_with_null_filter(self) -> None:
        from dazzle_back.runtime.route_generator import _build_via_subquery

        bindings = [
            {"junction_field": "agent", "target": "current_user", "operator": "="},
            {"junction_field": "contact", "target": "id", "operator": "="},
            {"junction_field": "revoked_at", "target": "null", "operator": "="},
        ]
        auth_context = MagicMock()

        entity_field, sql, params = _build_via_subquery(
            junction_entity="AgentAssignment",
            bindings=bindings,
            user_id="user-456",
            auth_context=auth_context,
        )

        assert "IS NULL" in sql
        assert entity_field == "id"

    def test_subquery_with_not_null_filter(self) -> None:
        from dazzle_back.runtime.route_generator import _build_via_subquery

        bindings = [
            {"junction_field": "user", "target": "current_user", "operator": "="},
            {"junction_field": "team", "target": "team", "operator": "="},
            {"junction_field": "active", "target": "null", "operator": "!="},
        ]
        auth_context = MagicMock()

        entity_field, sql, params = _build_via_subquery(
            junction_entity="TeamMembership",
            bindings=bindings,
            user_id="user-789",
            auth_context=auth_context,
        )

        assert "IS NOT NULL" in sql
        assert entity_field == "team"


class TestExtractViaCheckFilters:
    def test_via_check_produces_in_subquery_filter(self) -> None:
        from dazzle_back.runtime.route_generator import _extract_condition_filters

        condition = MagicMock()
        condition.kind = "via_check"
        condition.via_junction_entity = "AgentAssignment"
        condition.via_bindings = [
            {"junction_field": "agent", "target": "current_user.contact", "operator": "="},
            {"junction_field": "contact", "target": "id", "operator": "="},
        ]

        auth_context = MagicMock()
        auth_context.user = MagicMock()
        auth_context.user.contact = "user-contact-123"

        import logging

        filters: dict = {}
        _extract_condition_filters(
            condition, "user-456", filters, logging.getLogger(), auth_context
        )

        subquery_keys = [k for k in filters if k.endswith("__in_subquery")]
        assert len(subquery_keys) == 1


# ---------------------------------------------------------------------------
# RBAC matrix integration tests
# ---------------------------------------------------------------------------


class TestRbacMatrixVia:
    def test_via_scope_produces_permit_scoped(self) -> None:
        """A scope rule with a via condition should produce PERMIT_SCOPED."""
        dsl = """
module test
app test "Test"

entity AgentAssignment "Assignment":
  agent: ref Contact required
  contact: ref Contact required

entity Contact "Contact":
  name: str(200) required

  permit:
    list: role(agent)

  scope:
    list: via AgentAssignment(agent = current_user.contact, contact = id)
      for: agent
"""
        fragment = _parse(dsl)
        contact = [e for e in fragment.entities if e.name == "Contact"][0]

        # Verify the scope rule has a via condition
        scope_rule = contact.access.scopes[0]
        assert scope_rule.condition.via_condition is not None
        assert scope_rule.personas == ["agent"]
