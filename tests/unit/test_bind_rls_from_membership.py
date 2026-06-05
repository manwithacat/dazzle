"""_bind_rls_tenant_id sources the fence from the active membership (Plan 1a)."""

from unittest.mock import patch

from dazzle.back.runtime.auth.dependencies import _bind_rls_tenant_id
from dazzle.back.runtime.auth.models import AuthContext, MembershipRecord, UserRecord


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
        patch("dazzle.back.runtime.tenant_isolation.set_current_tenant_id") as set_tid,
        patch("dazzle.back.runtime.tenant_isolation.get_rls_user_attr_names", return_value=set()),
    ):
        _bind_rls_tenant_id(_ctx(active_membership=m))
    set_tid.assert_called_once_with("tenant-xyz")


def test_falls_back_to_preferences_when_no_membership() -> None:
    with (
        patch("dazzle.back.runtime.tenant_isolation.set_current_tenant_id") as set_tid,
        patch("dazzle.back.runtime.tenant_isolation.get_rls_user_attr_names", return_value=set()),
    ):
        _bind_rls_tenant_id(_ctx(prefs={"tenant_id": "tenant-legacy"}))
    set_tid.assert_called_once_with("tenant-legacy")


def test_unauthenticated_binds_nothing() -> None:
    with patch("dazzle.back.runtime.tenant_isolation.set_current_tenant_id") as set_tid:
        _bind_rls_tenant_id(AuthContext())
    set_tid.assert_not_called()
