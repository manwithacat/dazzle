"""SCIM provisioning kernel tests (auth Plan 4c.i).

A fake store exercises anti-hijack, create/update/deactivate/deprovision, the
deactivate→suspend+revoke semantics, org-scoping, and idempotency without Postgres.
"""

from datetime import datetime

import pytest

from dazzle.back.runtime.auth.connections import ConnectionRecord
from dazzle.back.runtime.auth.scim_provisioning import (
    ScimError,
    deprovision_scim_user,
    provision_scim_user,
    set_scim_user_active,
)


def _conn(**over) -> ConnectionRecord:
    base = {
        "id": "conn-1",
        "tenant_id": "org-1",
        "type": "scim",
        "provider": "native",
        "domains": ["acme.test"],
        "verified_domains": ["acme.test"],
        "config": {},
        "secrets": {"scim_bearer": "tok"},
        "group_mapping": {},
        "status": "active",
        "created_at": datetime(2026, 6, 6),
        "updated_at": datetime(2026, 6, 6),
    }
    base.update(over)
    return ConnectionRecord(**base)


class _User:
    def __init__(self, uid, email, verified=False):
        self.id = uid
        self.email = email
        self.email_verified = verified


class _Membership:
    def __init__(self, mid, tenant_id, identity_id, *, roles=None, status="active"):
        self.id = mid
        self.tenant_id = tenant_id
        self.identity_id = identity_id
        self.roles = roles or []
        self.status = status


class _Store:
    def __init__(self, *, users=None, memberships=None):
        self._users = dict(users or {})
        self._memberships = list(memberships or [])
        self.created_users = []
        self.marked_verified = []
        self.suspended = []
        self.reactivated = []
        self.removed = []
        self.role_updates = []
        self.sessions_revoked = []
        self._n = 0

    def get_user_by_email(self, email):
        return self._users.get(email)

    def create_user(self, *, email, password, username=None):
        self._n += 1
        u = _User(f"uid-{self._n}", email)
        self._users[email] = u
        self.created_users.append(u)
        return u

    def mark_email_verified(self, user_id):
        self.marked_verified.append(str(user_id))
        return True

    def get_memberships_for_identity(self, identity_id):
        return [m for m in self._memberships if m.identity_id == identity_id]

    def create_membership(self, *, tenant_id, identity_id, roles=None, reason=None):
        m = _Membership(f"mem-{tenant_id}-{identity_id}", tenant_id, identity_id, roles=roles)
        self._memberships.append(m)
        return m

    def suspend_membership(self, membership_id, *, reason=None):
        self.suspended.append(membership_id)
        for m in self._memberships:
            if m.id == membership_id:
                m.status = "suspended"
                return m
        return None

    def reactivate_membership(self, membership_id, *, reason=None):
        self.reactivated.append(membership_id)
        for m in self._memberships:
            if m.id == membership_id:
                m.status = "active"
                return m
        return None

    def remove_membership(self, membership_id, *, reason=None):
        before = len(self._memberships)
        self._memberships = [m for m in self._memberships if m.id != membership_id]
        ok = len(self._memberships) < before
        if ok:
            self.removed.append(membership_id)
        return ok

    def update_membership_roles(self, membership_id, roles, *, reason=None):
        self.role_updates.append((membership_id, roles))
        for m in self._memberships:
            if m.id == membership_id:
                m.roles = roles
                return m
        return None

    def delete_sessions_for_membership(self, membership_id):
        self.sessions_revoked.append(membership_id)
        return 1


# ---- anti-hijack ----


def test_provision_rejects_unverified_domain() -> None:
    store = _Store()
    with pytest.raises(ScimError) as ei:
        provision_scim_user(store, _conn(verified_domains=["acme.test"]), email="x@evil.test")
    assert ei.value.reason == "domain_not_verified"
    assert not store.created_users


def test_provision_no_verified_domains_rejects_all() -> None:
    store = _Store()
    with pytest.raises(ScimError):
        provision_scim_user(store, _conn(verified_domains=[]), email="x@acme.test")


def test_provision_empty_email_rejects() -> None:
    with pytest.raises(ScimError) as ei:
        provision_scim_user(_Store(), _conn(), email="")
    assert ei.value.reason == "no_email"


# ---- create ----


def test_provision_creates_identity_and_active_membership() -> None:
    store = _Store()
    res = provision_scim_user(
        store, _conn(group_mapping={"eng": "engineer"}), email="Jane@Acme.test", groups=["eng", "x"]
    )
    assert res.active is True and res.identity_id and res.membership_id
    m = store._memberships[-1]
    # #1342: the `groups` attribute is informational — roles are owned by /Groups,
    # so a SCIM User create no longer derives roles from `groups`.
    assert m.tenant_id == "org-1" and m.status == "active" and m.roles == []
    assert store.marked_verified == [res.identity_id]  # SSO/SCIM-vouched email


