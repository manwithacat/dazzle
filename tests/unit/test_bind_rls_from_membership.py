"""_bind_rls_tenant_id sources the fence ONLY from the active membership.

Plan 1a introduced membership-first binding; Plan 1d removed the legacy
preferences fallback (clean break) — a membership-less session binds nothing and
the RLS fence denies (fail-closed)."""

from unittest.mock import patch

from dazzle.http.runtime.auth.dependencies import _bind_rls_tenant_id
from dazzle.http.runtime.auth.models import AuthContext, MembershipRecord, UserRecord


def _ctx(active_membership=None, prefs=None) -> AuthContext:
    return AuthContext(
        user=UserRecord(email="a@b.test", password_hash="x"),
        is_authenticated=True,
        roles=[],
        preferences=prefs or {},
        active_membership=active_membership,
    )


def test_binds_tenant_id_from_active_membership() -> None:
    m = MembershipRecord(id="m-1", tenant_id="tenant-xyz", identity_id="u-1", roles=["admin"])
    with (
        patch("dazzle.http.runtime.tenant_isolation.set_current_tenant_id") as set_tid,
        patch("dazzle.http.runtime.tenant_isolation.get_rls_user_attr_names", return_value=set()),
    ):
        _bind_rls_tenant_id(_ctx(active_membership=m))
    set_tid.assert_called_once_with("tenant-xyz")


def test_no_membership_binds_nothing_even_with_prefs() -> None:
    # Plan 1d clean break: the preferences fallback is gone. A membership-less
    # session leaves dazzle.tenant_id unbound (fail-closed) even if a legacy
    # tenant_id preference is present.
    with (
        patch("dazzle.http.runtime.tenant_isolation.set_current_tenant_id") as set_tid,
        patch("dazzle.http.runtime.tenant_isolation.get_rls_user_attr_names", return_value=set()),
    ):
        _bind_rls_tenant_id(_ctx(prefs={"tenant_id": "tenant-legacy"}))
    set_tid.assert_not_called()


def test_unauthenticated_binds_nothing() -> None:
    with patch("dazzle.http.runtime.tenant_isolation.set_current_tenant_id") as set_tid:
        _bind_rls_tenant_id(AuthContext())
    set_tid.assert_not_called()
