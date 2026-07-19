"""
Unit tests for Cedar row-level RBAC filtering in list handlers.

Tests the _extract_cedar_row_filters and _extract_condition_filters functions
that convert Cedar permission rules to SQL-compatible row filters.
"""

from typing import Any

import pytest

from dazzle.http.runtime.route_generator import (
    _extract_cedar_row_filters,
    _extract_condition_filters,
)
from dazzle.http.specs.auth import (
    AccessComparisonKind,
    AccessConditionSpec,
    AccessLogicalKind,
    AccessOperationKind,
    AccessPolicyEffect,
    EntityAccessSpec,
    PermissionRuleSpec,
)

# ---- Helpers ----------------------------------------------------------------


def _make_condition(
    field: str,
    value: str | int | float | bool,
    op: AccessComparisonKind = AccessComparisonKind.EQUALS,
) -> AccessConditionSpec:
    return AccessConditionSpec(
        kind="comparison",
        field=field,
        comparison_op=op,
        value=value,
    )


def _make_and_condition(
    left: AccessConditionSpec,
    right: AccessConditionSpec,
) -> AccessConditionSpec:
    return AccessConditionSpec(
        kind="logical",
        logical_op=AccessLogicalKind.AND,
        logical_left=left,
        logical_right=right,
    )


def _make_or_condition(
    left: AccessConditionSpec,
    right: AccessConditionSpec,
) -> AccessConditionSpec:
    return AccessConditionSpec(
        kind="logical",
        logical_op=AccessLogicalKind.OR,
        logical_left=left,
        logical_right=right,
    )


def _make_rule(
    operation: AccessOperationKind,
    condition: AccessConditionSpec | None = None,
    effect: AccessPolicyEffect = AccessPolicyEffect.PERMIT,
    personas: list[str] | None = None,
) -> PermissionRuleSpec:
    return PermissionRuleSpec(
        operation=operation,
        condition=condition,
        effect=effect,
        personas=personas or [],
    )


def _make_access_spec(rules: list[PermissionRuleSpec]) -> EntityAccessSpec:
    return EntityAccessSpec(permissions=rules)


class _FakeUser:
    def __init__(self, roles: list[str]) -> None:
        self.roles = roles


class _FakeAuth:
    is_authenticated = True  # auth Plan 1b: effective_roles needs this

    def __init__(self, roles: list[str]) -> None:
        self.user = _FakeUser(roles)


# ---- Test classes -----------------------------------------------------------


