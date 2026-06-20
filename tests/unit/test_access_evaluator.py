"""
Tests for v0.7.0 access rule evaluator.

Tests the runtime evaluation of access rules including:
- Role checks: role(admin)
- Relationship traversal: owner.team_id
- Logical operators: AND/OR
- Comparison operators
"""

import pytest

from dazzle.http.specs import (
    AccessComparisonKind,
    AccessConditionSpec,
    AccessLogicalKind,
    AccessOperationKind,
    EntityAccessSpec,
    PermissionRuleSpec,
    VisibilityRuleSpec,
)
from dazzle.http.specs.auth import AccessAuthContext
from dazzle.render.access_evaluator import (
    AccessRuntimeContext,
    can_create,
    can_delete,
    can_read,
    can_update,
    evaluate_access_condition,
    evaluate_visibility,
    filter_visible_records,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def admin_context() -> AccessRuntimeContext:
    """Admin user context."""
    return AccessRuntimeContext(
        user_id="user-123",
        roles=["admin"],
        is_superuser=False,
    )


@pytest.fixture
def user_context() -> AccessRuntimeContext:
    """Regular user context."""
    return AccessRuntimeContext(
        user_id="user-456",
        roles=["user"],
        is_superuser=False,
    )


@pytest.fixture
def anonymous_context() -> AccessRuntimeContext:
    """Anonymous user context."""
    return AccessRuntimeContext(
        user_id=None,
        roles=[],
        is_superuser=False,
    )


@pytest.fixture
def superuser_context() -> AccessRuntimeContext:
    """Superuser context (bypasses all checks)."""
    return AccessRuntimeContext(
        user_id="superuser",
        roles=[],
        is_superuser=True,
    )


# =============================================================================
# Test Comparison Conditions
# =============================================================================


class TestComparisonConditions:
    """Test basic comparison conditions."""

    @pytest.mark.parametrize(
        ("field", "comparison_op", "value", "value_list", "match_record", "miss_record"),
        [
            (
                "owner_id",
                AccessComparisonKind.EQUALS,
                "current_user",
                None,
                {"id": "1", "owner_id": "user-456"},
                {"id": "2", "owner_id": "user-789"},
            ),
            (
                "status",
                AccessComparisonKind.EQUALS,
                "active",
                None,
                {"id": "1", "status": "active"},
                {"id": "2", "status": "inactive"},
            ),
            (
                "status",
                AccessComparisonKind.NOT_EQUALS,
                "deleted",
                None,
                {"id": "1", "status": "active"},
                {"id": "2", "status": "deleted"},
            ),
            (
                "priority",
                AccessComparisonKind.GREATER_THAN,
                5,
                None,
                {"id": "1", "priority": 10},
                {"id": "2", "priority": 3},
            ),
            (
                "category",
                AccessComparisonKind.IN,
                None,
                ["work", "personal", "urgent"],
                {"id": "1", "category": "work"},
                {"id": "2", "category": "archive"},
            ),
        ],
        ids=[
            "test_equals_current_user",
            "test_equals_literal",
            "test_not_equals",
            "test_greater_than",
            "test_in_operator",
        ],
    )
    def test_comparison(
        self,
        user_context: AccessRuntimeContext,
        field: str,
        comparison_op: AccessComparisonKind,
        value,
        value_list,
        match_record: dict,
        miss_record: dict,
    ):
        kwargs: dict = {
            "kind": "comparison",
            "field": field,
            "comparison_op": comparison_op,
        }
        if value is not None:
            kwargs["value"] = value
        if value_list is not None:
            kwargs["value_list"] = value_list
        condition = AccessConditionSpec(**kwargs)
        assert evaluate_access_condition(condition, match_record, user_context) is True
        assert evaluate_access_condition(condition, miss_record, user_context) is False


# =============================================================================
# Test Role Checks
# =============================================================================


class TestRoleChecks:
    """Test role(name) condition checks."""

    def test_role_check_matches(self, admin_context: AccessRuntimeContext):
        """Test that role(admin) matches admin user."""
        condition = AccessConditionSpec(
            kind="role_check",
            role_name="admin",
        )

        assert evaluate_access_condition(condition, {}, admin_context) is True

    def test_role_check_no_match(self, user_context: AccessRuntimeContext):
        """Test that role(admin) doesn't match regular user."""
        condition = AccessConditionSpec(
            kind="role_check",
            role_name="admin",
        )

        assert evaluate_access_condition(condition, {}, user_context) is False

    def test_superuser_bypasses_role_check(self, superuser_context: AccessRuntimeContext):
        """Test that superuser always passes role checks."""
        condition = AccessConditionSpec(
            kind="role_check",
            role_name="admin",
        )

        assert evaluate_access_condition(condition, {}, superuser_context) is True


# =============================================================================
# Test Logical Operators
# =============================================================================


class TestLogicalOperators:
    """Test AND/OR logical operators."""

    @pytest.mark.parametrize(
        ("logical_op", "left_field", "left_value", "context_name", "record", "expected"),
        [
            (
                AccessLogicalKind.AND,
                "status",
                "active",
                "admin_context",
                {"status": "active"},
                True,
            ),
            (
                AccessLogicalKind.AND,
                "status",
                "active",
                "user_context",
                {"status": "active"},
                False,
            ),
            (
                AccessLogicalKind.OR,
                "owner_id",
                "current_user",
                "user_context",
                {"owner_id": "user-456"},
                True,
            ),
            (
                AccessLogicalKind.OR,
                "owner_id",
                "current_user",
                "user_context",
                {"owner_id": "other-user"},
                False,
            ),
        ],
        ids=[
            "test_and_both_true",
            "test_and_one_false",
            "test_or_one_true",
            "test_or_both_false",
        ],
    )
    def test_logical(
        self,
        request: pytest.FixtureRequest,
        logical_op: AccessLogicalKind,
        left_field: str,
        left_value: str,
        context_name: str,
        record: dict,
        expected: bool,
    ):
        ctx = request.getfixturevalue(context_name)
        left = AccessConditionSpec(
            kind="comparison",
            field=left_field,
            comparison_op=AccessComparisonKind.EQUALS,
            value=left_value,
        )
        right = AccessConditionSpec(kind="role_check", role_name="admin")
        condition = AccessConditionSpec(
            kind="logical",
            logical_op=logical_op,
            logical_left=left,
            logical_right=right,
        )
        assert evaluate_access_condition(condition, record, ctx) is expected


# =============================================================================
# Test Visibility Rules
# =============================================================================


class TestVisibilityRules:
    """Test visibility rule evaluation."""

    def test_authenticated_visibility(self, user_context: AccessRuntimeContext):
        """Test visibility rule for authenticated users."""
        owner_condition = AccessConditionSpec(
            kind="comparison",
            field="owner_id",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_user",
        )
        access_spec = EntityAccessSpec(
            visibility=[
                VisibilityRuleSpec(
                    context=AccessAuthContext.AUTHENTICATED,
                    condition=owner_condition,
                )
            ],
            permissions=[],
        )

        own_record = {"id": "1", "owner_id": "user-456"}
        assert evaluate_visibility(access_spec, own_record, user_context) is True

        other_record = {"id": "2", "owner_id": "other-user"}
        assert evaluate_visibility(access_spec, other_record, user_context) is False

    def test_anonymous_visibility(self, anonymous_context: AccessRuntimeContext):
        """Test visibility rule for anonymous users."""
        public_condition = AccessConditionSpec(
            kind="comparison",
            field="is_public",
            comparison_op=AccessComparisonKind.EQUALS,
            value=True,
        )
        access_spec = EntityAccessSpec(
            visibility=[
                VisibilityRuleSpec(
                    context=AccessAuthContext.ANONYMOUS,
                    condition=public_condition,
                )
            ],
            permissions=[],
        )

        public_record = {"id": "1", "is_public": True}
        assert evaluate_visibility(access_spec, public_record, anonymous_context) is True

        private_record = {"id": "2", "is_public": False}
        assert evaluate_visibility(access_spec, private_record, anonymous_context) is False

    def test_superuser_sees_all(self, superuser_context: AccessRuntimeContext):
        """Test that superuser can see all records."""
        owner_condition = AccessConditionSpec(
            kind="comparison",
            field="owner_id",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_user",
        )
        access_spec = EntityAccessSpec(
            visibility=[
                VisibilityRuleSpec(
                    context=AccessAuthContext.AUTHENTICATED,
                    condition=owner_condition,
                )
            ],
            permissions=[],
        )

        other_record = {"id": "1", "owner_id": "other-user"}
        assert evaluate_visibility(access_spec, other_record, superuser_context) is True


# =============================================================================
# Test Permission Rules
# =============================================================================


class TestPermissionRules:
    """Test permission rule evaluation for write operations."""

    def test_create_permission_with_auth(self, user_context: AccessRuntimeContext):
        """Test create permission requiring authentication."""
        access_spec = EntityAccessSpec(
            visibility=[],
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.CREATE,
                    require_auth=True,
                    condition=None,  # Any authenticated user can create
                )
            ],
        )

        assert can_create(access_spec, user_context) is True

    def test_create_permission_denied_anonymous(self, anonymous_context: AccessRuntimeContext):
        """Test create permission denied for anonymous."""
        access_spec = EntityAccessSpec(
            visibility=[],
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.CREATE,
                    require_auth=True,
                    condition=None,
                )
            ],
        )

        assert can_create(access_spec, anonymous_context) is False

    def test_update_permission_owner_only(self, user_context: AccessRuntimeContext):
        """Test update permission for owner only."""
        owner_condition = AccessConditionSpec(
            kind="comparison",
            field="owner_id",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_user",
        )
        access_spec = EntityAccessSpec(
            visibility=[],
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.UPDATE,
                    require_auth=True,
                    condition=owner_condition,
                )
            ],
        )

        own_record = {"id": "1", "owner_id": "user-456"}
        assert can_update(access_spec, own_record, user_context) is True

        other_record = {"id": "2", "owner_id": "other-user"}
        assert can_update(access_spec, other_record, user_context) is False

    def test_delete_permission_admin_only(
        self,
        admin_context: AccessRuntimeContext,
        user_context: AccessRuntimeContext,
    ):
        """Test delete permission for admin role only."""
        role_condition = AccessConditionSpec(
            kind="role_check",
            role_name="admin",
        )
        access_spec = EntityAccessSpec(
            visibility=[],
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.DELETE,
                    require_auth=True,
                    condition=role_condition,
                )
            ],
        )

        record = {"id": "1", "title": "Some record"}

        # Admin can delete
        assert can_delete(access_spec, record, admin_context) is True

        # Regular user cannot delete
        assert can_delete(access_spec, record, user_context) is False


