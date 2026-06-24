"""Uniform membership admission gate (#1424 Task 1.4).

Proves that ``assert_domain_admissible`` is wired into EVERY membership-creating
path — invitation accept, enterprise SSO JIT, and SCIM provisioning — so that a
tenant which restricts membership to its verified domains refuses an off-domain
email on all three, and admits an on-domain email on all three. The pure gate
logic itself is tested in ``test_domain_join_admission.py``; this file proves the wiring.

Each path gets a minimal fake store (mirroring the per-module test idioms in
``test_enterprise_login.py`` / ``test_scim_provisioning.py``) that additionally
answers the gate's two store reads: ``get_org_settings`` and
``get_connections_for_tenant``.
"""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.auth import invitations
from dazzle.http.runtime.auth.connections import AssertedIdentity, ConnectionRecord
from dazzle.http.runtime.auth.domain_join import DomainNotAdmissibleError
from dazzle.http.runtime.auth.enterprise_login import provision_enterprise_login
from dazzle.http.runtime.auth.scim_provisioning import provision_scim_user

pytestmark = pytest.mark.gate

# A tenant that restricts membership to verified domains, with acme.test verified
# (acme.test is admissible; other.com / evil.test are not).
_RESTRICTED_SETTINGS = {
    "domain_join_policy": "admin_approval",
    "restrict_membership_to_verified_domains": True,
}
_OPEN_SETTINGS = {
    "domain_join_policy": "off",
    "restrict_membership_to_verified_domains": False,
}


def _conn(**over) -> ConnectionRecord:
    base = {
        "id": "conn-1",
        "tenant_id": "org-1",
        "type": "oidc",
        "provider": "native",
        "domains": ["acme.test"],
        "verified_domains": ["acme.test"],
        "config": {},
        "secrets": {"scim_bearer": "tok"},
        "group_mapping": {},
        "status": "active",
        "created_at": datetime(2026, 6, 20),
        "updated_at": datetime(2026, 6, 20),
    }
    base.update(over)
    return ConnectionRecord(**base)


class _User:
    def __init__(self, uid, email, verified=False):
        self.id = uid
        self.email = email
        self.email_verified = verified


class _Membership:
    def __init__(self, mid, tenant_id, identity_id, *, roles=None, external_id=None):
        self.id = mid
        self.tenant_id = tenant_id
        self.identity_id = identity_id
        self.roles = roles or []
        self.status = "active"
        self.external_id = external_id


class _Store:
    """Fake AuthStore covering the union of methods the three paths touch plus the
    admission gate's two reads (``get_org_settings`` / ``get_connections_for_tenant``).

    ``restrict`` toggles the per-tenant restriction; ``verified_domains`` is the
    connection's verified-domain set the gate unions over.
    """

    def __init__(
        self,
        *,
        restrict: bool,
        verified_domains=("acme.test",),
        users=None,
        invitation_row=None,
    ):
        self._restrict = restrict
        self._verified_domains = list(verified_domains)
        self._users = dict(users or {})
        self._users_by_id = {str(u.id): u for u in self._users.values()}
        self._memberships: list[_Membership] = []
        self._invitation_row = invitation_row
        self.created_memberships: list[_Membership] = []
        self._modifies: list[tuple] = []
        self._n = 0

    # ---- admission-gate reads ----
    def get_org_settings(self, tenant_id):
        return dict(_RESTRICTED_SETTINGS if self._restrict else _OPEN_SETTINGS)

    def get_connections_for_tenant(self, tenant_id):
        return [_conn(verified_domains=self._verified_domains)]

    # ---- identity / membership ----
    def get_user_by_email(self, email):
        return self._users.get(email)

    def get_user_by_id(self, uid):
        return self._users_by_id.get(str(uid))

    def create_user(self, *, email, password, username=None):
        assert password
        self._n += 1
        u = _User(f"00000000-0000-0000-0000-{self._n:012d}", email)
        self._users[email] = u
        self._users_by_id[str(u.id)] = u
        return u

    def mark_email_verified(self, user_id):
        u = self._users_by_id.get(str(user_id))
        if u is not None:
            u.email_verified = True
        return True

    def get_memberships_for_identity(self, identity_id):
        return [m for m in self._memberships if m.identity_id == identity_id]

    def get_membership_by_external_id(self, tenant_id, external_id):
        for m in self._memberships:
            if m.tenant_id == tenant_id and m.external_id == external_id:
                return m
        return None

    def create_membership(self, *, tenant_id, identity_id, roles=None, external_id=None, **kw):
        m = _Membership(
            f"mem-{tenant_id}-{identity_id}",
            tenant_id,
            identity_id,
            roles=roles,
            external_id=external_id,
        )
        self._memberships.append(m)
        self.created_memberships.append(m)
        return m

    # ---- invitation store interface ----
    def _execute(self, sql, params=None):
        return [self._invitation_row] if self._invitation_row is not None else []

    def _execute_modify(self, sql, params=None):
        self._modifies.append((sql, params))


