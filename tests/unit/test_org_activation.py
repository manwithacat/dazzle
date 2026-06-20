"""Pure two-phase activation resolver + glue (auth Plan 1b)."""

from types import SimpleNamespace

import pytest

from dazzle.http.runtime.auth.models import MembershipRecord
from dazzle.http.runtime.auth.org_activation import (
    FORBIDDEN_SENTINEL,
    Activated,
    HostForbidden,
    NeedsPicker,
    NoOrgs,
    _login_redirect_for_outcome,
    activate_session_for_login,
    derive_memberships_required,
    host_tenant_id_from_request,
    resolve_activation,
)


def _appspec(*tenant_host_flags: object) -> SimpleNamespace:
    """An appspec whose domain.entities carry the given `tenant_host` values."""
    entities = [SimpleNamespace(tenant_host=flag) for flag in tenant_host_flags]
    return SimpleNamespace(domain=SimpleNamespace(entities=entities))


class TestDeriveMembershipsRequired:
    """#1393 Phase A: declaring `tenant_host:` implies membership-gated login."""

    def test_tenant_host_implies_required_without_auto_provision(self) -> None:
        spec = _appspec(None, SimpleNamespace(domain="acme.example"))  # one entity has tenant_host
        assert derive_memberships_required(spec, auto_provision=False) is True

    def test_auto_provision_still_implies_required(self) -> None:
        spec = _appspec(None, None)  # no tenant_host
        assert derive_memberships_required(spec, auto_provision=True) is True

    def test_neither_is_not_required(self) -> None:
        spec = _appspec(None, None)
        assert derive_memberships_required(spec, auto_provision=False) is False

    def test_no_entities_is_not_required(self) -> None:
        assert derive_memberships_required(_appspec(), auto_provision=False) is False

    def test_missing_domain_is_safe(self) -> None:
        assert derive_memberships_required(SimpleNamespace(), auto_provision=False) is False

    def test_membership_gated_false_does_not_gate(self) -> None:
        # #1418: a tenant_host that opts out doesn't imply membership gating.
        spec = _appspec(SimpleNamespace(domain="acme.example", membership_gated=False))
        assert derive_memberships_required(spec, auto_provision=False) is False

    def test_mixed_gated_and_ungated_still_gates(self) -> None:
        # #1418: any gated tenant_host (default True) keeps the gate on.
        spec = _appspec(
            SimpleNamespace(domain="a.example", membership_gated=False),
            SimpleNamespace(domain="b.example", membership_gated=True),
        )
        assert derive_memberships_required(spec, auto_provision=False) is True

    def test_ungated_host_still_gated_by_auto_provision(self) -> None:
        # #1418: auto_provision overrides — membership model is on regardless.
        spec = _appspec(SimpleNamespace(domain="a.example", membership_gated=False))
        assert derive_memberships_required(spec, auto_provision=True) is True


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

    def test_no_orgs_proceeds_by_default_legacy_transition(self) -> None:
        # Pre-1c: no app has memberships, so zero-membership login proceeds.
        mid, target = _login_redirect_for_outcome(NoOrgs(), "/app")
        assert mid is None
        assert target == "/app"

    def test_no_orgs_redirects_when_memberships_required(self) -> None:
        mid, target = _login_redirect_for_outcome(NoOrgs(), "/app", memberships_required=True)
        assert mid is None
        assert target == "/auth/no-orgs"

    def test_host_forbidden_sentinel_when_membership_gated(self) -> None:
        # #1418: HostForbidden → 403 only when the app gates login on membership.
        mid, target = _login_redirect_for_outcome(
            HostForbidden(), "/app", memberships_required=True
        )
        assert mid is None
        assert target == FORBIDDEN_SENTINEL

    def test_host_forbidden_proceeds_when_ungated(self) -> None:
        # #1418: a `tenant_host: membership_gated: false` app (memberships_required off)
        # uses the host purely for resolution + the current_tenant lens — a host-pin with
        # no membership proceeds (self-authorizes) instead of 403.
        mid, target = _login_redirect_for_outcome(
            HostForbidden(), "/app", memberships_required=False
        )
        assert mid is None
        assert target == "/app"


class _ProvisioningStore:
    """Fake store recording ensure_single_org_membership calls (Plan 1c)."""

    def __init__(self) -> None:
        self.provisioned: list[str] = []
        self._memberships: dict[str, list[MembershipRecord]] = {}

    def get_memberships_for_identity(self, identity_id: str) -> list[MembershipRecord]:
        return list(self._memberships.get(identity_id, []))

    def ensure_single_org_membership(self, user, *, name="Default", appspec=None):  # noqa: ANN001
        self.provisioned.append(str(user.id))
        m = MembershipRecord(id="m-prov", tenant_id="t-default", identity_id=str(user.id))
        self._memberships[str(user.id)] = [m]
        return m


def _req_with_flag(*, provision: bool, tenant=None) -> SimpleNamespace:  # noqa: ANN001
    app = SimpleNamespace(state=SimpleNamespace(single_org_auto_provision=provision))
    return SimpleNamespace(app=app, state=SimpleNamespace(tenant=tenant))


