"""Tests for access control module (#coverage)."""

from __future__ import annotations

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

# ---------------------------------------------------------------------------
# AccessContext
# ---------------------------------------------------------------------------


class TestAccessContext:
    def test_unauthenticated(self) -> None:
        ctx = AccessContext()
        assert not ctx.is_authenticated
        assert not ctx.is_tenant_scoped

    def test_authenticated(self) -> None:
        ctx = AccessContext(user_id=uuid4())
        assert ctx.is_authenticated

    def test_tenant_scoped(self) -> None:
        ctx = AccessContext(tenant_id=uuid4())
        assert ctx.is_tenant_scoped

    def test_has_role(self) -> None:
        ctx = AccessContext(roles=["admin", "editor"])
        assert ctx.has_role("admin")
        assert ctx.has_role("editor")
        assert not ctx.has_role("viewer")

    def test_superuser_has_all_roles(self) -> None:
        ctx = AccessContext(is_superuser=True)
        assert ctx.has_role("anything")


# ---------------------------------------------------------------------------
# AccessRule.evaluate
# ---------------------------------------------------------------------------


class TestAccessRuleEvaluate:
    def test_public_rule(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="public")
        assert rule.evaluate(AccessContext()) is True

    def test_authenticated_rule_no_user(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="authenticated")
        assert rule.evaluate(AccessContext()) is False

    def test_authenticated_rule_with_user(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="authenticated")
        assert rule.evaluate(AccessContext(user_id=uuid4())) is True

    def test_owner_rule_matching(self) -> None:
        uid = uuid4()
        rule = AccessRule(operation=AccessOperation.READ, rule="owner", owner_field="owner_id")
        record = {"owner_id": str(uid)}
        assert rule.evaluate(AccessContext(user_id=uid), record) is True

    def test_owner_rule_not_matching(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="owner", owner_field="owner_id")
        record = {"owner_id": str(uuid4())}
        assert rule.evaluate(AccessContext(user_id=uuid4()), record) is False

    def test_owner_rule_create_without_record(self) -> None:
        rule = AccessRule(operation=AccessOperation.CREATE, rule="owner")
        assert rule.evaluate(AccessContext(user_id=uuid4()), None) is True

    def test_owner_rule_read_without_record(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="owner")
        assert rule.evaluate(AccessContext(user_id=uuid4()), None) is False

    def test_owner_rule_no_owner_field(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="owner")
        assert rule.evaluate(AccessContext(user_id=uuid4()), {"x": 1}) is False

    def test_owner_rule_null_owner_value(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="owner", owner_field="owner_id")
        assert rule.evaluate(AccessContext(user_id=uuid4()), {"owner_id": None}) is False

    def test_owner_rule_unauthenticated(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="owner", owner_field="owner_id")
        assert rule.evaluate(AccessContext(), {"owner_id": "x"}) is False

    def test_tenant_rule_matching(self) -> None:
        tid = uuid4()
        rule = AccessRule(operation=AccessOperation.READ, rule="tenant", tenant_field="tenant_id")
        record = {"tenant_id": str(tid)}
        assert rule.evaluate(AccessContext(tenant_id=tid), record) is True

    def test_tenant_rule_not_matching(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="tenant", tenant_field="tenant_id")
        record = {"tenant_id": str(uuid4())}
        assert rule.evaluate(AccessContext(tenant_id=uuid4()), record) is False

    def test_tenant_rule_no_tenant_context(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="tenant", tenant_field="tenant_id")
        assert rule.evaluate(AccessContext(), {"tenant_id": "x"}) is False

    def test_tenant_rule_create_without_record(self) -> None:
        rule = AccessRule(operation=AccessOperation.CREATE, rule="tenant", tenant_field="tenant_id")
        assert rule.evaluate(AccessContext(tenant_id=uuid4()), None) is True

    def test_tenant_rule_no_tenant_field(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="tenant")
        assert rule.evaluate(AccessContext(tenant_id=uuid4()), {"x": 1}) is False

    def test_tenant_rule_null_tenant_value(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="tenant", tenant_field="tenant_id")
        assert rule.evaluate(AccessContext(tenant_id=uuid4()), {"tenant_id": None}) is False

    def test_role_rule_matching(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="role:admin")
        assert rule.evaluate(AccessContext(roles=["admin"])) is True

    def test_role_rule_not_matching(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="role:admin")
        assert rule.evaluate(AccessContext(roles=["editor"])) is False

    def test_superuser_bypasses_all(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="owner", owner_field="owner_id")
        record = {"owner_id": str(uuid4())}
        assert rule.evaluate(AccessContext(is_superuser=True), record) is True

    def test_unknown_rule_denied(self) -> None:
        rule = AccessRule(operation=AccessOperation.READ, rule="custom_rule")
        assert rule.evaluate(AccessContext(user_id=uuid4())) is False


