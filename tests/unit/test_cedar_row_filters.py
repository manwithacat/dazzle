"""
Unit tests for Cedar row-level RBAC filtering in list handlers.

Tests the _extract_cedar_row_filters and _extract_condition_filters functions
that convert Cedar permission rules to SQL-compatible row filters.
"""

from __future__ import annotations

from dazzle_back.runtime.route_generator import (
    _extract_cedar_row_filters,
    _extract_condition_filters,
)
from dazzle_back.specs.auth import (
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


# ---- Test classes -----------------------------------------------------------


class TestExtractCedarRowFilters:
    """Tests for _extract_cedar_row_filters."""

    def test_owner_equals_current_user(self) -> None:
        """Basic owner_id = current_user condition produces row filter."""
        spec = _make_access_spec(
            [
                _make_rule(
                    AccessOperationKind.LIST,
                    condition=_make_condition("owner_id", "current_user"),
                ),
            ]
        )
        filters = _extract_cedar_row_filters(spec, "user-123")
        assert filters == {"owner_id": "user-123"}

    def test_read_rule_also_applies(self) -> None:
        """READ permission rules also contribute to list row filters."""
        spec = _make_access_spec(
            [
                _make_rule(
                    AccessOperationKind.READ,
                    condition=_make_condition("owner_id", "current_user"),
                ),
            ]
        )
        filters = _extract_cedar_row_filters(spec, "user-456")
        assert filters == {"owner_id": "user-456"}

    def test_non_list_read_rules_ignored(self) -> None:
        """CREATE/UPDATE/DELETE rules are not used for row filtering."""
        spec = _make_access_spec(
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
            ]
        )
        filters = _extract_cedar_row_filters(spec, "user-789")
        assert filters == {}

    def test_forbid_rules_ignored(self) -> None:
        """FORBID rules are not used for row-level filtering."""
        spec = _make_access_spec(
            [
                _make_rule(
                    AccessOperationKind.LIST,
                    condition=_make_condition("owner_id", "current_user"),
                    effect=AccessPolicyEffect.FORBID,
                ),
            ]
        )
        filters = _extract_cedar_row_filters(spec, "user-123")
        assert filters == {}

    def test_unconditional_permit_skips_filtering(self) -> None:
        """An unconditional permit rule means no row filtering needed."""
        spec = _make_access_spec(
            [
                _make_rule(AccessOperationKind.LIST, condition=None),
            ]
        )
        filters = _extract_cedar_row_filters(spec, "user-123")
        assert filters == {}

    def test_unconditional_permit_with_matching_persona(self) -> None:
        """Unconditional permit with matching persona skips filtering."""

        class FakeUser:
            roles = ["admin"]

        class FakeAuth:
            user = FakeUser()

        spec = _make_access_spec(
            [
                _make_rule(
                    AccessOperationKind.LIST,
                    condition=None,
                    personas=["admin"],
                ),
            ]
        )
        filters = _extract_cedar_row_filters(spec, "user-123", auth_context=FakeAuth())
        assert filters == {}

    def test_unconditional_permit_with_non_matching_persona(self) -> None:
        """Unconditional permit with non-matching persona doesn't grant unrestricted access."""

        class FakeUser:
            roles = ["viewer"]

        class FakeAuth:
            user = FakeUser()

        spec = _make_access_spec(
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
            ]
        )
        filters = _extract_cedar_row_filters(spec, "user-123", auth_context=FakeAuth())
        assert filters == {"owner_id": "user-123"}

    def test_no_permissions(self) -> None:
        """Empty permissions list returns empty filters."""
        spec = _make_access_spec([])
        filters = _extract_cedar_row_filters(spec, "user-123")
        assert filters == {}

    def test_no_permissions_attr(self) -> None:
        """Spec without permissions attribute returns empty filters."""

        class FakeSpec:
            pass

        filters = _extract_cedar_row_filters(FakeSpec(), "user-123")
        assert filters == {}

    def test_and_condition_both_extracted(self) -> None:
        """AND conditions produce multiple SQL filters."""
        spec = _make_access_spec(
            [
                _make_rule(
                    AccessOperationKind.LIST,
                    condition=_make_and_condition(
                        _make_condition("owner_id", "current_user"),
                        _make_condition("status", "active"),
                    ),
                ),
            ]
        )
        filters = _extract_cedar_row_filters(spec, "user-123")
        assert filters == {"owner_id": "user-123", "status": "active"}

    def test_or_condition_not_pushed_to_sql(self) -> None:
        """OR conditions are not pushed to SQL."""
        spec = _make_access_spec(
            [
                _make_rule(
                    AccessOperationKind.LIST,
                    condition=_make_or_condition(
                        _make_condition("owner_id", "current_user"),
                        _make_condition("is_public", True),
                    ),
                ),
            ]
        )
        filters = _extract_cedar_row_filters(spec, "user-123")
        assert filters == {}

    def test_persona_scoped_rule_wrong_role(self) -> None:
        """Rule with persona that doesn't match user's roles is skipped."""

        class FakeUser:
            roles = ["viewer"]

        class FakeAuth:
            user = FakeUser()

        spec = _make_access_spec(
            [
                _make_rule(
                    AccessOperationKind.LIST,
                    condition=_make_condition("department_id", "current_user"),
                    personas=["manager"],
                ),
            ]
        )
        filters = _extract_cedar_row_filters(spec, "user-123", auth_context=FakeAuth())
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

    def test_greater_than_ignored(self) -> None:
        """Non-equality comparisons are not pushed to SQL."""
        cond = _make_condition("age", 18, AccessComparisonKind.GREATER_THAN)
        filters: dict[str, object] = {}
        _extract_condition_filters(cond, "u1", filters, None)
        assert filters == {}
