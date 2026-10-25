"""#1853: [auth.self_signup] join_host_org admits a brand-new identity to the host org.

Without it a fresh sign-up on a host-pinned org's own address got the host-pin
403; cyfuture monkeypatched a private call path to auto-join, which #1805 broke.
The join is declared, limited to identities with no memberships and no
membership history, held until the email is verified (by default), and created
at the host itself with the declared role.
"""

from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.core.manifest import AuthSelfSignupConfig
from dazzle.http.runtime.auth.admin_policy import AdminPolicy
from dazzle.http.runtime.auth.models import MembershipRecord
from dazzle.http.runtime.auth.org_activation import (
    VERIFY_TO_JOIN_SENTINEL,
    Activated,
    HostForbidden,
    VerifyToJoin,
    _login_redirect_for_outcome,
    activate_session_for_login,
)
from dazzle.http.runtime.subsystems.auth import _validated_self_signup

_JOIN = AuthSelfSignupConfig(join_host_org=True, role="customer")


class _Store:
    def __init__(self, memberships: list[MembershipRecord] = (), events: list[Any] = ()) -> None:  # type: ignore[assignment]
        self.memberships = list(memberships)
        self.events = list(events)
        self.created: list[dict[str, Any]] = []

    def get_memberships_for_identity(self, identity_id: str) -> list[MembershipRecord]:
        return [m for m in self.memberships if m.identity_id == identity_id]

    def get_membership_events(self, *, identity_id: str) -> list[Any]:
        return self.events

    def create_membership(self, **kw: Any) -> MembershipRecord:
        self.created.append(kw)
        m = MembershipRecord(
            id="m-new", tenant_id=kw["tenant_id"], identity_id=kw["identity_id"], roles=kw["roles"]
        )
        self.memberships.append(m)
        return m


def _request(self_signup: AuthSelfSignupConfig | None, host: str | None = "org-host") -> Any:
    tenant = SimpleNamespace(id=host, ancestor_ids=("org-root",)) if host else None
    app = SimpleNamespace(state=SimpleNamespace(self_signup=self_signup))
    return SimpleNamespace(app=app, state=SimpleNamespace(tenant=tenant))


def _user(verified: bool = True) -> Any:
    return SimpleNamespace(id="u-1", email="new@example.com", email_verified=verified)


def test_new_verified_identity_joins_the_host_with_the_declared_role() -> None:
    store = _Store()
    out = activate_session_for_login(store, _user(), _request(_JOIN))
    assert isinstance(out, Activated) and out.membership_id == "m-new"
    (created,) = store.created
    assert created["tenant_id"] == "org-host"  # the leaf host, never the root
    assert created["roles"] == ["customer"]


@pytest.mark.parametrize(
    ("store", "self_signup", "host", "expected"),
    [
        pytest.param(
            _Store([MembershipRecord(id="m-x", tenant_id="other-org", identity_id="u-1")]),
            _JOIN,
            "org-host",
            HostForbidden,
            id="member-elsewhere-still-forbidden",
        ),
        pytest.param(
            _Store(
                [
                    MembershipRecord(
                        id="m-x", tenant_id="other-org", identity_id="u-1", status="suspended"
                    )
                ]
            ),
            _JOIN,
            "org-host",
            HostForbidden,
            id="suspended-elsewhere-still-forbidden",
        ),
        pytest.param(
            _Store(events=[object()]),
            _JOIN,
            "org-host",
            HostForbidden,
            id="removed-member-history-still-forbidden",
        ),
        pytest.param(_Store(), None, "org-host", HostForbidden, id="not-declared-forbidden"),
    ],
)
def test_join_is_refused(store: _Store, self_signup: Any, host: str, expected: type) -> None:
    out = activate_session_for_login(store, _user(), _request(self_signup, host))
    assert isinstance(out, expected)
    assert store.created == []


def test_unpinned_host_never_self_joins() -> None:
    store = _Store()
    activate_session_for_login(store, _user(), _request(_JOIN, host=None))
    assert store.created == []


def test_unverified_email_is_held_until_verified() -> None:
    store = _Store()
    out = activate_session_for_login(store, _user(verified=False), _request(_JOIN))
    assert isinstance(out, VerifyToJoin)
    assert store.created == []
    assert _login_redirect_for_outcome(out, "/app", memberships_required=True) == (
        None,
        VERIFY_TO_JOIN_SENTINEL,
    )

    opted_out = AuthSelfSignupConfig(
        join_host_org=True, role="customer", require_verified_email=False
    )
    assert isinstance(
        activate_session_for_login(store, _user(verified=False), _request(opted_out)), Activated
    )


def _policy(*admins: str) -> AdminPolicy:
    return AdminPolicy.from_config(org_admin_roles=list(admins), admin_capabilities={})


def test_boot_validation_fails_closed() -> None:
    kw = {"declared_personas": {"customer", "admin"}, "memberships_required": True}
    assert _validated_self_signup(_JOIN, admin_policy=_policy("admin"), **kw) is _JOIN
    with pytest.raises(ValueError, match="not a declared persona"):
        _validated_self_signup(
            AuthSelfSignupConfig(join_host_org=True, role="ghost"), admin_policy=_policy(), **kw
        )
    with pytest.raises(ValueError, match="admin capabilities"):
        _validated_self_signup(_JOIN, admin_policy=_policy("customer"), **kw)
    assert (
        _validated_self_signup(
            _JOIN,
            admin_policy=_policy(),
            declared_personas={"customer"},
            memberships_required=False,
        )
        is None
    )