# =============================================================================
# Test Complex Access Patterns
# =============================================================================


class TestComplexAccessPatterns:
    """Test complex real-world access patterns."""

    def test_owner_or_admin_update(
        self,
        admin_context: AccessRuntimeContext,
        user_context: AccessRuntimeContext,
    ):
        """Test: owner_id = current_user or role(admin)."""
        owner_condition = AccessConditionSpec(
            kind="comparison",
            field="owner_id",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_user",
        )
        admin_condition = AccessConditionSpec(
            kind="role_check",
            role_name="admin",
        )
        or_condition = AccessConditionSpec(
            kind="logical",
            logical_op=AccessLogicalKind.OR,
            logical_left=owner_condition,
            logical_right=admin_condition,
        )

        access_spec = EntityAccessSpec(
            visibility=[],
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.UPDATE,
                    require_auth=True,
                    condition=or_condition,
                )
            ],
        )

        record = {"id": "1", "owner_id": "other-user"}

        # Admin can update any record
        assert can_update(access_spec, record, admin_context) is True

        # Owner can update their own record
        own_record = {"id": "2", "owner_id": "user-456"}
        assert can_update(access_spec, own_record, user_context) is True

        # Non-owner non-admin cannot update
        assert can_update(access_spec, record, user_context) is False

    def test_filter_visible_records(self, user_context: AccessRuntimeContext):
        """Test filtering a list of records by visibility."""
        owner_condition = AccessConditionSpec(
            kind="comparison",
            field="owner_id",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_user",
        )
        access_spec = EntityAccessSpec(
            visibility=[
                VisibilityRuleSpec(
                    context=AccessAuthContext.AUTHENTICATED,
                    condition=owner_condition,
                )
            ],
            permissions=[],
        )

        records = [
            {"id": "1", "owner_id": "user-456", "title": "My task"},
            {"id": "2", "owner_id": "other-user", "title": "Not mine"},
            {"id": "3", "owner_id": "user-456", "title": "Also mine"},
            {"id": "4", "owner_id": "someone", "title": "Not mine either"},
        ]

        visible = filter_visible_records(access_spec, records, user_context)

        assert len(visible) == 2
        assert all(r["owner_id"] == "user-456" for r in visible)


# =============================================================================
# Test Convenience Functions
# =============================================================================


class TestConvenienceFunctions:
    """Test can_read, can_create, can_update, can_delete functions."""

    def test_can_read_uses_visibility(self, user_context: AccessRuntimeContext):
        """Test that can_read uses visibility rules."""
        owner_condition = AccessConditionSpec(
            kind="comparison",
            field="owner_id",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_user",
        )
        access_spec = EntityAccessSpec(
            visibility=[
                VisibilityRuleSpec(
                    context=AccessAuthContext.AUTHENTICATED,
                    condition=owner_condition,
                )
            ],
            permissions=[],
        )

        own_record = {"id": "1", "owner_id": "user-456"}
        assert can_read(access_spec, own_record, user_context) is True

    def test_no_rules_defaults_to_allow(self, user_context: AccessRuntimeContext):
        """Test that no visibility rules means public access."""
        access_spec = EntityAccessSpec(
            visibility=[],
            permissions=[],
        )

        record = {"id": "1", "owner_id": "anyone"}
        assert can_read(access_spec, record, user_context) is True
