"""Cross-tenant guard wiring tests (#1289 slice 5 follow-up).

Exercises `enforce_cross_tenant()` directly with stub request + auth
context objects so the FastAPI dependency wiring is covered without
spinning up a full ASGI app.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from dazzle.http.runtime.tenant.cookies import apex_cookie_name, host_cookie_name
from dazzle.http.runtime.tenant.guard_wiring import enforce_cross_tenant
from dazzle.http.runtime.tenant.resolver import ResolvedTenant

APP_NAME = "AegisMark"
HOST_COOKIE = host_cookie_name(APP_NAME)
APEX_COOKIE = apex_cookie_name(APP_NAME)


def _tenant(
    slug: str,
    *,
    tid: object | None = None,
    ancestor_ids: tuple[str, ...] = (),
) -> ResolvedTenant:
    return ResolvedTenant(
        kind="Trust",
        id=tid or uuid4(),
        slug=slug,
        name=slug.title(),
        ancestor_ids=ancestor_ids,
    )


def _tenant_state(super_admin_role: str = "super_admin") -> SimpleNamespace:
    return SimpleNamespace(
        app_name=APP_NAME,
        canonical_hosts=frozenset({"app.example.com"}),
        super_admin_role=super_admin_role,
    )


def _request(
    *,
    cookies: dict[str, str] | None = None,
    tenant: ResolvedTenant | None = None,
    tenant_state: SimpleNamespace | None = _tenant_state(),
) -> SimpleNamespace:
    return SimpleNamespace(
        cookies=cookies or {},
        state=SimpleNamespace(tenant=tenant),
        app=SimpleNamespace(state=SimpleNamespace(tenant_host=tenant_state)),
    )


def _auth(roles: list[str], *, member_tenant_id: str | None = None) -> SimpleNamespace:
    """Build an AuthContext-shaped stub.

    #1518: the session's bound tenant comes from ``active_membership.tenant_id``
    (the org id), NOT a slug on the user — mirror the real AuthContext shape so
    the wiring test can't pass by fabricating a ``user.tenant_slug`` the
    production ``UserRecord`` never carries.
    """
    membership = (
        SimpleNamespace(tenant_id=member_tenant_id) if member_tenant_id is not None else None
    )
    return SimpleNamespace(roles=roles, user=SimpleNamespace(), active_membership=membership)


# --- legacy app (no tenant_host:) --------------------------------------------


def test_legacy_app_is_a_no_op():
    """Apps without a tenant_host: block carry app.state.tenant_host = None."""
    request = _request(cookies={HOST_COOKIE: "anything"}, tenant_state=None)
    enforce_cross_tenant(request, _auth(["member"]))


# --- tenant_host app, no relevant cookie -------------------------------------


def test_no_relevant_cookie_passes():
    """Sessions still on legacy dazzle_session cookie — guard sees nothing."""
    request = _request(cookies={"dazzle_session": "irrelevant"}, tenant=_tenant("acme"))
    enforce_cross_tenant(request, _auth(["member"]))


# --- host cookie matrix ------------------------------------------------------


def test_host_cookie_matching_tenant_passes():
    t = _tenant("acme")
    request = _request(cookies={HOST_COOKIE: "sid"}, tenant=t)
    enforce_cross_tenant(request, _auth(["member"], member_tenant_id=str(t.id)))


def test_host_cookie_ancestor_membership_passes():
    """ADR-0037: a member of the resolved host's ancestor (root) reaches the host."""
    root = uuid4()
    leaf = _tenant("leaf", ancestor_ids=(str(root),))
    request = _request(cookies={HOST_COOKIE: "sid"}, tenant=leaf)
    enforce_cross_tenant(request, _auth(["member"], member_tenant_id=str(root)))


def test_host_cookie_mismatched_tenant_raises_403():
    from fastapi import HTTPException

    request = _request(cookies={HOST_COOKIE: "sid"}, tenant=_tenant("other"))
    with pytest.raises(HTTPException) as excinfo:
        enforce_cross_tenant(request, _auth(["member"], member_tenant_id=str(uuid4())))
    assert excinfo.value.status_code == 403


def test_host_cookie_no_active_membership_fails_closed_403():
    """#1518: a host cookie whose session carries no active membership → 403."""
    from fastapi import HTTPException

    request = _request(cookies={HOST_COOKIE: "sid"}, tenant=_tenant("acme"))
    with pytest.raises(HTTPException) as excinfo:
        enforce_cross_tenant(request, _auth(["member"]))
    assert excinfo.value.status_code == 403


def test_host_cookie_on_apex_request_raises_403():
    from fastapi import HTTPException

    request = _request(cookies={HOST_COOKIE: "sid"}, tenant=None)
    with pytest.raises(HTTPException) as excinfo:
        enforce_cross_tenant(request, _auth(["member"], member_tenant_id=str(uuid4())))
    assert excinfo.value.status_code == 403


# --- apex cookie matrix ------------------------------------------------------


def test_apex_cookie_with_super_admin_passes():
    request = _request(cookies={APEX_COOKIE: "sid"}, tenant=_tenant("acme"))
    enforce_cross_tenant(request, _auth(["super_admin"]))


def test_apex_cookie_with_prefixed_super_admin_role_passes():
    """AuthContext.roles often carries the database `role_` prefix."""
    request = _request(cookies={APEX_COOKIE: "sid"}, tenant=_tenant("acme"))
    enforce_cross_tenant(request, _auth(["role_super_admin"]))


def test_apex_cookie_without_super_admin_raises_403():
    from fastapi import HTTPException

    request = _request(cookies={APEX_COOKIE: "sid"}, tenant=_tenant("acme"))
    with pytest.raises(HTTPException) as excinfo:
        enforce_cross_tenant(request, _auth(["member"]))
    assert excinfo.value.status_code == 403
