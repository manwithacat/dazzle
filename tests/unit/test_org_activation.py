"""Pure two-phase activation resolver + glue (auth Plan 1b)."""

from types import SimpleNamespace

import pytest

from dazzle.http.runtime.auth.models import MembershipRecord
from dazzle.http.runtime.auth.org_activation import (
    FORBIDDEN_SENTINEL,
    Activated,
    ActivationOutcome,
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


def _host(domain: str, **kw: object) -> SimpleNamespace:
    return SimpleNamespace(domain=domain, **kw)


@pytest.mark.parametrize(
    ("spec", "auto_provision", "expected"),
    [
        pytest.param(
            _appspec(None, _host("acme.example")),
            False,
            True,
            id="tenant-host-implies-required-1393",
        ),
        pytest.param(_appspec(None, None), True, True, id="auto-provision-implies-required"),
        pytest.param(_appspec(None, None), False, False, id="neither-not-required"),
        pytest.param(_appspec(), False, False, id="no-entities-not-required"),
        pytest.param(SimpleNamespace(), False, False, id="missing-domain-is-safe"),
        # #1418: a tenant_host that opts out doesn't imply membership gating ...
        pytest.param(
            _appspec(_host("acme.example", membership_gated=False)),
            False,
            False,
            id="membership-gated-false-does-not-gate-1418",
        ),
        # ... but any gated tenant_host (default True) keeps the gate on ...
        pytest.param(
            _appspec(
                _host("a.example", membership_gated=False),
                _host("b.example", membership_gated=True),
            ),
            False,
            True,
            id="mixed-gated-and-ungated-gates-1418",
        ),
        # ... and auto_provision overrides — membership model is on regardless.
        pytest.param(
            _appspec(_host("a.example", membership_gated=False)),
            True,
            True,
            id="ungated-host-gated-by-auto-provision-1418",
        ),
    ],
)
def test_derive_memberships_required(
    spec: SimpleNamespace, auto_provision: bool, expected: bool
) -> None:
    """#1393 Phase A: declaring `tenant_host:` implies membership-gated login."""
    assert derive_memberships_required(spec, auto_provision=auto_provision) is expected


def _m(mid: str, tid: str, status: str = "active") -> MembershipRecord:
    return MembershipRecord(id=mid, tenant_id=tid, identity_id="u-1", status=status)


# Shared instances: MembershipRecord equality includes its timestamps.
_TWO_ACTIVE = (_m("m-1", "t-1"), _m("m-2", "t-2"))


@pytest.mark.parametrize(
    ("memberships", "host_tenant_id", "host_ancestor_ids", "expected"),
    [
        pytest.param([], None, (), NoOrgs(), id="zero-memberships-no-orgs"),
        pytest.param([_m("m-1", "t-1")], None, (), Activated("m-1"), id="single-active-activates"),
        pytest.param(
            list(_TWO_ACTIVE),
            None,
            (),
            NeedsPicker(_TWO_ACTIVE),
            id="multiple-active-need-picker",
        ),
        pytest.param(
            [_m("m-1", "t-1", status="suspended"), _m("m-2", "t-2")],
            None,
            (),
            Activated("m-2"),
            id="non-active-ignored",
        ),
        pytest.param(
            [_m("m-1", "t-1"), _m("m-2", "t-2")],
            "t-2",
            (),
            Activated("m-2"),
            id="host-pin-matches-membership",
        ),
        pytest.param(
            [_m("m-1", "t-1")], "t-OTHER", (), HostForbidden(), id="host-pin-no-match-forbidden"
        ),
        pytest.param(
            [_m("m-1", "t-1", status="suspended")],
            "t-1",
            (),
            HostForbidden(),
            id="host-pin-matches-only-active",
        ),
        # ADR-0037 Phase 5 — a root membership reaches descendant hosts via the
        # resolved host's ancestor chain (ResolvedTenant.ancestor_ids). The ROOT
        # membership binds (-> RLS fence = trust).
        pytest.param(
            [_m("m-root", "trust")],
            "school",
            ("trust",),
            Activated("m-root"),
            id="root-member-reaches-descendant-host",
        ),
        pytest.param(
            [_m("m-leaf", "school")],
            "school",
            ("trust",),
            Activated("m-leaf"),
            id="leaf-member-matches-host-directly",
        ),
        # Member of an UNRELATED trust -> not host, not any ancestor -> 403.
        pytest.param(
            [_m("m-other", "trust-B")],
            "school-A",
            ("trust-A",),
            HostForbidden(),
            id="non-member-of-chain-forbidden",
        ),
        # Empty ancestor chain keeps Layer-1 exact match: no widening.
        pytest.param(
            [_m("m-root", "trust")],
            "school",
            (),
            HostForbidden(),
            id="no-ancestors-exact-match-only",
        ),
        pytest.param(
            [_m("m-region", "region")],
            "school",
            ("trust", "region"),
            Activated("m-region"),
            id="three-level-root-reaches-deepest-host",
        ),
    ],
)
def test_resolve_activation(
    memberships: list[MembershipRecord],
    host_tenant_id: str | None,
    host_ancestor_ids: tuple[str, ...],
    expected: ActivationOutcome,
) -> None:
    out = resolve_activation(
        memberships=memberships,
        host_tenant_id=host_tenant_id,
        host_ancestor_ids=host_ancestor_ids,
    )
    assert out == expected


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


@pytest.mark.parametrize(
    ("outcome", "kwargs", "expected"),
    [
        pytest.param(Activated("m-9"), {}, ("m-9", "/app"), id="activated-keeps-next"),
        pytest.param(NeedsPicker(()), {}, (None, "/auth/select-org"), id="needs-picker-select-org"),
        # Pre-1c legacy transition: zero-membership login proceeds by default.
        pytest.param(NoOrgs(), {}, (None, "/app"), id="no-orgs-proceeds-by-default"),
        pytest.param(
            NoOrgs(),
            {"memberships_required": True},
            (None, "/auth/no-orgs"),
            id="no-orgs-redirects-when-required",
        ),
        # #1418: HostForbidden -> 403 sentinel only when login is membership-gated;
        # a `membership_gated: false` app uses the host purely for resolution +
        # the current_tenant lens, so a host-pin with no membership proceeds.
        pytest.param(
            HostForbidden(),
            {"memberships_required": True},
            (None, FORBIDDEN_SENTINEL),
            id="host-forbidden-sentinel-when-gated-1418",
        ),
        pytest.param(
            HostForbidden(),
            {"memberships_required": False},
            (None, "/app"),
            id="host-forbidden-proceeds-when-ungated-1418",
        ),
    ],
)
def test_login_redirect_for_outcome(
    outcome: ActivationOutcome, kwargs: dict, expected: tuple[str | None, str]
) -> None:
    assert _login_redirect_for_outcome(outcome, "/app", **kwargs) == expected


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


class TestJsonApiHostForbiddenGate:
    """#1418: the JSON API login path (json_active_membership_id) honours the
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

        from dazzle.http.runtime.auth.sign_in import json_active_membership_id

        user = SimpleNamespace(id="u-1")
        with pytest.raises(HTTPException) as ei:
            json_active_membership_id(
                self._store_no_membership(), user, self._request(memberships_required=True)
            )
        assert ei.value.status_code == 403

    def test_ungated_app_proceeds_membership_less(self) -> None:
        from dazzle.http.runtime.auth.sign_in import json_active_membership_id

        user = SimpleNamespace(id="u-1")
        result = json_active_membership_id(
            self._store_no_membership(), user, self._request(memberships_required=False)
        )
        assert result is None  # proceed membership-less; RLS fence still applies
