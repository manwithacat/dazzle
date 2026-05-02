"""Tests for #957 cycle 2 — admin_personas tenant-filter bypass.

`AccessContext.tenant_admin_personas` lets persona-named users (e.g.
`super_admin`, `support`) read records across tenants. The bypass
applies in two places:

  1. `AccessRule.evaluate(rule="tenant", ...)` — returns True even
     when the record's tenant_id doesn't match the context's tenant_id.
  2. `AccessPolicy.get_list_filters()` — omits the tenant_id filter so
     SELECT queries return cross-tenant rows.

Cycle 1 (#957) shipped the DSL surface (`TenancySpec.admin_personas`).
Cycle 2 wires the runtime check. Cycle 3+ will add the request
middleware that populates `tenant_admin_personas` from the active
`TenancySpec` × the user's personas.
"""

from __future__ import annotations

from uuid import uuid4

from dazzle_back.runtime.access_control import (
    AccessContext,
    AccessOperation,
    AccessPolicy,
    AccessRule,
)


class TestBypassProperty:
    def test_default_no_bypass(self) -> None:
        ctx = AccessContext(user_id=uuid4(), tenant_id=uuid4())
        assert ctx.bypasses_tenant_filter is False

    def test_persona_match_triggers_bypass(self) -> None:
        ctx = AccessContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            roles=["support"],
            tenant_admin_personas=["super_admin", "support"],
        )
        assert ctx.bypasses_tenant_filter is True

    def test_persona_mismatch_no_bypass(self) -> None:
        ctx = AccessContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            roles=["teacher"],
            tenant_admin_personas=["super_admin", "support"],
        )
        assert ctx.bypasses_tenant_filter is False

    def test_superuser_always_bypasses(self) -> None:
        ctx = AccessContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            is_superuser=True,
            tenant_admin_personas=[],
        )
        assert ctx.bypasses_tenant_filter is True

    def test_empty_admin_personas_means_no_bypass_even_with_roles(self) -> None:
        ctx = AccessContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            roles=["super_admin"],
            tenant_admin_personas=[],  # Tenancy hasn't declared any
        )
        assert ctx.bypasses_tenant_filter is False


class TestRuleEvaluation:
    def test_tenant_rule_bypassed_for_admin_persona(self) -> None:
        rule = AccessRule(
            operation=AccessOperation.READ,
            rule="tenant",
            tenant_field="tenant_id",
        )
        ctx = AccessContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            roles=["support"],
            tenant_admin_personas=["support"],
        )
        # Record belongs to a *different* tenant than the context.
        record = {"tenant_id": str(uuid4())}
        assert rule.evaluate(ctx, record) is True

    def test_tenant_rule_still_filters_for_non_admin(self) -> None:
        rule = AccessRule(
            operation=AccessOperation.READ,
            rule="tenant",
            tenant_field="tenant_id",
        )
        ctx = AccessContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            roles=["teacher"],
            tenant_admin_personas=["super_admin"],
        )
        # Record belongs to a *different* tenant than the context.
        record = {"tenant_id": str(uuid4())}
        assert rule.evaluate(ctx, record) is False

    def test_admin_bypass_works_without_tenant_id_in_context(self) -> None:
        # Cross-tenant admins might not have a single tenant_id pinned.
        rule = AccessRule(
            operation=AccessOperation.READ,
            rule="tenant",
            tenant_field="tenant_id",
        )
        ctx = AccessContext(
            user_id=uuid4(),
            tenant_id=None,
            roles=["super_admin"],
            tenant_admin_personas=["super_admin"],
        )
        record = {"tenant_id": str(uuid4())}
        assert rule.evaluate(ctx, record) is True


class TestListFilters:
    def test_admin_persona_omits_tenant_filter(self) -> None:
        policy = AccessPolicy.create_tenant_based("Manuscript")
        ctx = AccessContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            roles=["support"],
            tenant_admin_personas=["support"],
        )
        filters = policy.get_list_filters(ctx)
        assert "tenant_id" not in filters

    def test_non_admin_keeps_tenant_filter(self) -> None:
        policy = AccessPolicy.create_tenant_based("Manuscript")
        tenant = uuid4()
        ctx = AccessContext(
            user_id=uuid4(),
            tenant_id=tenant,
            roles=["teacher"],
            tenant_admin_personas=["super_admin"],
        )
        filters = policy.get_list_filters(ctx)
        assert filters.get("tenant_id") == tenant

    def test_default_context_keeps_tenant_filter(self) -> None:
        # Backward compat: contexts created without admin_personas keep
        # the cycle-1 behaviour exactly.
        policy = AccessPolicy.create_tenant_based("Manuscript")
        tenant = uuid4()
        ctx = AccessContext(user_id=uuid4(), tenant_id=tenant)
        filters = policy.get_list_filters(ctx)
        assert filters.get("tenant_id") == tenant