# ---------------------------------------------------------------------------
# AccessPolicy
# ---------------------------------------------------------------------------


class TestAccessPolicy:
    def test_public_policy(self) -> None:
        policy = AccessPolicy.create_public("Task")
        ctx = AccessContext()
        for op in AccessOperation:
            assert policy.can_access(op, ctx) is True

    def test_authenticated_policy(self) -> None:
        policy = AccessPolicy.create_authenticated("Task")
        assert policy.can_access(AccessOperation.READ, AccessContext()) is False
        assert policy.can_access(AccessOperation.READ, AccessContext(user_id=uuid4())) is True

    def test_owner_based_policy(self) -> None:
        uid = uuid4()
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        ctx = AccessContext(user_id=uid)
        record = {"owner_id": str(uid)}
        assert policy.can_access(AccessOperation.CREATE, ctx) is True
        assert policy.can_access(AccessOperation.READ, ctx, record) is True
        assert policy.can_access(AccessOperation.UPDATE, ctx, record) is True
        assert policy.can_access(AccessOperation.DELETE, ctx, record) is True

    def test_owner_based_denies_others(self) -> None:
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        record = {"owner_id": str(uuid4())}
        assert (
            policy.can_access(AccessOperation.READ, AccessContext(user_id=uuid4()), record) is False
        )

    def test_tenant_based_policy(self) -> None:
        tid = uuid4()
        policy = AccessPolicy.create_tenant_based("Task", "tenant_id")
        ctx = AccessContext(tenant_id=tid)
        record = {"tenant_id": str(tid)}
        for op in AccessOperation:
            assert policy.can_access(op, ctx, record) is True

    def test_no_rule_denies(self) -> None:
        policy = AccessPolicy(entity_name="Task")
        assert policy.can_access(AccessOperation.READ, AccessContext(user_id=uuid4())) is False

    def test_get_list_filters_owner(self) -> None:
        uid = uuid4()
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        filters = policy.get_list_filters(AccessContext(user_id=uid))
        assert filters == {"owner_id": uid}

    def test_get_list_filters_tenant(self) -> None:
        tid = uuid4()
        policy = AccessPolicy.create_tenant_based("Task", "tenant_id")
        filters = policy.get_list_filters(AccessContext(tenant_id=tid))
        assert filters == {"tenant_id": tid}

    def test_get_list_filters_no_rule(self) -> None:
        policy = AccessPolicy(entity_name="Task")
        assert policy.get_list_filters(AccessContext()) == {}


# ---------------------------------------------------------------------------
# PolicyRegistry
# ---------------------------------------------------------------------------


class TestPolicyRegistry:
    def test_register_and_get(self) -> None:
        registry = PolicyRegistry()
        policy = AccessPolicy.create_public("Task")
        registry.register(policy)
        assert registry.get("Task") is policy

    def test_get_unknown_returns_none(self) -> None:
        registry = PolicyRegistry()
        assert registry.get("Unknown") is None

    def test_default_policy(self) -> None:
        registry = PolicyRegistry()
        default = AccessPolicy.create_authenticated("_default")
        registry.set_default(default)
        assert registry.get("Unknown") is default

    def test_has_policy(self) -> None:
        registry = PolicyRegistry()
        registry.register(AccessPolicy.create_public("Task"))
        assert registry.has_policy("Task") is True
        assert registry.has_policy("Other") is False


# ---------------------------------------------------------------------------
# AccessEnforcer
# ---------------------------------------------------------------------------