def test_provision_inactive_creates_then_suspends() -> None:
    store = _Store()
    res = provision_scim_user(store, _conn(), email="x@acme.test", active=False)
    assert res.active is False
    assert store.suspended == [res.membership_id]


def test_provision_reuses_existing_identity() -> None:
    existing = _User("uid-9", "jane@acme.test", verified=True)
    store = _Store(users={"jane@acme.test": existing})
    provision_scim_user(store, _conn(), email="jane@acme.test")
    assert not store.created_users and store.marked_verified == []  # already verified


# ---- update / sync ----


def test_provision_does_not_sync_roles_from_groups_attribute() -> None:
    # #1342 clean-break: roles are owned by the /Groups endpoint (RFC: User.groups
    # is server-managed). A User push with a `groups` attribute does NOT add/remove
    # roles on the membership — de-escalation now happens via /Groups membership.
    u = _User("uid-1", "jane@acme.test", verified=True)
    m = _Membership("mem-1", "org-1", "uid-1", roles=["existing"])
    store = _Store(users={"jane@acme.test": u}, memberships=[m])
    provision_scim_user(
        store, _conn(group_mapping={"eng": "engineer"}), email="jane@acme.test", groups=["eng"]
    )
    assert store.role_updates == []  # roles untouched — /Groups owns them
    assert m.roles == ["existing"]


def test_provision_reactivates_suspended_on_active_true() -> None:
    u = _User("uid-1", "jane@acme.test", verified=True)
    m = _Membership("mem-1", "org-1", "uid-1", status="suspended")
    store = _Store(users={"jane@acme.test": u}, memberships=[m])
    provision_scim_user(store, _conn(), email="jane@acme.test", active=True)
    assert store.reactivated == ["mem-1"]


def test_provision_active_false_suspends_and_revokes() -> None:
    u = _User("uid-1", "jane@acme.test", verified=True)
    m = _Membership("mem-1", "org-1", "uid-1", status="active")
    store = _Store(users={"jane@acme.test": u}, memberships=[m])
    provision_scim_user(store, _conn(), email="jane@acme.test", active=False)
    assert store.suspended == ["mem-1"] and store.sessions_revoked == ["mem-1"]


# ---- set_active ----


def test_set_active_false_suspends_and_revokes() -> None:
    m = _Membership("mem-1", "org-1", "uid-1", status="active")
    store = _Store(memberships=[m])
    mid = set_scim_user_active(store, _conn(), identity_id="uid-1", active=False)
    assert mid == "mem-1"
    assert store.suspended == ["mem-1"] and store.sessions_revoked == ["mem-1"]


def test_set_active_true_reactivates() -> None:
    m = _Membership("mem-1", "org-1", "uid-1", status="suspended")
    store = _Store(memberships=[m])
    set_scim_user_active(store, _conn(), identity_id="uid-1", active=True)
    assert store.reactivated == ["mem-1"]


def test_set_active_idempotent_no_op() -> None:
    m = _Membership("mem-1", "org-1", "uid-1", status="active")
    store = _Store(memberships=[m])
    set_scim_user_active(store, _conn(), identity_id="uid-1", active=True)  # already active
    assert store.suspended == [] and store.reactivated == []


def test_set_active_unknown_membership_raises() -> None:
    with pytest.raises(ScimError) as ei:
        set_scim_user_active(_Store(), _conn(), identity_id="ghost", active=False)
    assert ei.value.reason == "not_found"


# ---- org-scoping ----


def test_operations_are_scoped_to_connection_org() -> None:
    # The identity has a membership in a DIFFERENT org; this connection (org-1) must
    # not touch it — it provisions a new org-1 membership instead.
    u = _User("uid-1", "jane@acme.test", verified=True)
    other = _Membership("mem-other", "org-2", "uid-1", status="active")
    store = _Store(users={"jane@acme.test": u}, memberships=[other])
    res = provision_scim_user(store, _conn(tenant_id="org-1"), email="jane@acme.test")
    assert res.membership_id != "mem-other"
    assert other.status == "active"  # org-2 untouched
    # Deactivating via org-1's connection must not suspend org-2's membership.
    set_scim_user_active(store, _conn(tenant_id="org-1"), identity_id="uid-1", active=False)
    assert "mem-other" not in store.suspended


# ---- deprovision ----


def test_deprovision_removes_and_revokes() -> None:
    m = _Membership("mem-1", "org-1", "uid-1", status="active")
    store = _Store(memberships=[m])
    assert deprovision_scim_user(store, _conn(), identity_id="uid-1") is True
    assert store.removed == ["mem-1"] and store.sessions_revoked == ["mem-1"]


def test_deprovision_idempotent_when_absent() -> None:
    assert deprovision_scim_user(_Store(), _conn(), identity_id="ghost") is False
