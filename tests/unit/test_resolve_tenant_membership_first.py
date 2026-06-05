"""current_user.tenant_id resolves from the active membership first (Plan 1d)."""

from dazzle.back.runtime.auth.models import AuthContext, MembershipRecord, UserRecord
from dazzle.back.runtime.route_generator import _resolve_user_attribute


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


def test_tenant_id_falls_back_to_preferences_without_membership() -> None:
    val = _resolve_user_attribute("tenant_id", _ctx(prefs_tid="tenant-LEGACY"))
    assert val == "tenant-LEGACY"


def test_non_tenant_attr_unaffected_by_membership() -> None:
    # A non-tenant scope attr (e.g. school) still resolves from preferences even
    # when a membership is present — only tenant_id is membership-sourced.
    ctx = _ctx(membership_tid="tenant-A")
    ctx.preferences["school"] = "S1"
    assert _resolve_user_attribute("school", ctx) == "S1"
