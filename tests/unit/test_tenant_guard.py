"""Cross-tenant guard tests (#1289 slice 5)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from dazzle.http.runtime.tenant.guard import (
    ApexCookieNotSuperAdmin,
    CrossTenantForbidden,
    GuardOutcome,
    HostCookieMissingTenant,
    check_cross_tenant,
)
from dazzle.http.runtime.tenant.resolver import ResolvedTenant


def _tenant(slug: str = "acme") -> ResolvedTenant:
    return ResolvedTenant(kind="Trust", id=uuid4(), slug=slug, name=slug.title())


def test_host_cookie_matching_tenant_passes():
    out = check_cross_tenant(
        cookie_kind="host",
        session_tenant_slug="acme",
        request_tenant=_tenant("acme"),
        user_role="member",
        super_admin_role="super_admin",
    )
    assert out is GuardOutcome.PASS


def test_host_cookie_mismatched_tenant_raises():
    with pytest.raises(CrossTenantForbidden):
        check_cross_tenant(
            cookie_kind="host",
            session_tenant_slug="acme",
            request_tenant=_tenant("other"),
            user_role="member",
            super_admin_role="super_admin",
        )


def test_host_cookie_on_apex_raises():
    with pytest.raises(HostCookieMissingTenant):
        check_cross_tenant(
            cookie_kind="host",
            session_tenant_slug="acme",
            request_tenant=None,
            user_role="member",
            super_admin_role="super_admin",
        )


def test_apex_cookie_with_super_admin_passes_for_any_tenant():
    out = check_cross_tenant(
        cookie_kind="apex",
        session_tenant_slug=None,
        request_tenant=_tenant("acme"),
        user_role="super_admin",
        super_admin_role="super_admin",
    )
    assert out is GuardOutcome.PASS


def test_apex_cookie_without_super_admin_raises():
    with pytest.raises(ApexCookieNotSuperAdmin):
        check_cross_tenant(
            cookie_kind="apex",
            session_tenant_slug=None,
            request_tenant=_tenant("acme"),
            user_role="member",
            super_admin_role="super_admin",
        )


def test_no_cookie_present_passes_through():
    """Unauthenticated requests don't trip the guard; auth itself decides."""
    out = check_cross_tenant(
        cookie_kind=None,
        session_tenant_slug=None,
        request_tenant=_tenant("acme"),
        user_role="",
        super_admin_role="super_admin",
    )
    assert out is GuardOutcome.PASS


def test_apex_cookie_with_super_admin_passes_on_apex_request():
    """Super admin on the apex domain itself (no tenant resolved) — still passes."""
    out = check_cross_tenant(
        cookie_kind="apex",
        session_tenant_slug=None,
        request_tenant=None,
        user_role="super_admin",
        super_admin_role="super_admin",
    )
    assert out is GuardOutcome.PASS
