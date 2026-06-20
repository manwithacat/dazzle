"""current_user.tenant_id resolves ONLY from the active membership (Plan 1d).

The legacy preferences/domain-user fallback was removed (clean break): without
an active membership, tenant_id resolves to the deny sentinel so the scope
predicate / RLS fence denies (fail-closed)."""

from dazzle.http.runtime.auth.models import AuthContext, MembershipRecord, UserRecord
from dazzle.http.runtime.route_generator import _resolve_user_attribute


def _ctx(*, membership_tid=None, prefs_tid=None):  # noqa: ANN001
    m = (
        MembershipRecord(id="m-1", tenant_id=membership_tid, identity_id="u-1")
        if membership_tid is not None
        else None
    )
    return AuthContext(
        user=UserRecord(email="a@b.test", password_hash="x"),
        is_authenticated=True,
        roles=[],
        preferences={"tenant_id": prefs_tid} if prefs_tid is not None else {},
        active_membership=m,
    )


def test_tenant_id_prefers_active_membership() -> None:
    # Membership says tenant-A; preferences say tenant-LEGACY — membership wins.
    val = _resolve_user_attribute(
        "tenant_id", _ctx(membership_tid="tenant-A", prefs_tid="tenant-LEGACY")
    )
    assert val == "tenant-A"


def test_tenant_id_denies_without_membership_ignoring_prefs() -> None:
    # Plan 1d clean break: no membership → deny sentinel, even with a legacy
    # tenant_id preference present (the prefs fallback was removed).
    val = _resolve_user_attribute("tenant_id", _ctx(prefs_tid="tenant-LEGACY"))
    assert val == "__RBAC_DENY__"


def test_non_tenant_attr_unaffected_by_membership() -> None:
    # A non-tenant scope attr (e.g. school) still resolves from preferences even
    # when a membership is present — only tenant_id is membership-sourced.
    ctx = _ctx(membership_tid="tenant-A")
    ctx.preferences["school"] = "S1"
    assert _resolve_user_attribute("school", ctx) == "S1"