class TestAccessEnforcer:
    def _enforcer(self, policy: AccessPolicy, **ctx_kwargs: object) -> AccessEnforcer:
        ctx = AccessContext(**ctx_kwargs)  # type: ignore[arg-type]
        return AccessEnforcer(policy, lambda: ctx)

    def test_check_create_allowed(self) -> None:
        policy = AccessPolicy.create_authenticated("Task")
        enforcer = self._enforcer(policy, user_id=uuid4())
        data = enforcer.check_create({"title": "Test"})
        assert data["title"] == "Test"

    def test_check_create_injects_owner(self) -> None:
        uid = uuid4()
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = self._enforcer(policy, user_id=uid)
        data = enforcer.check_create({"title": "Test"})
        assert data["owner_id"] == uid

    def test_check_create_injects_tenant(self) -> None:
        tid = uuid4()
        policy = AccessPolicy.create_tenant_based("Task", "tenant_id")
        enforcer = self._enforcer(policy, tenant_id=tid)
        data = enforcer.check_create({"title": "Test"})
        assert data["tenant_id"] == tid

    def test_check_create_denied(self) -> None:
        policy = AccessPolicy.create_authenticated("Task")
        enforcer = self._enforcer(policy)
        with pytest.raises(AccessDenied):
            enforcer.check_create({"title": "Test"})

    def test_check_read_allowed(self) -> None:
        uid = uuid4()
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = self._enforcer(policy, user_id=uid)
        enforcer.check_read({"owner_id": str(uid)})  # should not raise

    def test_check_read_denied(self) -> None:
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = self._enforcer(policy, user_id=uuid4())
        with pytest.raises(AccessDenied):
            enforcer.check_read({"owner_id": str(uuid4())})

    def test_check_read_none_record(self) -> None:
        policy = AccessPolicy.create_authenticated("Task")
        enforcer = self._enforcer(policy, user_id=uuid4())
        enforcer.check_read(None)  # should not raise

    def test_check_update_denied(self) -> None:
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = self._enforcer(policy, user_id=uuid4())
        with pytest.raises(AccessDenied):
            enforcer.check_update({"owner_id": str(uuid4())})

    def test_check_delete_denied(self) -> None:
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = self._enforcer(policy, user_id=uuid4())
        with pytest.raises(AccessDenied):
            enforcer.check_delete({"owner_id": str(uuid4())})

    def test_get_list_filters(self) -> None:
        uid = uuid4()
        policy = AccessPolicy.create_owner_based("Task", "owner_id")
        enforcer = self._enforcer(policy, user_id=uid)
        assert enforcer.get_list_filters() == {"owner_id": uid}


# ---------------------------------------------------------------------------
# AccessDenied exception
# ---------------------------------------------------------------------------


class TestAccessDenied:
    def test_message_format(self) -> None:
        exc = AccessDenied(AccessOperation.READ, "Task", "Not allowed")
        assert "read" in str(exc)
        assert "Task" in str(exc)
        assert exc.operation == AccessOperation.READ
        assert exc.entity == "Task"


# ---------------------------------------------------------------------------
# Field detection
# ---------------------------------------------------------------------------


class TestFieldDetection:
    def test_detect_owner_field_by_name(self) -> None:
        fields = [
            {"name": "id", "type": {}},
            {"name": "owner_id", "type": {}},
        ]
        assert detect_owner_field(fields) == "owner_id"

    def test_detect_owner_field_created_by(self) -> None:
        fields = [{"name": "created_by", "type": {}}]
        assert detect_owner_field(fields) == "created_by"

    def test_detect_owner_field_by_ref(self) -> None:
        fields = [
            {"name": "author", "type": {"kind": "ref", "ref_entity": "User"}},
        ]
        assert detect_owner_field(fields) == "author"

    def test_detect_owner_field_none(self) -> None:
        fields = [{"name": "title", "type": {}}]
        assert detect_owner_field(fields) is None

    def test_detect_tenant_field(self) -> None:
        fields = [{"name": "tenant_id", "type": {}}]
        assert detect_tenant_field(fields) == "tenant_id"

    def test_detect_tenant_field_org(self) -> None:
        fields = [{"name": "organization_id", "type": {}}]
        assert detect_tenant_field(fields) == "organization_id"

    def test_detect_tenant_field_none(self) -> None:
        fields = [{"name": "title", "type": {}}]
        assert detect_tenant_field(fields) is None


# ---------------------------------------------------------------------------
# create_policy_from_entity
# ---------------------------------------------------------------------------


class TestCreatePolicyFromEntity:
    def test_with_owner_field(self) -> None:
        fields = [{"name": "owner_id", "type": {}}]
        policy = create_policy_from_entity("Task", fields)
        assert policy.owner_field == "owner_id"

    def test_with_tenant_field(self) -> None:
        fields = [{"name": "tenant_id", "type": {}}]
        policy = create_policy_from_entity("Task", fields)
        assert policy.tenant_field == "tenant_id"

    def test_default_public(self) -> None:
        fields = [{"name": "title", "type": {}}]
        policy = create_policy_from_entity("Task", fields)
        assert policy.can_access(AccessOperation.READ, AccessContext()) is True

    def test_default_authenticated(self) -> None:
        fields = [{"name": "title", "type": {}}]
        policy = create_policy_from_entity("Task", fields, default_mode="authenticated")
        assert policy.can_access(AccessOperation.READ, AccessContext()) is False
