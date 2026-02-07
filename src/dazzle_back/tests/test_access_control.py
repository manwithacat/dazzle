"""
Tests for access control and row-level security.

Tests owner-based, tenant-based, and role-based access control.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from dazzle_back.runtime.access_control import (
    AccessContext,
    AccessDenied,
    AccessEnforcer,
    AccessOperation,
    AccessPolicy,
    AccessRule,
    PolicyRegistry,
    create_policy_from_entity,
    detect_owner_field,
    detect_tenant_field,
)

# =============================================================================
# AccessContext Tests
# =============================================================================


class TestAccessContext:
    """Tests for AccessContext."""

    def test_unauthenticated_context(self) -> None:
        """Test unauthenticated context."""
        context = AccessContext()

        assert context.is_authenticated is False
        assert context.is_tenant_scoped is False
        assert context.user_id is None

    def test_authenticated_context(self) -> None:
        """Test authenticated context."""
        user_id = uuid4()
        context = AccessContext(user_id=user_id)

        assert context.is_authenticated is True
        assert context.user_id == user_id

    def test_tenant_scoped_context(self) -> None:
        """Test tenant-scoped context."""
        tenant_id = uuid4()
        context = AccessContext(tenant_id=tenant_id)

        assert context.is_tenant_scoped is True
        assert context.tenant_id == tenant_id

    def test_has_role(self) -> None:
        """Test role checking."""
        context = AccessContext(roles=["admin", "editor"])

        assert context.has_role("admin") is True
        assert context.has_role("editor") is True
        assert context.has_role("viewer") is False

    def test_superuser_has_all_roles(self) -> None:
        """Test superuser has all roles."""
        context = AccessContext(is_superuser=True)

        assert context.has_role("admin") is True
        assert context.has_role("anything") is True


# =============================================================================
# AccessRule Tests
# =============================================================================


class TestAccessRule:
    """Tests for AccessRule evaluation."""

    def test_public_rule(self) -> None:
        """Test public access rule."""
        rule = AccessRule(operation=AccessOperation.READ, rule="public")
        context = AccessContext()  # Unauthenticated

        assert rule.evaluate(context) is True

    def test_authenticated_rule_with_user(self) -> None:
        """Test authenticated rule with logged-in user."""
        rule = AccessRule(operation=AccessOperation.READ, rule="authenticated")
        context = AccessContext(user_id=uuid4())

        assert rule.evaluate(context) is True

    def test_authenticated_rule_without_user(self) -> None:
        """Test authenticated rule without user."""
        rule = AccessRule(operation=AccessOperation.READ, rule="authenticated")
        context = AccessContext()

        assert rule.evaluate(context) is False

    def test_owner_rule_matching(self) -> None:
        """Test owner rule with matching owner."""
        user_id = uuid4()
        rule = AccessRule(
            operation=AccessOperation.READ,
            rule="owner",
            owner_field="owner_id",
        )
        context = AccessContext(user_id=user_id)
        record = {"id": uuid4(), "owner_id": user_id, "title": "Test"}

        assert rule.evaluate(context, record) is True

    def test_owner_rule_not_matching(self) -> None:
        """Test owner rule with different owner."""
        rule = AccessRule(
            operation=AccessOperation.READ,
            rule="owner",
            owner_field="owner_id",
        )
        context = AccessContext(user_id=uuid4())
        record = {"id": uuid4(), "owner_id": uuid4(), "title": "Test"}

        assert rule.evaluate(context, record) is False

    def test_owner_rule_create_without_record(self) -> None:
        """Test owner rule for create (no record yet)."""
        rule = AccessRule(
            operation=AccessOperation.CREATE,
            rule="owner",
            owner_field="owner_id",
        )
        context = AccessContext(user_id=uuid4())

        # Create should allow if authenticated
        assert rule.evaluate(context, None) is True

    def test_tenant_rule_matching(self) -> None:
        """Test tenant rule with matching tenant."""
        tenant_id = uuid4()
        rule = AccessRule(
            operation=AccessOperation.READ,
            rule="tenant",
            tenant_field="tenant_id",
        )
        context = AccessContext(tenant_id=tenant_id)
        record = {"id": uuid4(), "tenant_id": tenant_id}

        assert rule.evaluate(context, record) is True

    def test_tenant_rule_not_matching(self) -> None:
        """Test tenant rule with different tenant."""
        rule = AccessRule(
            operation=AccessOperation.READ,
            rule="tenant",
            tenant_field="tenant_id",
        )
        context = AccessContext(tenant_id=uuid4())
        record = {"id": uuid4(), "tenant_id": uuid4()}

        assert rule.evaluate(context, record) is False

    def test_role_rule_with_role(self) -> None:
        """Test role rule with matching role."""
        rule = AccessRule(operation=AccessOperation.DELETE, rule="role:admin")
        context = AccessContext(user_id=uuid4(), roles=["admin"])

        assert rule.evaluate(context) is True

    def test_role_rule_without_role(self) -> None:
        """Test role rule without matching role."""
        rule = AccessRule(operation=AccessOperation.DELETE, rule="role:admin")
        context = AccessContext(user_id=uuid4(), roles=["editor"])

        assert rule.evaluate(context) is False

    def test_superuser_bypasses_all(self) -> None:
        """Test superuser bypasses all rules."""
        rule = AccessRule(
            operation=AccessOperation.DELETE,
            rule="owner",
            owner_field="owner_id",
        )
        context = AccessContext(user_id=uuid4(), is_superuser=True)
        record = {"id": uuid4(), "owner_id": uuid4()}  # Different owner

        assert rule.evaluate(context, record) is True


# =============================================================================
# AccessPolicy Tests
# =============================================================================


class TestAccessPolicy:
    """Tests for AccessPolicy."""

    def test_create_public_policy(self) -> None:
        """Test creating public policy."""
        policy = AccessPolicy.create_public("Task")

        assert policy.entity_name == "Task"
        assert policy.can_access(AccessOperation.READ, AccessContext()) is True
        assert policy.can_access(AccessOperation.CREATE, AccessContext()) is True

    def test_create_authenticated_policy(self) -> None:
        """Test creating authenticated policy."""
        policy = AccessPolicy.create_authenticated("Task")
        context_anon = AccessContext()
        context_auth = AccessContext(user_id=uuid4())

        assert policy.can_access(AccessOperation.READ, context_anon) is False
        assert policy.can_access(AccessOperation.READ, context_auth) is True

    def test_create_owner_based_policy(self) -> None:
        """Test creating owner-based policy."""
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        user_id = uuid4()
        context = AccessContext(user_id=user_id)

        # Can create (authenticated)
        assert policy.can_access(AccessOperation.CREATE, context) is True

        # Can read own record
        own_record = {"id": uuid4(), "owner_id": user_id}
        assert policy.can_access(AccessOperation.READ, context, own_record) is True

        # Cannot read other's record
        other_record = {"id": uuid4(), "owner_id": uuid4()}
        assert policy.can_access(AccessOperation.READ, context, other_record) is False

    def test_create_tenant_based_policy(self) -> None:
        """Test creating tenant-based policy."""
        policy = AccessPolicy.create_tenant_based("Task", "tenant_id")
        tenant_id = uuid4()
        context = AccessContext(tenant_id=tenant_id)

        # Can read same tenant
        same_tenant = {"id": uuid4(), "tenant_id": tenant_id}
        assert policy.can_access(AccessOperation.READ, context, same_tenant) is True

        # Cannot read different tenant
        diff_tenant = {"id": uuid4(), "tenant_id": uuid4()}
        assert policy.can_access(AccessOperation.READ, context, diff_tenant) is False

    def test_get_list_filters_owner(self) -> None:
        """Test getting list filters for owner-based policy."""
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        user_id = uuid4()
        context = AccessContext(user_id=user_id)

        filters = policy.get_list_filters(context)

        assert filters == {"owner_id": user_id}

    def test_get_list_filters_tenant(self) -> None:
        """Test getting list filters for tenant-based policy."""
        policy = AccessPolicy.create_tenant_based("Task", "tenant_id")
        tenant_id = uuid4()
        context = AccessContext(tenant_id=tenant_id)

        filters = policy.get_list_filters(context)

        assert filters == {"tenant_id": tenant_id}


# =============================================================================
# PolicyRegistry Tests
# =============================================================================


class TestPolicyRegistry:
    """Tests for PolicyRegistry."""

    def test_register_and_get(self) -> None:
        """Test registering and getting policy."""
        registry = PolicyRegistry()
        policy = AccessPolicy.create_public("Task")

        registry.register(policy)

        assert registry.get("Task") == policy

    def test_get_missing_returns_none(self) -> None:
        """Test getting missing policy."""
        registry = PolicyRegistry()

        assert registry.get("NonExistent") is None

    def test_default_policy(self) -> None:
        """Test default policy fallback."""
        registry = PolicyRegistry()
        default = AccessPolicy.create_authenticated("Default")
        registry.set_default(default)

        # Missing entity returns default
        assert registry.get("NonExistent") == default

    def test_has_policy(self) -> None:
        """Test checking if policy exists."""
        registry = PolicyRegistry()
        policy = AccessPolicy.create_public("Task")
        registry.register(policy)

        assert registry.has_policy("Task") is True
        assert registry.has_policy("Other") is False


# =============================================================================
# AccessEnforcer Tests
# =============================================================================


class TestAccessEnforcer:
    """Tests for AccessEnforcer."""

    @pytest.fixture
    def user_context(self) -> Any:
        """Create a user context."""
        return AccessContext(user_id=uuid4())

    def test_check_create_injects_owner(self, user_context: Any) -> None:
        """Test create check injects owner_id."""
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = AccessEnforcer(policy, lambda: user_context)

        data = {"title": "Test Task"}
        result = enforcer.check_create(data)

        assert result["owner_id"] == user_context.user_id
        assert result["title"] == "Test Task"

    def test_check_create_denies_unauthenticated(self) -> None:
        """Test create check denies unauthenticated."""
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = AccessEnforcer(policy, lambda: AccessContext())

        with pytest.raises(AccessDenied) as exc_info:
            enforcer.check_create({"title": "Test"})

        assert exc_info.value.operation == AccessOperation.CREATE

    def test_check_read_allows_owner(self, user_context: Any) -> None:
        """Test read check allows owner."""
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = AccessEnforcer(policy, lambda: user_context)

        record = {"id": uuid4(), "owner_id": user_context.user_id}

        # Should not raise
        enforcer.check_read(record)

    def test_check_read_denies_non_owner(self, user_context: Any) -> None:
        """Test read check denies non-owner."""
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = AccessEnforcer(policy, lambda: user_context)

        record = {"id": uuid4(), "owner_id": uuid4()}  # Different owner

        with pytest.raises(AccessDenied) as exc_info:
            enforcer.check_read(record)

        assert exc_info.value.operation == AccessOperation.READ

    def test_check_update_denies_non_owner(self, user_context: Any) -> None:
        """Test update check denies non-owner."""
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = AccessEnforcer(policy, lambda: user_context)

        record = {"id": uuid4(), "owner_id": uuid4()}

        with pytest.raises(AccessDenied):
            enforcer.check_update(record)

    def test_check_delete_denies_non_owner(self, user_context: Any) -> None:
        """Test delete check denies non-owner."""
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = AccessEnforcer(policy, lambda: user_context)

        record = {"id": uuid4(), "owner_id": uuid4()}

        with pytest.raises(AccessDenied):
            enforcer.check_delete(record)

    def test_get_list_filters(self, user_context: Any) -> None:
        """Test getting list filters."""
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = AccessEnforcer(policy, lambda: user_context)

        filters = enforcer.get_list_filters()

        assert filters == {"owner_id": user_context.user_id}


# =============================================================================
# Field Detection Tests
# =============================================================================


class TestFieldDetection:
    """Tests for field detection functions."""

    def test_detect_owner_field_by_name(self) -> None:
        """Test detecting owner field by common names."""
        fields = [
            {"name": "id", "type": {"kind": "scalar"}},
            {"name": "owner_id", "type": {"kind": "scalar"}},
            {"name": "title", "type": {"kind": "scalar"}},
        ]

        assert detect_owner_field(fields) == "owner_id"

    def test_detect_owner_field_by_ref(self) -> None:
        """Test detecting owner field by User reference."""
        fields = [
            {"name": "id", "type": {"kind": "scalar"}},
            {"name": "author", "type": {"kind": "ref", "ref_entity": "User"}},
            {"name": "title", "type": {"kind": "scalar"}},
        ]

        assert detect_owner_field(fields) == "author"

    def test_detect_owner_field_not_found(self) -> None:
        """Test no owner field detected."""
        fields = [
            {"name": "id", "type": {"kind": "scalar"}},
            {"name": "title", "type": {"kind": "scalar"}},
        ]

        assert detect_owner_field(fields) is None

    def test_detect_tenant_field(self) -> None:
        """Test detecting tenant field."""
        fields = [
            {"name": "id", "type": {"kind": "scalar"}},
            {"name": "tenant_id", "type": {"kind": "scalar"}},
            {"name": "title", "type": {"kind": "scalar"}},
        ]

        assert detect_tenant_field(fields) == "tenant_id"

    def test_detect_tenant_field_org(self) -> None:
        """Test detecting organization_id as tenant field."""
        fields = [
            {"name": "id", "type": {"kind": "scalar"}},
            {"name": "organization_id", "type": {"kind": "scalar"}},
        ]

        assert detect_tenant_field(fields) == "organization_id"


# =============================================================================
# Policy Creation from Entity Tests
# =============================================================================


class TestCreatePolicyFromEntity:
    """Tests for create_policy_from_entity."""

    def test_creates_owner_policy_if_owner_field(self) -> None:
        """Test creates owner policy when owner field detected."""
        fields = [
            {"name": "id", "type": {"kind": "scalar"}},
            {"name": "owner_id", "type": {"kind": "ref", "ref_entity": "User"}},
            {"name": "title", "type": {"kind": "scalar"}},
        ]

        policy = create_policy_from_entity("Task", fields)

        assert policy.entity_name == "Task"
        assert policy.owner_field == "owner_id"

    def test_creates_tenant_policy_if_tenant_field(self) -> None:
        """Test creates tenant policy when tenant field detected."""
        fields = [
            {"name": "id", "type": {"kind": "scalar"}},
            {"name": "tenant_id", "type": {"kind": "scalar"}},
            {"name": "name", "type": {"kind": "scalar"}},
        ]

        policy = create_policy_from_entity("Project", fields)

        assert policy.entity_name == "Project"
        assert policy.tenant_field == "tenant_id"

    def test_creates_public_policy_by_default(self) -> None:
        """Test creates public policy when no special fields."""
        fields = [
            {"name": "id", "type": {"kind": "scalar"}},
            {"name": "name", "type": {"kind": "scalar"}},
        ]

        policy = create_policy_from_entity("Category", fields)

        # Should allow public access
        assert policy.can_access(AccessOperation.READ, AccessContext()) is True

    def test_creates_authenticated_policy_when_specified(self) -> None:
        """Test creates authenticated policy when requested."""
        fields = [
            {"name": "id", "type": {"kind": "scalar"}},
            {"name": "name", "type": {"kind": "scalar"}},
        ]

        policy = create_policy_from_entity("Secret", fields, default_mode="authenticated")

        # Should require authentication
        assert policy.can_access(AccessOperation.READ, AccessContext()) is False
        assert policy.can_access(AccessOperation.READ, AccessContext(user_id=uuid4())) is True
