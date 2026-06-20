"""SCIM provisioning kernel tests (auth Plan 4c.i).

A fake store exercises anti-hijack, create/update/deactivate/deprovision, the
deactivate→suspend+revoke semantics, org-scoping, and idempotency without Postgres.
"""

from datetime import datetime

import pytest

from dazzle.http.runtime.auth.connections import ConnectionRecord
from dazzle.http.runtime.auth.scim_provisioning import (
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
    def __init__(
        self, mid, tenant_id, identity_id, *, roles=None, status="active", external_id=None
    ):
        self.id = mid
        self.tenant_id = tenant_id
        self.identity_id = identity_id
        self.roles = roles or []
        self.status = status
        self.external_id = external_id


class _Store:
    def __init__(self, *, users=None, memberships=None):
        self._users = dict(users or {})
        self._memberships = list(memberships or [])
        # by-id index so _identity_email (UUID lookup) resolves; uids are valid UUID strings.
        self._users_by_id = {str(u.id): u for u in self._users.values()}
        self.created_users = []
        self.marked_verified = []
        self.suspended = []
        self.reactivated = []
        self.removed = []
        self.role_updates = []
        self.sessions_revoked = []
        self.external_id_updates = []
        self._n = 0

    def get_user_by_email(self, email):
        return self._users.get(email)

    # #1424 admission gate reads. Default: tenant does NOT restrict, so
    # assert_domain_admissible is a no-op and these tests exercise the
    # pre-existing (unrestricted) behaviour.
    def get_org_settings(self, tenant_id):
        return {}

    def get_connections_for_tenant(self, tenant_id):
        return []

    def get_user_by_id(self, uid):
        return self._users_by_id.get(str(uid))

    def create_user(self, *, email, password, username=None):
        self._n += 1
        u = _User(f"00000000-0000-0000-0000-{self._n:012d}", email)
        self._users[email] = u
        self._users_by_id[str(u.id)] = u
        self.created_users.append(u)
        return u

    def mark_email_verified(self, user_id):
        self.marked_verified.append(str(user_id))
        return True

    def get_memberships_for_identity(self, identity_id):
        return [m for m in self._memberships if m.identity_id == identity_id]

    def get_membership_by_external_id(self, tenant_id, external_id):
        for m in self._memberships:
            if m.tenant_id == tenant_id and getattr(m, "external_id", None) == external_id:
                return m
        return None

    def create_membership(
        self, *, tenant_id, identity_id, roles=None, external_id=None, reason=None
    ):
        m = _Membership(
            f"mem-{tenant_id}-{identity_id}",
            tenant_id,
            identity_id,
            roles=roles,
            external_id=external_id,
        )
        self._memberships.append(m)
        return m

    def update_membership_external_id(self, membership_id, external_id):
        self.external_id_updates.append((membership_id, external_id))
        for m in self._memberships:
            if m.id == membership_id:
                m.external_id = external_id
                return m
        return None

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


def test_parse_group_patch_ops() -> None:
    from dazzle.http.runtime.auth.scim_provisioning import parse_group_patch

    ops = parse_group_patch(
        {
            "Operations": [
                {"op": "add", "path": "members", "value": [{"value": "m1"}, {"value": "m2"}]},
                {"op": "remove", "path": 'members[value eq "m3"]'},
                {"op": "replace", "path": "displayName", "value": "NewName"},
            ]
        }
    )
    assert ("add_members", ["m1", "m2"]) in ops
    assert ("remove_member", "m3") in ops
    assert ("rename", "NewName") in ops


def test_parse_group_patch_remove_all_and_replace_members() -> None:
    from dazzle.http.runtime.auth.scim_provisioning import parse_group_patch

    ops = parse_group_patch(
        {
            "Operations": [
                {"op": "remove", "path": "members"},
                {"op": "replace", "path": "members", "value": [{"value": "m9"}]},
                {"op": "replace", "value": {"displayName": "X"}},  # no-path replace form
            ]
        }
    )
    assert ("replace_members", []) in ops  # remove-all
    assert ("replace_members", ["m9"]) in ops
    assert ("rename", "X") in ops


def test_parse_group_patch_skips_unknown_ops() -> None:
    from dazzle.http.runtime.auth.scim_provisioning import parse_group_patch

    assert (
        parse_group_patch({"Operations": [{"op": "add", "path": "externalId", "value": "x"}]}) == []
    )
    assert parse_group_patch({}) == []


# ---- externalId echo + dedup (#1342 gap 1) ----

# a valid-UUID identity id so _identity_email (UUID lookup) resolves for mismatch logging
_UID = "11111111-1111-1111-1111-111111111111"


def test_provision_captures_external_id_on_create() -> None:
    store = _Store()
    res = provision_scim_user(store, _conn(), email="jane@acme.test", external_id="guid-1")
    m = store._memberships[-1]
    assert m.external_id == "guid-1"
    assert res.membership_id == m.id


def test_provision_dedup_by_external_id_under_changed_email() -> None:
    # The IdP renamed the mailbox but re-pushed the same externalId. We must update the
    # EXISTING membership, not fork a new identity.
    u = _User(_UID, "old@acme.test", verified=True)
    m = _Membership("mem-1", "org-1", _UID, external_id="guid-1")
    store = _Store(users={"old@acme.test": u}, memberships=[m])

    res = provision_scim_user(store, _conn(), email="new@acme.test", external_id="guid-1")

    assert res.membership_id == "mem-1"  # same membership
    assert not store.created_users  # no duplicate identity forked
    assert len(store._memberships) == 1
    assert u.email == "old@acme.test"  # global identity email NOT rewritten
    assert "new@acme.test" not in store._users  # no new identity under the new email


def test_provision_external_id_mismatch_logs_loud_warning(caplog) -> None:
    u = _User(_UID, "old@acme.test", verified=True)
    m = _Membership("mem-1", "org-1", _UID, external_id="guid-1")
    store = _Store(users={"old@acme.test": u}, memberships=[m])

    with caplog.at_level("WARNING"):
        provision_scim_user(store, _conn(), email="new@acme.test", external_id="guid-1")

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("externalId" in r.getMessage() and "guid-1" in r.getMessage() for r in warnings)


def test_provision_external_id_match_same_email_no_warning(caplog) -> None:
    u = _User(_UID, "jane@acme.test", verified=True)
    m = _Membership("mem-1", "org-1", _UID, external_id="guid-1")
    store = _Store(users={"jane@acme.test": u}, memberships=[m])

    with caplog.at_level("WARNING"):
        provision_scim_user(store, _conn(), email="jane@acme.test", external_id="guid-1")

    assert [r for r in caplog.records if r.levelname == "WARNING"] == []


def test_provision_dedup_syncs_active_state() -> None:
    u = _User(_UID, "jane@acme.test", verified=True)
    m = _Membership("mem-1", "org-1", _UID, status="active", external_id="guid-1")
    store = _Store(users={"jane@acme.test": u}, memberships=[m])

    provision_scim_user(store, _conn(), email="jane@acme.test", external_id="guid-1", active=False)

    assert store.suspended == ["mem-1"] and store.sessions_revoked == ["mem-1"]


def test_provision_backfills_external_id_on_email_matched_membership() -> None:
    # Existing membership found by email with no stored externalId — first push that carries
    # one should backfill it so future renamed-email re-pushes resolve via the stable id.
    u = _User(_UID, "jane@acme.test", verified=True)
    m = _Membership("mem-1", "org-1", _UID)  # no external_id yet
    store = _Store(users={"jane@acme.test": u}, memberships=[m])

    provision_scim_user(store, _conn(), email="jane@acme.test", external_id="guid-1")

    assert store.external_id_updates == [("mem-1", "guid-1")]
    assert m.external_id == "guid-1"


def test_provision_without_external_id_preserves_email_keyed_behaviour() -> None:
    store = _Store()
    res = provision_scim_user(store, _conn(), email="jane@acme.test")
    assert store._memberships[-1].external_id is None
    assert res.active is True


# ---- concurrent (tenant_id, external_id) unique-index collision → converge, not 500 ----


def _unique_violation():
    import psycopg

    return psycopg.errors.UniqueViolation(
        "duplicate key value violates uq_memberships_tenant_external"
    )


def test_provision_create_race_converges_on_winner() -> None:
    # Two parallel pushes for a new externalId: both miss the lookup, the loser's INSERT trips
    # the unique index. We must converge on the winner's membership, not raise a 500.
    winner = _Membership("mem-winner", "org-1", _UID, external_id="guid-1", status="active")

    class _RaceStore(_Store):
        def __init__(self):
            super().__init__()
            self._winner_visible = False

        def get_membership_by_external_id(self, tenant_id, external_id):
            # invisible on the dedup-first lookup, visible after the failed INSERT (the race)
            if self._winner_visible and external_id == "guid-1":
                return winner
            return None

        def create_membership(self, **kw):
            self._winner_visible = True
            raise _unique_violation()

    store = _RaceStore()
    res = provision_scim_user(
        store, _conn(), email="jane@acme.test", external_id="guid-1", active=False
    )
    assert res.membership_id == "mem-winner"
    assert store.suspended == ["mem-winner"]  # active flag synced onto the winner


def test_provision_backfill_collision_converges_and_warns(caplog) -> None:
    # email resolves to membership B; the pushed externalId already names membership A in-org.
    u = _User(_UID, "jane@acme.test", verified=True)
    b = _Membership("mem-B", "org-1", _UID)  # email-matched (jane's), no external_id
    # the externalId already names a DIFFERENT membership/identity in the same org
    a = _Membership("mem-A", "org-1", "22222222-2222-2222-2222-222222222222", external_id="guid-1")

    class _CollideStore(_Store):
        def get_membership_by_external_id(self, tenant_id, external_id):
            # invisible on dedup-first (forces the email path), visible on convergence re-read
            return a if getattr(self, "_collided", False) and external_id == "guid-1" else None

        def update_membership_external_id(self, membership_id, external_id):
            self._collided = True
            raise _unique_violation()

    store = _CollideStore(users={"jane@acme.test": u}, memberships=[a, b])
    with caplog.at_level("WARNING"):
        res = provision_scim_user(store, _conn(), email="jane@acme.test", external_id="guid-1")
    assert res.membership_id == "mem-A"  # converged on the externalId's membership
    assert any("collided on backfill" in r.getMessage() for r in caplog.records)


def test_provision_non_unique_db_error_is_not_swallowed() -> None:
    # A create failure that ISN'T a uniqueness hit must propagate, not be silently converged.
    class _BoomStore(_Store):
        def create_membership(self, **kw):
            raise RuntimeError("connection lost")

    with pytest.raises(RuntimeError, match="connection lost"):
        provision_scim_user(_BoomStore(), _conn(), email="jane@acme.test", external_id="guid-1")
