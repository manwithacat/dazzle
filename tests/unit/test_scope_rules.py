"""
Unit tests for ScopeRule IR type and AccessSpec.scopes field.
"""

from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
)
from dazzle.core.ir.domain import AccessSpec, PermissionKind, ScopeRule


def _make_condition() -> ConditionExpr:
    """Helper: build a simple field condition (owner_id = current_user)."""
    return ConditionExpr(
        comparison=Comparison(
            field="owner_id",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="current_user"),
        )
    )


class TestScopeRule:
    """Tests for ScopeRule dataclass / Pydantic model."""

    def test_scope_rule_with_field_condition(self):
        """ScopeRule stores operation and condition correctly."""
        condition = _make_condition()
        rule = ScopeRule(
            operation=PermissionKind.READ,
            condition=condition,
            personas=["manager"],
        )

        assert rule.operation == PermissionKind.READ
        assert rule.condition == condition
        assert rule.personas == ["manager"]

    def test_scope_rule_condition_none_means_all(self):
        """condition=None means 'all records' — no row filter applied."""
        rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=None,
            personas=["admin"],
        )

        assert rule.operation == PermissionKind.LIST
        assert rule.condition is None
        assert rule.personas == ["admin"]

    def test_scope_rule_wildcard_personas(self):
        """personas=['*'] means all authorized roles."""
        rule = ScopeRule(
            operation=PermissionKind.READ,
            condition=_make_condition(),
            personas=["*"],
        )

        assert rule.personas == ["*"]

    def test_scope_rule_default_personas_empty(self):
        """personas defaults to empty list when not supplied."""
        rule = ScopeRule(operation=PermissionKind.DELETE)

        assert rule.personas == []

    def test_scope_rule_all_permission_kinds(self):
        """ScopeRule accepts every PermissionKind value."""
        for kind in PermissionKind:
            rule = ScopeRule(operation=kind)
            assert rule.operation == kind


class TestAccessSpecScopes:
    """Tests for the scopes field on AccessSpec."""

    def test_access_spec_scopes_defaults_to_empty_list(self):
        """AccessSpec.scopes must default to an empty list."""
        spec = AccessSpec()

        assert spec.scopes == []

    def test_access_spec_scopes_accepts_scope_rule_list(self):
        """AccessSpec.scopes accepts a list of ScopeRule instances."""
        rules = [
            ScopeRule(operation=PermissionKind.READ, personas=["*"]),
            ScopeRule(
                operation=PermissionKind.LIST,
                condition=_make_condition(),
                personas=["manager"],
            ),
        ]
        spec = AccessSpec(scopes=rules)

        assert len(spec.scopes) == 2
        assert spec.scopes[0].operation == PermissionKind.READ
        assert spec.scopes[1].operation == PermissionKind.LIST
        assert spec.scopes[1].personas == ["manager"]

    def test_access_spec_existing_fields_unaffected(self):
        """Adding scopes does not disturb visibility or permissions fields."""
        spec = AccessSpec()

        assert spec.visibility == []
        assert spec.permissions == []
        assert spec.scopes == []
