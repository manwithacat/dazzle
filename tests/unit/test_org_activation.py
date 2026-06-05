"""Pure two-phase activation resolver + glue (auth Plan 1b)."""

from types import SimpleNamespace

from dazzle.back.runtime.auth.models import MembershipRecord
from dazzle.back.runtime.auth.org_activation import (
    FORBIDDEN_SENTINEL,
    Activated,
    HostForbidden,
    NeedsPicker,
    NoOrgs,
    _login_redirect_for_outcome,
    activate_session_for_login,
    host_tenant_id_from_request,
    resolve_activation,
)


def _m(mid: str, tid: str, status: str = "active") -> MembershipRecord:
    return MembershipRecord(id=mid, tenant_id=tid, identity_id="u-1", status=status)


class TestResolveActivation:
    def test_zero_memberships_is_no_orgs(self) -> None:
        assert isinstance(resolve_activation(memberships=[], host_tenant_id=None), NoOrgs)

    def test_single_active_membership_auto_activates(self) -> None:
        out = resolve_activation(memberships=[_m("m-1", "t-1")], host_tenant_id=None)
        assert isinstance(out, Activated)
        assert out.membership_id == "m-1"

    def test_multiple_active_memberships_need_picker(self) -> None:
        out = resolve_activation(
            memberships=[_m("m-1", "t-1"), _m("m-2", "t-2")], host_tenant_id=None
        )
        assert isinstance(out, NeedsPicker)
        assert {m.id for m in out.memberships} == {"m-1", "m-2"}

    def test_non_active_memberships_are_ignored(self) -> None:
        out = resolve_activation(
            memberships=[_m("m-1", "t-1", status="suspended"), _m("m-2", "t-2")],
            host_tenant_id=None,
        )
        assert isinstance(out, Activated)
        assert out.membership_id == "m-2"

    def test_host_pin_matches_membership(self) -> None:
        out = resolve_activation(
            memberships=[_m("m-1", "t-1"), _m("m-2", "t-2")], host_tenant_id="t-2"
        )
        assert isinstance(out, Activated)
        assert out.membership_id == "m-2"

    def test_host_pin_no_matching_membership_is_forbidden(self) -> None:
        out = resolve_activation(memberships=[_m("m-1", "t-1")], host_tenant_id="t-OTHER")
        assert isinstance(out, HostForbidden)

    def test_host_pin_matches_only_active_membership(self) -> None:
        out = resolve_activation(
            memberships=[_m("m-1", "t-1", status="suspended")], host_tenant_id="t-1"
        )
        assert isinstance(out, HostForbidden)


class _FakeStore:
    def __init__(self, memberships: list[MembershipRecord]) -> None:
        self._m = memberships

    def get_memberships_for_identity(self, identity_id: str) -> list[MembershipRecord]:
        return list(self._m)


def _req(tenant: object | None) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(tenant=tenant))


class TestRequestGlue:
    def test_host_tenant_id_none_when_no_state(self) -> None:
        assert host_tenant_id_from_request(SimpleNamespace()) is None

    def test_host_tenant_id_none_for_canonical_host(self) -> None:
        assert host_tenant_id_from_request(_req(None)) is None

    def test_host_tenant_id_stringifies_resolved_id(self) -> None:
        resolved = SimpleNamespace(id="t-7", slug="acme")
        assert host_tenant_id_from_request(_req(resolved)) == "t-7"

    def test_activate_for_login_uses_store_and_request(self) -> None:
        store = _FakeStore([_m("m-1", "t-1"), _m("m-2", "t-2")])
        user = SimpleNamespace(id="u-1")
        out = activate_session_for_login(store, user, _req(SimpleNamespace(id="t-2")))
        assert isinstance(out, Activated)
        assert out.membership_id == "m-2"
        out2 = activate_session_for_login(store, user, _req(None))
        assert isinstance(out2, NeedsPicker)


class TestLoginRedirectMapper:
    def test_activated_keeps_next_target(self) -> None:
        mid, target = _login_redirect_for_outcome(Activated("m-9"), "/app")
        assert mid == "m-9"
        assert target == "/app"

    def test_needs_picker_redirects_to_select_org(self) -> None:
        mid, target = _login_redirect_for_outcome(NeedsPicker(()), "/app")
        assert mid is None
        assert target == "/auth/select-org"

    def test_no_orgs_redirects(self) -> None:
        mid, target = _login_redirect_for_outcome(NoOrgs(), "/app")
        assert mid is None
        assert target == "/auth/no-orgs"

    def test_host_forbidden_uses_sentinel(self) -> None:
        mid, target = _login_redirect_for_outcome(HostForbidden(), "/app")
        assert mid is None
        assert target == FORBIDDEN_SENTINEL
