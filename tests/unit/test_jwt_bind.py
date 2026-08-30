"""ADR-0055 PR2: JWT claim vs membership vs Host; cookie wins over Bearer."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from dazzle.http.runtime.auth.jwt_bind import bind_jwt_tenant_context
from dazzle.http.runtime.auth.models import MembershipRecord, UserRecord


def _user() -> UserRecord:
    return UserRecord(email="a@b.test", password_hash="x")


def _store(user: UserRecord, memberships: list[MembershipRecord]) -> SimpleNamespace:
    return SimpleNamespace(
        get_user_by_id=lambda uid: user if str(uid) == str(user.id) else None,
        get_memberships_for_identity=lambda _iid: memberships,
    )


def _jwt(user: UserRecord, *, tenant_id: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(is_authenticated=True, user_id=str(user.id), tenant_id=tenant_id)


def _request(*, topology: str = "", host_id: str | None = None, gated: bool = True):
    tenant = None
    if host_id is not None:
        tenant = SimpleNamespace(id=host_id, ancestor_ids=())
    return SimpleNamespace(
        state=SimpleNamespace(tenant=tenant),
        app=SimpleNamespace(
            state=SimpleNamespace(
                memberships_required=gated,
                tenant_host=SimpleNamespace(app_name="app", topology=topology),
            )
        ),
    )


def test_claim_must_be_active_membership() -> None:
    user = _user()
    m = MembershipRecord(id="m1", tenant_id="t-ok", identity_id=str(user.id))
    with pytest.raises(HTTPException) as exc:
        bind_jwt_tenant_context(
            _request(topology="apex"),
            _jwt(user, tenant_id="t-other"),
            _store(user, [m]),
        )
    assert exc.value.status_code == 403


def test_b_claim_mismatch_host_403() -> None:
    user = _user()
    host = str(uuid4())
    other = str(uuid4())
    m = MembershipRecord(id="m1", tenant_id=other, identity_id=str(user.id))
    with pytest.raises(HTTPException) as exc:
        bind_jwt_tenant_context(
            _request(topology="provider_subdomain", host_id=host),
            _jwt(user, tenant_id=other),
            _store(user, [m]),
        )
    assert exc.value.status_code == 403


def test_apex_sole_membership_when_claim_absent() -> None:
    user = _user()
    m = MembershipRecord(id="m1", tenant_id="t1", identity_id=str(user.id))
    ctx = bind_jwt_tenant_context(
        _request(topology="apex"),
        _jwt(user, tenant_id=None),
        _store(user, [m]),
    )
    assert ctx.is_authenticated
    assert ctx.active_membership is m


def test_cookie_wins_over_bearer() -> None:
    from dazzle.http.runtime.auth.dependencies import _resolve_auth_context
    from dazzle.http.runtime.auth.models import AuthContext

    user = _user()
    cookie_ctx = AuthContext(user=user, is_authenticated=True, roles=["member"])
    store = SimpleNamespace(validate_session=lambda _sid: cookie_ctx)

    def _boom(_request):
        raise AssertionError("Bearer must not be consulted when a cookie is present")

    request = SimpleNamespace(
        cookies={"dazzle_session": "sid-1"},
        app=SimpleNamespace(
            state=SimpleNamespace(
                tenant_host=None,
                jwt_verifier=SimpleNamespace(get_auth_context=_boom),
            )
        ),
        headers={},
    )
    got = _resolve_auth_context(request, store, "dazzle_session")
    assert got is cookie_ctx


def test_unauthenticated_jwt_returns_empty() -> None:
    user = _user()
    ctx = bind_jwt_tenant_context(
        _request(),
        SimpleNamespace(is_authenticated=False, user_id=None, tenant_id=None),
        _store(user, []),
    )
    assert not ctx.is_authenticated
