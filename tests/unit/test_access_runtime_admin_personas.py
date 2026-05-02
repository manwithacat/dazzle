"""Tests for #957 cycle 4 — `AccessRuntimeContext.tenant_admin_personas`.

Cycle 3 made `AppSpec.tenancy.admin_personas` reachable from the
runtime. Cycle 4 extends `AccessRuntimeContext` (the production Cedar
context) with a `tenant_admin_personas` field and a
`bypasses_tenant_filter` property — mirroring the cycle-2 work on the
pydantic `AccessContext` so both paths can short-circuit cross-tenant
scope predicates uniformly.

Cycle 5 will thread `admin_personas` from each route_generator call
site's enclosing scope. Until then, omitting the parameter keeps prior
behaviour exactly.
"""

from __future__ import annotations

from uuid import uuid4

from dazzle.core.access import AccessRuntimeContext


class TestRolesAndBypassDefaults:
    def test_default_no_admin_personas(self) -> None:
        ctx = AccessRuntimeContext(user_id=str(uuid4()), roles=["teacher"])
        assert ctx.tenant_admin_personas == frozenset()
        assert ctx.bypasses_tenant_filter is False

    def test_explicit_empty_no_bypass(self) -> None:
        ctx = AccessRuntimeContext(
            user_id=str(uuid4()),
            roles=["super_admin"],  # Has the role…
            tenant_admin_personas=[],  # …but tenancy hasn't whitelisted it.
        )
        assert ctx.bypasses_tenant_filter is False

    def test_persona_match_triggers_bypass(self) -> None:
        ctx = AccessRuntimeContext(
            user_id=str(uuid4()),
            roles=["support"],
            tenant_admin_personas=["super_admin", "support"],
        )
        assert ctx.bypasses_tenant_filter is True

    def test_persona_mismatch_no_bypass(self) -> None:
        ctx = AccessRuntimeContext(
            user_id=str(uuid4()),
            roles=["teacher"],
            tenant_admin_personas=["super_admin", "support"],
        )
        assert ctx.bypasses_tenant_filter is False

    def test_superuser_always_bypasses(self) -> None:
        ctx = AccessRuntimeContext(
            user_id=str(uuid4()),
            roles=[],
            is_superuser=True,
            tenant_admin_personas=[],
        )
        assert ctx.bypasses_tenant_filter is True


class TestBackwardCompat:
    def test_omitting_admin_personas_preserves_default(self) -> None:
        # Existing callers who don't pass admin_personas must see the
        # exact pre-cycle-4 behaviour: empty admin set, no bypass.
        ctx = AccessRuntimeContext(
            user_id=str(uuid4()),
            roles=["teacher"],
            is_superuser=False,
        )
        assert ctx.tenant_admin_personas == frozenset()
        assert ctx.bypasses_tenant_filter is False

    def test_has_role_unchanged(self) -> None:
        ctx = AccessRuntimeContext(
            user_id=str(uuid4()),
            roles=["teacher", "marker"],
            tenant_admin_personas=["super_admin"],
        )
        # has_role must keep ignoring tenant_admin_personas — the
        # admin set only affects the tenant-filter bypass, not the
        # general role check.
        assert ctx.has_role("teacher") is True
        assert ctx.has_role("super_admin") is False
