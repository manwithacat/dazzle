"""Cross-tenant guard tests (#1289 slice 5; id-based rework #1518)."""

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


def test_host_cookie_matching_tenant_passes():
    tid = str(uuid4())
    out = check_cross_tenant(
        cookie_kind="host",
        session_tenant_id=tid,
        request_tenant_id=tid,
        user_role="member",
        super_admin_role="super_admin",
    )
    assert out is GuardOutcome.PASS


def test_host_cookie_ancestor_membership_passes():
    """ADR-0037: a member of an ancestor (e.g. Trust root) reaches a descendant host."""
    root = str(uuid4())
    leaf = str(uuid4())
    out = check_cross_tenant(
        cookie_kind="host",
        session_tenant_id=root,
        request_tenant_id=leaf,
        request_ancestor_ids=(root,),
        user_role="member",
        super_admin_role="super_admin",
    )
    assert out is GuardOutcome.PASS


def test_host_cookie_mismatched_tenant_raises():
    with pytest.raises(CrossTenantForbidden):
        check_cross_tenant(
            cookie_kind="host",
            session_tenant_id=str(uuid4()),
            request_tenant_id=str(uuid4()),
            user_role="member",
            super_admin_role="super_admin",
        )


def test_host_cookie_sibling_leaf_not_in_chain_raises():
    """A sibling-leaf member is not in this host's {self ∪ ancestors} set."""
    trust = str(uuid4())
    leaf = str(uuid4())
    sibling = str(uuid4())
    with pytest.raises(CrossTenantForbidden):
        check_cross_tenant(
            cookie_kind="host",
            session_tenant_id=sibling,
            request_tenant_id=leaf,
            request_ancestor_ids=(trust,),
            user_role="member",
            super_admin_role="super_admin",
        )


def test_host_cookie_no_membership_binding_fails_closed():
    """#1518: a host cookie whose session has no active-membership tenant → 403."""
    with pytest.raises(HostCookieMissingTenant):
        check_cross_tenant(
            cookie_kind="host",
            session_tenant_id=None,
            request_tenant_id=str(uuid4()),
            user_role="member",
            super_admin_role="super_admin",
        )


def test_host_cookie_on_apex_raises():
    with pytest.raises(HostCookieMissingTenant):
        check_cross_tenant(
            cookie_kind="host",
            session_tenant_id=str(uuid4()),
            request_tenant_id=None,
            user_role="member",
            super_admin_role="super_admin",
        )


def test_apex_cookie_with_super_admin_passes_for_any_tenant():
    out = check_cross_tenant(
        cookie_kind="apex",
        session_tenant_id=None,
        request_tenant_id=str(uuid4()),
        user_role="super_admin",
        super_admin_role="super_admin",
    )
    assert out is GuardOutcome.PASS


def test_apex_cookie_without_super_admin_raises():
    with pytest.raises(ApexCookieNotSuperAdmin):
        check_cross_tenant(
            cookie_kind="apex",
            session_tenant_id=None,
            request_tenant_id=str(uuid4()),
            user_role="member",
            super_admin_role="super_admin",
        )


def test_no_cookie_present_passes_through():
    """Unauthenticated requests don't trip the guard; auth itself decides."""
    out = check_cross_tenant(
        cookie_kind=None,
        session_tenant_id=None,
        request_tenant_id=str(uuid4()),
        user_role="",
        super_admin_role="super_admin",
    )
    assert out is GuardOutcome.PASS


def test_apex_cookie_with_super_admin_passes_on_apex_request():
    """Super admin on the apex domain itself (no tenant resolved) — still passes."""
    out = check_cross_tenant(
        cookie_kind="apex",
        session_tenant_id=None,
        request_tenant_id=None,
        user_role="super_admin",
        super_admin_role="super_admin",
    )
    assert out is GuardOutcome.PASS