class TestLazyProvisioning:
    def test_provisions_when_flag_on_and_zero_memberships(self) -> None:
        store = _ProvisioningStore()
        user = SimpleNamespace(id="u-1")
        out = activate_session_for_login(store, user, _req_with_flag(provision=True))
        assert store.provisioned == ["u-1"]
        assert isinstance(out, Activated)
        assert out.membership_id == "m-prov"

    def test_does_not_provision_when_flag_off(self) -> None:
        store = _ProvisioningStore()
        user = SimpleNamespace(id="u-1")
        out = activate_session_for_login(store, user, _req_with_flag(provision=False))
        assert store.provisioned == []
        assert isinstance(out, NoOrgs)

    def test_does_not_provision_when_membership_already_exists(self) -> None:
        store = _ProvisioningStore()
        store._memberships["u-1"] = [MembershipRecord(id="m-x", tenant_id="t-1", identity_id="u-1")]
        user = SimpleNamespace(id="u-1")
        out = activate_session_for_login(store, user, _req_with_flag(provision=True))
        assert store.provisioned == []
        assert isinstance(out, Activated)
        assert out.membership_id == "m-x"

    def test_does_not_provision_when_host_pinned(self) -> None:
        store = _ProvisioningStore()
        user = SimpleNamespace(id="u-1")
        out = activate_session_for_login(
            store, user, _req_with_flag(provision=True, tenant=SimpleNamespace(id="t-pinned"))
        )
        assert store.provisioned == []  # host-pin guard: no provision
        assert isinstance(out, HostForbidden)


class TestHostPinAncestorReachability:
    """ADR-0037 Phase 5 — a membership at the root reaches descendant hosts via
    the resolved host's ancestor chain (ResolvedTenant.ancestor_ids)."""

    def test_root_member_reaches_descendant_host(self) -> None:
        # Member of root "trust" (m-root); host resolves to descendant "school"
        # whose ancestor chain is ("trust",). The ROOT membership activates.
        out = resolve_activation(
            memberships=[_m("m-root", "trust")],
            host_tenant_id="school",
            host_ancestor_ids=("trust",),
        )
        assert isinstance(out, Activated)
        assert out.membership_id == "m-root"  # binds the root (→ RLS fence = trust)

    def test_leaf_member_still_matches_host_directly(self) -> None:
        out = resolve_activation(
            memberships=[_m("m-leaf", "school")],
            host_tenant_id="school",
            host_ancestor_ids=("trust",),
        )
        assert isinstance(out, Activated)
        assert out.membership_id == "m-leaf"

    def test_non_member_of_whole_chain_is_forbidden(self) -> None:
        # Member of an UNRELATED trust → not host, not any ancestor → 403.
        out = resolve_activation(
            memberships=[_m("m-other", "trust-B")],
            host_tenant_id="school-A",
            host_ancestor_ids=("trust-A",),
        )
        assert isinstance(out, HostForbidden)

    def test_no_ancestors_is_exact_match_only(self) -> None:
        # Empty ancestor chain preserves Layer-1 exact-match: root member on a
        # leaf host with no chain is forbidden (no widening).
        out = resolve_activation(
            memberships=[_m("m-root", "trust")],
            host_tenant_id="school",
            host_ancestor_ids=(),
        )
        assert isinstance(out, HostForbidden)

    def test_three_level_root_member_reaches_deepest_host(self) -> None:
        out = resolve_activation(
            memberships=[_m("m-region", "region")],
            host_tenant_id="school",
            host_ancestor_ids=("trust", "region"),
        )
        assert isinstance(out, Activated)
        assert out.membership_id == "m-region"


class TestJsonApiHostForbiddenGate:
    """#1418: the JSON API login path (_json_active_membership_id) honours the
    membership gate exactly like the HTML redirect mapper — host-pin 403 only when
    the app gates login on membership; a `membership_gated: false` app proceeds."""

    @staticmethod
    def _request(*, memberships_required: bool):
        # Host-pinned request (state.tenant.id set) for an app whose membership gate
        # is toggled. ancestor_ids empty (flat host).
        tenant = SimpleNamespace(id="org-1", ancestor_ids=())
        app = SimpleNamespace(state=SimpleNamespace(memberships_required=memberships_required))
        return SimpleNamespace(app=app, state=SimpleNamespace(tenant=tenant))

    @staticmethod
    def _store_no_membership():
        return SimpleNamespace(
            get_memberships_for_identity=lambda _id: [],
        )

    def test_gated_app_raises_403(self) -> None:
        from fastapi import HTTPException

        from dazzle.http.runtime.auth.routes import _json_active_membership_id

        user = SimpleNamespace(id="u-1")
        with pytest.raises(HTTPException) as ei:
            _json_active_membership_id(
                self._store_no_membership(), user, self._request(memberships_required=True)
            )
        assert ei.value.status_code == 403

    def test_ungated_app_proceeds_membership_less(self) -> None:
        from dazzle.http.runtime.auth.routes import _json_active_membership_id

        user = SimpleNamespace(id="u-1")
        result = _json_active_membership_id(
            self._store_no_membership(), user, self._request(memberships_required=False)
        )
        assert result is None  # proceed membership-less; RLS fence still applies
