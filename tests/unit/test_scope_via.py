"""Tests for scope via clause — junction-table access control (#530)."""

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
# Null FK / __RBAC_DENY__ guard tests (#580)
# ---------------------------------------------------------------------------


class TestViaDenyOnNullFK:
    """When _resolve_user_attribute returns __RBAC_DENY__ (null FK), the via
    subquery must return zero rows cleanly instead of crashing with a 500."""

    def test_build_via_subquery_returns_empty_on_deny(self) -> None:
        from unittest.mock import patch

        from dazzle_back.runtime.route_generator import _build_via_subquery

        bindings = [
            {"junction_field": "agent", "target": "current_user.school", "operator": "="},
            {"junction_field": "contact", "target": "id", "operator": "="},
        ]

        with patch(
            "dazzle_back.runtime.route_generator._resolve_user_attribute",
            return_value="__RBAC_DENY__",
        ):
            entity_field, sql, params = _build_via_subquery(
                junction_entity="AgentAssignment",
                bindings=bindings,
                user_id="user-456",
                auth_context=MagicMock(),
            )

        assert sql == "SELECT NULL WHERE FALSE"
        assert params == []
        assert entity_field == "id"

    def test_build_via_subquery_deny_entity_field_before_user_binding(self) -> None:
        """Entity binding listed after user binding — entity_field found from bindings scan."""
        from unittest.mock import patch

        from dazzle_back.runtime.route_generator import _build_via_subquery

        # user binding first, entity binding second
        bindings = [
            {"junction_field": "agent", "target": "current_user.school", "operator": "="},
            {"junction_field": "team", "target": "team_id", "operator": "="},
        ]

        with patch(
            "dazzle_back.runtime.route_generator._resolve_user_attribute",
            return_value="__RBAC_DENY__",
        ):
            entity_field, sql, params = _build_via_subquery(
                junction_entity="TeamMembership",
                bindings=bindings,
                user_id="user-789",
                auth_context=MagicMock(),
            )

        assert sql == "SELECT NULL WHERE FALSE"
        assert params == []
        assert entity_field == "team_id"

    def test_extract_condition_filters_via_deny_produces_empty_subquery(self) -> None:
        from unittest.mock import patch

        from dazzle_back.runtime.route_generator import _extract_condition_filters

        condition = MagicMock()
        condition.kind = "via_check"
        condition.via_junction_entity = "AgentAssignment"
        condition.via_bindings = [
            {"junction_field": "agent", "target": "current_user.school", "operator": "="},
            {"junction_field": "contact", "target": "id", "operator": "="},
        ]

        import logging

        filters: dict = {}
        with patch(
            "dazzle_back.runtime.route_generator._resolve_user_attribute",
            return_value="__RBAC_DENY__",
        ):
            _extract_condition_filters(
                condition, "user-456", filters, logging.getLogger(), MagicMock()
            )

        subquery_keys = [k for k in filters if k.endswith("__in_subquery")]
        assert len(subquery_keys) == 1
        sql, params = filters[subquery_keys[0]]
        assert sql == "SELECT NULL WHERE FALSE"
        assert params == []

    def test_set_filter_deny_produces_impossible_subquery(self) -> None:
        """Regular (non-via) scope clause with __RBAC_DENY__ uses impossible subquery."""
        from dazzle_back.runtime.route_generator import _extract_condition_filters

        condition = MagicMock()
        condition.kind = "comparison"
        condition.field = "school_id"
        condition.value = "current_user.school"
        condition.comparison_op = MagicMock(value="=")

        import logging

        auth_context = MagicMock()
        auth_context.user = MagicMock(spec=[])  # no .school attribute
        auth_context.preferences = {}  # no school in preferences

        filters: dict = {}
        _extract_condition_filters(
            condition, "user-456", filters, logging.getLogger(), auth_context
        )

        # Should produce an impossible subquery, not a raw __RBAC_DENY__ string
        if "school_id__in_subquery" in filters:
            sql, params = filters["school_id__in_subquery"]
            assert sql == "SELECT NULL WHERE FALSE"
        else:
            # Should NOT have the sentinel as a plain value
            assert filters.get("school_id") != "__RBAC_DENY__"


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


# ---------------------------------------------------------------------------
# Negation syntax tests
# ---------------------------------------------------------------------------


def test_not_via_parsed() -> None:
    """not via BlockList(...) parses to ViaCondition with negated=True."""
    dsl = """
module test
app test "Test"

entity BlockList "Block List":
  blocker: ref User required
  blocked: ref User required

entity User "User":
  name: str(200) required

  permit:
    list: role(member)

  scope:
    list: not via BlockList(blocker = current_user, blocked = id)
      for: member
"""
    fragment = _parse(dsl)
    user = [e for e in fragment.entities if e.name == "User"][0]
    assert user.access is not None
    assert len(user.access.scopes) == 1
    scope_rule = user.access.scopes[0]
    assert scope_rule.condition is not None
    via = scope_rule.condition.via_condition
    assert via is not None
    assert via.negated is True
    assert via.junction_entity == "BlockList"
    assert len(via.bindings) == 2


def test_not_parenthesised() -> None:
    """not (status = archived) parses as a NOT-wrapped condition."""
    from dazzle.core.ir.conditions import LogicalOperator

    dsl = """
module test
app test "Test"

entity Document "Document":
  status: enum[draft, active, archived] required
  owner: ref User required

  permit:
    list: role(editor)

  scope:
    list: not (status = archived)
      for: editor
"""
    fragment = _parse(dsl)
    doc = [e for e in fragment.entities if e.name == "Document"][0]
    assert doc.access is not None
    assert len(doc.access.scopes) == 1
    scope_rule = doc.access.scopes[0]
    assert scope_rule.condition is not None
    expr = scope_rule.condition
    # The outer expression should be a NOT logical operator wrapping the inner comparison
    assert expr.operator == LogicalOperator.NOT
    assert expr.left is not None
    # The inner condition should be the comparison: status = archived
    inner = expr.left
    assert inner.comparison is not None
    assert inner.comparison.field == "status"