class TestExtractCedarRowFilters:
    """Tests for _extract_cedar_row_filters.

    One contract, one table: a rules list (plus the requesting user's
    roles, when persona-scoped) maps to the row filters pushed to SQL.
    `roles=None` means no auth context is supplied.
    """

    @pytest.mark.parametrize(
        ("rules", "roles", "expected"),
        [
            pytest.param(
                # Basic owner_id = current_user condition produces row filter.
                [
                    _make_rule(
                        AccessOperationKind.LIST,
                        condition=_make_condition("owner_id", "current_user"),
                    ),
                ],
                None,
                {"owner_id": "user-123"},
                id="owner-equals-current-user",
            ),
            pytest.param(
                # READ permission rules also contribute to list row filters.
                [
                    _make_rule(
                        AccessOperationKind.READ,
                        condition=_make_condition("owner_id", "current_user"),
                    ),
                ],
                None,
                {"owner_id": "user-123"},
                id="read-rule-also-applies",
            ),
            pytest.param(
                # CREATE/UPDATE/DELETE rules are not used for row filtering.
                [
                    _make_rule(
                        AccessOperationKind.CREATE,
                        condition=_make_condition("owner_id", "current_user"),
                    ),
                    _make_rule(
                        AccessOperationKind.UPDATE,
                        condition=_make_condition("owner_id", "current_user"),
                    ),
                    _make_rule(
                        AccessOperationKind.DELETE,
                        condition=_make_condition("owner_id", "current_user"),
                    ),
                ],
                None,
                {},
                id="non-list-read-rules-ignored",
            ),
            pytest.param(
                # FORBID rules are not used for row-level filtering.
                [
                    _make_rule(
                        AccessOperationKind.LIST,
                        condition=_make_condition("owner_id", "current_user"),
                        effect=AccessPolicyEffect.FORBID,
                    ),
                ],
                None,
                {},
                id="forbid-rules-ignored",
            ),
            pytest.param(
                # An unconditional permit rule means no row filtering needed.
                [_make_rule(AccessOperationKind.LIST, condition=None)],
                None,
                {},
                id="unconditional-permit-skips-filtering",
            ),
            pytest.param(
                # Unconditional permit with matching persona skips filtering.
                [
                    _make_rule(
                        AccessOperationKind.LIST,
                        condition=None,
                        personas=["admin"],
                    ),
                ],
                ["admin"],
                {},
                id="unconditional-permit-matching-persona",
            ),
            pytest.param(
                # Unconditional permit with non-matching persona doesn't
                # grant unrestricted access.
                [
                    _make_rule(
                        AccessOperationKind.LIST,
                        condition=_make_condition("owner_id", "current_user"),
                        personas=["viewer"],
                    ),
                    _make_rule(
                        AccessOperationKind.LIST,
                        condition=None,
                        personas=["admin"],
                    ),
                ],
                ["viewer"],
                {"owner_id": "user-123"},
                id="unconditional-permit-non-matching-persona",
            ),
            pytest.param(
                # Empty permissions list returns empty filters.
                [],
                None,
                {},
                id="no-permissions",
            ),
            pytest.param(
                # AND conditions produce multiple SQL filters.
                [
                    _make_rule(
                        AccessOperationKind.LIST,
                        condition=_make_and_condition(
                            _make_condition("owner_id", "current_user"),
                            _make_condition("status", "active"),
                        ),
                    ),
                ],
                None,
                {"owner_id": "user-123", "status": "active"},
                id="and-condition-both-extracted",
            ),
            pytest.param(
                # OR conditions are not pushed to SQL.
                [
                    _make_rule(
                        AccessOperationKind.LIST,
                        condition=_make_or_condition(
                            _make_condition("owner_id", "current_user"),
                            _make_condition("is_public", True),
                        ),
                    ),
                ],
                None,
                {},
                id="or-condition-not-pushed-to-sql",
            ),
            pytest.param(
                # Rule with persona that doesn't match user's roles is skipped.
                [
                    _make_rule(
                        AccessOperationKind.LIST,
                        condition=_make_condition("department_id", "current_user"),
                        personas=["manager"],
                    ),
                ],
                ["viewer"],
                {},
                id="persona-scoped-rule-wrong-role",
            ),
        ],
    )
    def test_rules_map_to_row_filters(
        self,
        rules: list[PermissionRuleSpec],
        roles: list[str] | None,
        expected: dict[str, object],
    ) -> None:
        spec = _make_access_spec(rules)
        auth_context = _FakeAuth(roles) if roles is not None else None
        filters = _extract_cedar_row_filters(spec, "user-123", auth_context=auth_context)
        assert filters == expected

    def test_no_permissions_attr(self) -> None:
        """Spec without permissions attribute returns empty filters."""

        class FakeSpec:
            pass

        filters = _extract_cedar_row_filters(FakeSpec(), "user-123")
        assert filters == {}


class TestExtractConditionFilters:
    """Tests for _extract_condition_filters directly."""

    def test_simple_comparison_equals(self) -> None:
        cond = _make_condition("owner_id", "current_user")
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "u1", filters, None)
        assert filters == {"owner_id": "u1"}

    def test_not_equals_comparison(self) -> None:
        cond = _make_condition("status", "archived", AccessComparisonKind.NOT_EQUALS)
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "u1", filters, None)
        assert filters == {"status__ne": "archived"}

    def test_literal_value_equals(self) -> None:
        cond = _make_condition("tenant_id", "acme-corp")
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "u1", filters, None)
        assert filters == {"tenant_id": "acme-corp"}

    def test_boolean_value(self) -> None:
        cond = _make_condition("is_active", True)
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "u1", filters, None)
        assert filters == {"is_active": True}

    def test_nested_and(self) -> None:
        cond = _make_and_condition(
            _make_condition("owner_id", "current_user"),
            _make_and_condition(
                _make_condition("status", "active"),
                _make_condition("is_visible", True),
            ),
        )
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "u1", filters, None)
        assert filters == {"owner_id": "u1", "status": "active", "is_visible": True}

    def test_or_is_skipped(self) -> None:
        cond = _make_or_condition(
            _make_condition("owner_id", "current_user"),
            _make_condition("is_public", True),
        )
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "u1", filters, None)
        assert filters == {}

    def test_unknown_kind_is_no_op(self) -> None:
        cond = AccessConditionSpec(kind="role_check", role_name="admin")
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "u1", filters, None)
        assert filters == {}

    def test_greater_than_pushed_to_sql(self) -> None:
        """Inequality comparisons (>, >=, <, <=) are pushed to SQL (#547)."""
        cond = _make_condition("age", 18, AccessComparisonKind.GREATER_THAN)
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "u1", filters, None)
        assert filters == {"age__gt": 18}


