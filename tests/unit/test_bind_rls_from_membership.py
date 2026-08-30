"""_bind_rls_tenant_id sources the fence ONLY from the active membership.

Plan 1a introduced membership-first binding; Plan 1d removed the legacy
preferences fallback (clean break) — a membership-less session binds nothing and
the RLS fence denies (fail-closed)."""

from types import SimpleNamespace
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


def test_apex_topology_binds_host_lens_from_membership() -> None:
    from dazzle.http.runtime.auth.dependencies import _bind_apex_lens

    m = MembershipRecord(id="m-1", tenant_id="practice-1", identity_id="u-1")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(tenant_host=SimpleNamespace(app_name="app", topology="apex"))
        )
    )
    with patch("dazzle.http.runtime.auth.dependencies.set_current_host_tenant_id") as set_host:
        _bind_apex_lens(request, _ctx(active_membership=m))
    set_host.assert_called_once_with("practice-1")


def test_leftover_topology_does_not_invent_apex_lens() -> None:
    from dazzle.http.runtime.auth.dependencies import _bind_apex_lens

    m = MembershipRecord(id="m-1", tenant_id="practice-1", identity_id="u-1")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(tenant_host=SimpleNamespace(app_name="app", topology="zzz"))
        )
    )
    with patch("dazzle.http.runtime.auth.dependencies.set_current_host_tenant_id") as set_host:
        _bind_apex_lens(request, _ctx(active_membership=m))
    set_host.assert_not_called()


def test_schema_isolation_binds_search_path_from_membership() -> None:
    from dazzle.http.runtime.auth.dependencies import _bind_schema_from_membership

    m = MembershipRecord(id="m-1", tenant_id="tid-1", identity_id="u-1")
    record = SimpleNamespace(schema_name="tenant_acme", status="active")
    registry = SimpleNamespace(get_by_id=lambda _tid: record)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(tenant_registry=registry)))
    with (
        patch("dazzle.http.runtime.auth.dependencies.get_current_tenant_schema", return_value=None),
        patch("dazzle.http.runtime.auth.dependencies.set_current_tenant_schema") as set_schema,
    ):
        _bind_schema_from_membership(request, _ctx(active_membership=m))
    set_schema.assert_called_once_with("tenant_acme")


def test_schema_isolation_does_not_invent_from_leftover_registry() -> None:
    from dazzle.http.runtime.auth.dependencies import _bind_schema_from_membership

    m = MembershipRecord(id="m-1", tenant_id="tid-1", identity_id="u-1")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(tenant_registry=None)))
    with patch("dazzle.http.runtime.auth.dependencies.set_current_tenant_schema") as set_schema:
        _bind_schema_from_membership(request, _ctx(active_membership=m))
    set_schema.assert_not_called()
