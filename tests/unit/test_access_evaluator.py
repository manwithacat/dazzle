"""
Tests for v0.7.0 access rule evaluator.

Tests the runtime evaluation of access rules including:
- Role checks: role(admin)
- Relationship traversal: owner.team_id
- Logical operators: AND/OR
- Comparison operators
"""

import pytest

from dazzle_dnr_back.runtime.access_evaluator import (
    AccessRuntimeContext,
    can_create,
    can_delete,
    can_read,
    can_update,
    evaluate_access_condition,
    evaluate_visibility,
    filter_visible_records,
)
from dazzle_dnr_back.specs import (
    AccessComparisonKind,
    AccessConditionSpec,
    AccessLogicalKind,
    AccessOperationKind,
    EntityAccessSpec,
    PermissionRuleSpec,
    VisibilityRuleSpec,
)
from dazzle_dnr_back.specs.auth import AccessAuthContext

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

    def test_equals_current_user(self, user_context: AccessRuntimeContext):
        """Test owner_id = current_user comparison."""
        condition = AccessConditionSpec(
            kind="comparison",
            field="owner_id",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_user",
        )

        record = {"id": "1", "owner_id": "user-456"}
        assert evaluate_access_condition(condition, record, user_context) is True

        other_record = {"id": "2", "owner_id": "user-789"}
        assert evaluate_access_condition(condition, other_record, user_context) is False

    def test_equals_literal(self, user_context: AccessRuntimeContext):
        """Test field = literal comparison."""
        condition = AccessConditionSpec(
            kind="comparison",
            field="status",
            comparison_op=AccessComparisonKind.EQUALS,
            value="active",
        )

        active_record = {"id": "1", "status": "active"}
        assert evaluate_access_condition(condition, active_record, user_context) is True

        inactive_record = {"id": "2", "status": "inactive"}
        assert evaluate_access_condition(condition, inactive_record, user_context) is False

    def test_not_equals(self, user_context: AccessRuntimeContext):
        """Test != operator."""
        condition = AccessConditionSpec(
            kind="comparison",
            field="status",
            comparison_op=AccessComparisonKind.NOT_EQUALS,
            value="deleted",
        )

        active_record = {"id": "1", "status": "active"}
        assert evaluate_access_condition(condition, active_record, user_context) is True

        deleted_record = {"id": "2", "status": "deleted"}
        assert evaluate_access_condition(condition, deleted_record, user_context) is False

    def test_greater_than(self, user_context: AccessRuntimeContext):
        """Test > operator for numeric comparison."""
        condition = AccessConditionSpec(
            kind="comparison",
            field="priority",
            comparison_op=AccessComparisonKind.GREATER_THAN,
            value=5,
        )

        high_priority = {"id": "1", "priority": 10}
        assert evaluate_access_condition(condition, high_priority, user_context) is True

        low_priority = {"id": "2", "priority": 3}
        assert evaluate_access_condition(condition, low_priority, user_context) is False

    def test_in_operator(self, user_context: AccessRuntimeContext):
        """Test IN operator with value list."""
        condition = AccessConditionSpec(
            kind="comparison",
            field="category",
            comparison_op=AccessComparisonKind.IN,
            value_list=["work", "personal", "urgent"],
        )

        work_record = {"id": "1", "category": "work"}
        assert evaluate_access_condition(condition, work_record, user_context) is True

        other_record = {"id": "2", "category": "archive"}
        assert evaluate_access_condition(condition, other_record, user_context) is False


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

    def test_and_both_true(self, admin_context: AccessRuntimeContext):
        """Test AND where both conditions are true."""
        left = AccessConditionSpec(
            kind="comparison",
            field="status",
            comparison_op=AccessComparisonKind.EQUALS,
            value="active",
        )
        right = AccessConditionSpec(
            kind="role_check",
            role_name="admin",
        )
        condition = AccessConditionSpec(
            kind="logical",
            logical_op=AccessLogicalKind.AND,
            logical_left=left,
            logical_right=right,
        )

        record = {"status": "active"}
        assert evaluate_access_condition(condition, record, admin_context) is True

    def test_and_one_false(self, user_context: AccessRuntimeContext):
        """Test AND where one condition is false."""
        left = AccessConditionSpec(
            kind="comparison",
            field="status",
            comparison_op=AccessComparisonKind.EQUALS,
            value="active",
        )
        right = AccessConditionSpec(
            kind="role_check",
            role_name="admin",
        )
        condition = AccessConditionSpec(
            kind="logical",
            logical_op=AccessLogicalKind.AND,
            logical_left=left,
            logical_right=right,
        )

        record = {"status": "active"}
        # Status matches but user is not admin
        assert evaluate_access_condition(condition, record, user_context) is False

    def test_or_one_true(self, user_context: AccessRuntimeContext):
        """Test OR where one condition is true."""
        left = AccessConditionSpec(
            kind="comparison",
            field="owner_id",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_user",
        )
        right = AccessConditionSpec(
            kind="role_check",
            role_name="admin",
        )
        condition = AccessConditionSpec(
            kind="logical",
            logical_op=AccessLogicalKind.OR,
            logical_left=left,
            logical_right=right,
        )

        record = {"owner_id": "user-456"}  # Matches user context
        assert evaluate_access_condition(condition, record, user_context) is True

    def test_or_both_false(self, user_context: AccessRuntimeContext):
        """Test OR where both conditions are false."""
        left = AccessConditionSpec(
            kind="comparison",
            field="owner_id",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_user",
        )
        right = AccessConditionSpec(
            kind="role_check",
            role_name="admin",
        )
        condition = AccessConditionSpec(
            kind="logical",
            logical_op=AccessLogicalKind.OR,
            logical_left=left,
            logical_right=right,
        )

        record = {"owner_id": "other-user"}  # Doesn't match
        assert evaluate_access_condition(condition, record, user_context) is False


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