class TestExtractConditionFiltersIR:
    """Tests for _extract_condition_filters with IR ConditionExpr objects.

    These represent the actual condition type used at runtime (entity.access
    contains PermissionRule with ConditionExpr conditions, not AccessConditionSpec).
    """

    def _make_ir_condition(
        self,
        field: str,
        value: str | int | float | bool,
        op: str = "=",
    ) -> Any:
        from dazzle.core.ir.conditions import (
            Comparison,
            ComparisonOperator,
            ConditionExpr,
            ConditionValue,
        )

        return ConditionExpr(
            comparison=Comparison(
                field=field,
                operator=ComparisonOperator(op),
                value=ConditionValue(literal=value),
            )
        )

    def _make_ir_and(self, left: Any, right: Any) -> Any:
        from dazzle.core.ir.conditions import ConditionExpr, LogicalOperator

        return ConditionExpr(left=left, operator=LogicalOperator.AND, right=right)

    def _make_ir_or(self, left: Any, right: Any) -> Any:
        from dazzle.core.ir.conditions import ConditionExpr, LogicalOperator

        return ConditionExpr(left=left, operator=LogicalOperator.OR, right=right)

    def test_ir_current_user_equals(self) -> None:
        """IR ConditionExpr: student = current_user produces row filter."""
        cond = self._make_ir_condition("student", "current_user")
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "user-abc", filters, None)
        assert filters == {"student": "user-abc"}

    def test_ir_literal_value(self) -> None:
        """IR ConditionExpr: status = 'active' produces literal filter."""
        cond = self._make_ir_condition("status", "active")
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "user-abc", filters, None)
        assert filters == {"status": "active"}

    def test_ir_boolean_value(self) -> None:
        """IR ConditionExpr: is_public = true produces boolean filter."""
        cond = self._make_ir_condition("is_public", True)
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "user-abc", filters, None)
        assert filters == {"is_public": True}

    def test_ir_not_equals(self) -> None:
        """IR ConditionExpr: status != 'archived' produces __ne filter."""
        cond = self._make_ir_condition("status", "archived", "!=")
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "user-abc", filters, None)
        assert filters == {"status__ne": "archived"}

    def test_ir_and_compound(self) -> None:
        """IR ConditionExpr: AND compound extracts both sides."""
        cond = self._make_ir_and(
            self._make_ir_condition("student", "current_user"),
            self._make_ir_condition("active", True),
        )
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "user-abc", filters, None)
        assert filters == {"student": "user-abc", "active": True}

    def test_ir_or_not_pushed(self) -> None:
        """Mixed-field IR OR is fail-closed (#1630), not a silent no-op."""
        cond = self._make_ir_or(
            self._make_ir_condition("owner_id", "current_user"),
            self._make_ir_condition("is_public", True),
        )
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "user-abc", filters, None)
        # Cannot lower mixed-field OR to field__in → empty subquery, not {}.
        assert "__or_unsupported__in_subquery" in filters

    def test_ir_nested_and(self) -> None:
        """IR ConditionExpr: nested AND extracts all conditions."""
        cond = self._make_ir_and(
            self._make_ir_condition("student", "current_user"),
            self._make_ir_and(
                self._make_ir_condition("status", "active"),
                self._make_ir_condition("visible", True),
            ),
        )
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "user-abc", filters, None)
        assert filters == {"student": "user-abc", "status": "active", "visible": True}

    def test_ir_full_cedar_pipeline(self) -> None:
        """End-to-end: IR AccessSpec with PermissionRule + ConditionExpr."""
        from dazzle.core.ir.conditions import (
            Comparison,
            ComparisonOperator,
            ConditionExpr,
            ConditionValue,
        )
        from dazzle.core.ir.domain import (
            AccessSpec,
            PermissionKind,
            PermissionRule,
        )

        access = AccessSpec(
            permissions=[
                PermissionRule(
                    operation=PermissionKind.LIST,
                    condition=ConditionExpr(
                        comparison=Comparison(
                            field="student",
                            operator=ComparisonOperator.EQUALS,
                            value=ConditionValue(literal="current_user"),
                        )
                    ),
                ),
            ]
        )
        filters = _extract_cedar_row_filters(access, "student-001")
        assert filters == {"student": "student-001"}