def _invitation_row(*, org_id="org-1", email="x@other.com"):
    now = datetime.now(UTC)
    return {
        "token": "tok-1",
        "org_id": org_id,
        "email": email.strip().lower(),
        "roles": json.dumps(["member"]),
        "invited_by": "admin-1",
        "expires_at": (now + timedelta(hours=24)).isoformat(),
        "accepted_at": None,
        "created_at": now.isoformat(),
    }


def _asserted(email, *, groups=None, claims_source="id_token", **attrs):
    return AssertedIdentity(
        email=email, attributes=attrs, groups=groups or [], claims_source=claims_source
    )


# ---------------------------------------------------------------- invitations


def test_accept_invitation_rejects_off_domain_when_restricted() -> None:
    store = _Store(restrict=True, invitation_row=_invitation_row(email="x@other.com"))
    with pytest.raises(DomainNotAdmissibleError):
        invitations.accept_invitation(
            store, "tok-1", identity_id="u1", accepting_email="x@other.com", email_verified=True
        )
    assert not store.created_memberships  # gate fired before create


def test_accept_invitation_admits_on_domain_when_restricted() -> None:
    store = _Store(restrict=True, invitation_row=_invitation_row(email="jane@acme.test"))
    membership = invitations.accept_invitation(
        store, "tok-1", identity_id="u1", accepting_email="jane@acme.test", email_verified=True
    )
    assert membership.tenant_id == "org-1"
    assert len(store.created_memberships) == 1


def test_accept_invitation_unrestricted_admits_off_domain() -> None:
    store = _Store(restrict=False, invitation_row=_invitation_row(email="x@other.com"))
    membership = invitations.accept_invitation(
        store, "tok-1", identity_id="u1", accepting_email="x@other.com", email_verified=True
    )
    assert membership.tenant_id == "org-1"


# ------------------------------------------------------------- enterprise SSO


def test_enterprise_login_rejects_off_domain_when_restricted() -> None:
    # SSO has its own anti-hijack check against the connection's verified set, so to
    # prove the admission gate is REACHED (not just that anti-hijack fired) we restrict
    # with an empty tenant verified set: even an email the connection itself accepts is
    # then inadmissible, and only the admission gate can raise here.
    store = _Store(restrict=True, verified_domains=[])
    conn = _conn(verified_domains=["acme.test"])  # connection admits acme.test
    with pytest.raises(DomainNotAdmissibleError):
        provision_enterprise_login(store, conn, _asserted("jane@acme.test"))
    assert not store.created_memberships


def test_enterprise_login_admits_on_domain_when_restricted() -> None:
    store = _Store(restrict=True, verified_domains=["acme.test"])
    conn = _conn(verified_domains=["acme.test"])
    user, mid = provision_enterprise_login(store, conn, _asserted("jane@acme.test"))
    assert mid and len(store.created_memberships) == 1


def test_enterprise_login_unrestricted_admits() -> None:
    store = _Store(restrict=False, verified_domains=[])
    conn = _conn(verified_domains=["acme.test"])
    user, mid = provision_enterprise_login(store, conn, _asserted("jane@acme.test"))
    assert mid and len(store.created_memberships) == 1


# -------------------------------------------------------------------- SCIM


def test_scim_provision_rejects_off_domain_when_restricted() -> None:
    # As with SSO, SCIM's own _require_verified_domain enforces the connection set.
    # Restrict with an empty tenant verified set so the gate refuses even an
    # on-connection email, proving the gate is reached before create_membership.
    store = _Store(restrict=True, verified_domains=[])
    conn = _conn(type="scim", verified_domains=["acme.test"])
    with pytest.raises(DomainNotAdmissibleError):
        provision_scim_user(store, conn, email="jane@acme.test", external_id="ext-1", active=True)
    assert not store.created_memberships


def test_scim_provision_admits_on_domain_when_restricted() -> None:
    store = _Store(restrict=True, verified_domains=["acme.test"])
    conn = _conn(type="scim", verified_domains=["acme.test"])
    result = provision_scim_user(
        store, conn, email="jane@acme.test", external_id="ext-1", active=True
    )
    assert result.identity_id and len(store.created_memberships) == 1


def test_scim_provision_unrestricted_admits() -> None:
    store = _Store(restrict=False, verified_domains=[])
    conn = _conn(type="scim", verified_domains=["acme.test"])
    result = provision_scim_user(
        store, conn, email="jane@acme.test", external_id="ext-1", active=True
    )
    assert result.identity_id and len(store.created_memberships) == 1


def test_namespace_connection_not_required() -> None:
    # Guard: real call sites pass a frozen ConnectionRecord, not a namespace.
    assert isinstance(_conn(), ConnectionRecord)
    assert not isinstance(_conn(), SimpleNamespace)
