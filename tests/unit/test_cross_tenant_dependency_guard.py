"""#1519: the cross-tenant cookie guard must run on ALL auth dependency
factories, not just `create_auth_dependency`.

Before #1519 only the full-auth dependency called `enforce_cross_tenant`, so a
cross-tenant `__Host-` cookie presented on a deny-gated or optional-auth route
reached the handler (the RLS fence still denied data, but the belt-and-suspenders
cookie guard was skipped). These tests pin that all three factories 403 a
cross-tenant cookie — while an *unauthenticated* session on an optional/deny
route still falls through to anonymous rather than 403ing.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException

from dazzle.http.runtime.auth import (
    AuthContext,
    create_auth_dependency,
    create_deny_dependency,
    create_optional_auth_dependency,
)
from dazzle.http.runtime.auth.models import MembershipRecord
from dazzle.http.runtime.tenant.cookies import host_cookie_name
from dazzle.http.runtime.tenant.resolver import ResolvedTenant

APP_NAME = "AegisMark"
HOST_COOKIE = host_cookie_name(APP_NAME)


def _tenant_marker() -> SimpleNamespace:
    return SimpleNamespace(
        app_name=APP_NAME,
        canonical_hosts=frozenset({"app.example.com"}),
        super_admin_role="super_admin",
    )


def _request(*, tenant_id: object | None) -> SimpleNamespace:
    """A tenant-host request carrying the app's `__Host-` session cookie."""
    tenant = (
        ResolvedTenant(kind="Trust", id=tenant_id, slug="acme", name="Acme")
        if tenant_id is not None
        else None
    )
    return SimpleNamespace(
        cookies={HOST_COOKIE: "sid"},
        state=SimpleNamespace(tenant=tenant),
        app=SimpleNamespace(state=SimpleNamespace(tenant_host=_tenant_marker())),
    )


def _store_returning(ctx: AuthContext) -> MagicMock:
    store = MagicMock()
    store.validate_session = MagicMock(return_value=ctx)
    return store


def _authed_ctx(member_tenant_id: str) -> AuthContext:
    return AuthContext(
        is_authenticated=True,
        roles=["member"],
        active_membership=MembershipRecord(
            id="m-1", tenant_id=member_tenant_id, identity_id="u-1", roles=["member"]
        ),
    )


# ── deny dependency ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deny_dep_403s_cross_tenant_cookie() -> None:
    member_tid = str(uuid4())
    ctx = _authed_ctx(member_tid)
    dep = create_deny_dependency(_store_returning(ctx), deny_roles=["intern"])
    # Host resolves to a DIFFERENT tenant than the session's membership.
    with pytest.raises(HTTPException) as exc:
        await dep(_request(tenant_id=uuid4()))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_deny_dep_allows_same_tenant_cookie() -> None:
    org_id = uuid4()
    ctx = _authed_ctx(str(org_id))
    dep = create_deny_dependency(_store_returning(ctx), deny_roles=["intern"])
    result = await dep(_request(tenant_id=org_id))
    assert result.is_authenticated


# ── optional-auth dependency ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_optional_dep_403s_cross_tenant_cookie() -> None:
    ctx = _authed_ctx(str(uuid4()))
    dep = create_optional_auth_dependency(_store_returning(ctx))
    with pytest.raises(HTTPException) as exc:
        await dep(_request(tenant_id=uuid4()))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_optional_dep_allows_same_tenant_cookie() -> None:
    org_id = uuid4()
    ctx = _authed_ctx(str(org_id))
    dep = create_optional_auth_dependency(_store_returning(ctx))
    result = await dep(_request(tenant_id=org_id))
    assert result.is_authenticated


@pytest.mark.asyncio
async def test_optional_dep_unauthenticated_cookie_stays_anonymous() -> None:
    """Regression guard: an expired/invalid session with a stale host cookie must
    fall through to anonymous on an optional route, NOT 403 (the guard only fires
    for authenticated sessions)."""
    ctx = AuthContext()  # is_authenticated=False
    dep = create_optional_auth_dependency(_store_returning(ctx))
    result = await dep(_request(tenant_id=uuid4()))
    assert result.is_authenticated is False


# ── full-auth dependency (unchanged, but pin it) ─────────────────────────────


@pytest.mark.asyncio
async def test_auth_dep_403s_cross_tenant_cookie() -> None:
    ctx = _authed_ctx(str(uuid4()))
    dep = create_auth_dependency(_store_returning(ctx))
    with pytest.raises(HTTPException) as exc:
        await dep(_request(tenant_id=uuid4()))
    assert exc.value.status_code == 403
