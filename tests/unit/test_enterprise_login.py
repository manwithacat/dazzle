"""Enterprise JIT identity-join kernel tests (auth Plan 4b.ii).

A fake store exercises the security-critical logic without Postgres: the
anti-hijack domain check, differential trust on claims_source, identity/membership
reuse-or-create, group→persona mapping, and the concurrent-create race.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from psycopg.errors import UniqueViolation

from dazzle.http.runtime.auth.connections import AssertedIdentity, ConnectionRecord
from dazzle.http.runtime.auth.enterprise_login import (
    EnterpriseLoginError,
    map_groups_to_roles,
    provision_enterprise_login,
)


def _conn(**over) -> ConnectionRecord:
    base = {
        "id": "conn-1",
        "tenant_id": "org-1",
        "type": "oidc",
        "provider": "native",
        "domains": ["acme.test"],
        "verified_domains": ["acme.test"],
        "config": {},
        "secrets": {},
        "group_mapping": {},
        "status": "active",
        "created_at": datetime(2026, 6, 5),
        "updated_at": datetime(2026, 6, 5),
    }
    base.update(over)
    return ConnectionRecord(**base)


def _asserted(email="jane@acme.test", *, groups=None, claims_source="id_token", **attrs):
    return AssertedIdentity(
        email=email, attributes=attrs, groups=groups or [], claims_source=claims_source
    )


class _FakeUser:
    def __init__(self, uid: str, email: str, email_verified: bool = False):
        self.id = uid
        self.email = email
        self.email_verified = email_verified


class _FakeMembership:
    def __init__(self, mid: str, tenant_id: str, identity_id: str, roles=None):
        self.id = mid
        self.tenant_id = tenant_id
        self.identity_id = identity_id
        self.roles = roles or []
        self.status = "active"


class _FakeStore:
    """Minimal AuthStore stand-in. ``create_membership_error`` injects a raise."""

    def __init__(self, *, users=None, memberships=None, create_membership_error=None):
        self._users = dict(users or {})  # email → _FakeUser
        self._memberships = list(memberships or [])
        self._created_users: list[_FakeUser] = []
        self._marked_verified: list[str] = []
        self._create_membership_error = create_membership_error
        self._next_uid = 100

    def get_user_by_email(self, email):
        return self._users.get(email)

    def create_user(self, *, email, password, username=None):
        assert password  # passwordless-but-unguessable
        uid = f"uid-{self._next_uid}"
        self._next_uid += 1
        u = _FakeUser(uid, email)
        self._users[email] = u
        self._created_users.append(u)
        return u

    def get_memberships_for_identity(self, identity_id):
        return [m for m in self._memberships if m.identity_id == identity_id]

    def mark_email_verified(self, user_id):
        for u in self._users.values():
            if str(u.id) == str(user_id):
                u.email_verified = True
                self._marked_verified.append(str(user_id))
                return True
        return False

    def create_membership(self, *, tenant_id, identity_id, roles=None, reason=None):
        if self._create_membership_error is not None:
            err = self._create_membership_error
            self._create_membership_error = None  # raise once, then allow retry-resolve
            raise err
        m = _FakeMembership(f"mem-{tenant_id}-{identity_id}", tenant_id, identity_id, roles)
        self._memberships.append(m)
        return m


# ---- anti-hijack ----


def test_domain_not_in_verified_domains_refuses() -> None:
    store = _FakeStore()
    conn = _conn(verified_domains=["acme.test"])
    with pytest.raises(EnterpriseLoginError) as ei:
        provision_enterprise_login(store, conn, _asserted("eve@evil.test"))
    assert ei.value.reason == "domain_not_verified"
    assert not store._created_users  # never created an identity for a rejected assertion


def test_no_verified_domains_refuses_everyone() -> None:
    store = _FakeStore()
    conn = _conn(verified_domains=[])
    with pytest.raises(EnterpriseLoginError) as ei:
        provision_enterprise_login(store, conn, _asserted("jane@acme.test"))
    assert ei.value.reason == "domain_not_verified"


def test_verified_domain_match_is_case_insensitive() -> None:
    store = _FakeStore()
    conn = _conn(verified_domains=["Acme.Test"])
    user, mid = provision_enterprise_login(store, conn, _asserted("Jane@ACME.test"))
    assert user.email == "jane@acme.test" and mid


def test_empty_email_refuses() -> None:
    store = _FakeStore()
    with pytest.raises(EnterpriseLoginError) as ei:
        provision_enterprise_login(store, _conn(), _asserted(""))
    assert ei.value.reason == "no_email"


# ---- differential trust ----


def test_unsigned_fallback_without_email_verified_refuses() -> None:
    store = _FakeStore()
    asserted = _asserted("jane@acme.test", claims_source="userinfo_endpoint")  # no email_verified
    with pytest.raises(EnterpriseLoginError) as ei:
        provision_enterprise_login(store, _conn(), asserted)
    assert ei.value.reason == "unverified_fallback"


def test_unsigned_fallback_with_email_verified_true_allowed() -> None:
    store = _FakeStore()
    asserted = _asserted("jane@acme.test", claims_source="userinfo_endpoint", email_verified=True)
    user, mid = provision_enterprise_login(store, _conn(), asserted)
    assert user.email == "jane@acme.test" and mid


def test_id_token_path_tolerates_missing_email_verified() -> None:
    store = _FakeStore()
    # id_token source, no email_verified attribute — allowed (authlib already validated).
    user, mid = provision_enterprise_login(store, _conn(), _asserted("jane@acme.test"))
    assert user.email == "jane@acme.test" and mid


# ---- identity reuse/create ----


def test_existing_identity_is_reused() -> None:
    existing = _FakeUser("uid-1", "jane@acme.test")
    store = _FakeStore(users={"jane@acme.test": existing})
    user, _ = provision_enterprise_login(store, _conn(), _asserted("jane@acme.test"))
    assert user is existing and not store._created_users


def test_absent_identity_is_created() -> None:
    store = _FakeStore()
    user, _ = provision_enterprise_login(store, _conn(), _asserted("new@acme.test"))
    assert user.email == "new@acme.test" and len(store._created_users) == 1


def test_provisioned_identity_is_marked_email_verified() -> None:
    # The org IdP vouched for the email within its verified domain → the global
    # identity must not linger as email_verified=False (M1).
    store = _FakeStore()
    user, _ = provision_enterprise_login(store, _conn(), _asserted("new@acme.test"))
    assert user.email_verified is True
    assert store._marked_verified == [str(user.id)]


def test_already_verified_identity_is_not_rewritten() -> None:
    existing = _FakeUser("uid-1", "jane@acme.test", email_verified=True)
    store = _FakeStore(users={"jane@acme.test": existing})
    provision_enterprise_login(store, _conn(), _asserted("jane@acme.test"))
    assert store._marked_verified == []  # no redundant write on every login


def test_existing_unverified_identity_is_marked_verified() -> None:
    existing = _FakeUser("uid-1", "jane@acme.test", email_verified=False)
    store = _FakeStore(users={"jane@acme.test": existing})
    provision_enterprise_login(store, _conn(), _asserted("jane@acme.test"))
    assert store._marked_verified == ["uid-1"]  # IdP proof verifies the mailbox


# ---- membership reuse/JIT-create ----


def test_existing_membership_reused_not_duplicated() -> None:
    existing = _FakeUser("uid-1", "jane@acme.test")
    mem = _FakeMembership("mem-existing", "org-1", "uid-1")
    store = _FakeStore(users={"jane@acme.test": existing}, memberships=[mem])
    _, mid = provision_enterprise_login(store, _conn(), _asserted("jane@acme.test"))
    assert mid == "mem-existing" and len(store._memberships) == 1


def test_membership_in_other_org_does_not_satisfy() -> None:
    existing = _FakeUser("uid-1", "jane@acme.test")
    other = _FakeMembership("mem-other", "org-2", "uid-1")  # different org
    store = _FakeStore(users={"jane@acme.test": existing}, memberships=[other])
    _, mid = provision_enterprise_login(
        store, _conn(tenant_id="org-1"), _asserted("jane@acme.test")
    )
    assert mid != "mem-other" and len(store._memberships) == 2  # JIT-created for org-1


def test_jit_disabled_refuses_when_no_membership() -> None:
    store = _FakeStore()
    conn = _conn(config={"jit_provisioning": False})
    with pytest.raises(EnterpriseLoginError) as ei:
        provision_enterprise_login(store, conn, _asserted("jane@acme.test"))
    assert ei.value.reason == "no_membership"


def test_jit_disabled_still_reuses_existing_membership() -> None:
    existing = _FakeUser("uid-1", "jane@acme.test")
    mem = _FakeMembership("mem-existing", "org-1", "uid-1")
    store = _FakeStore(users={"jane@acme.test": existing}, memberships=[mem])
    conn = _conn(config={"jit_provisioning": False})
    _, mid = provision_enterprise_login(store, conn, _asserted("jane@acme.test"))
    assert mid == "mem-existing"


# ---- group → persona mapping ----


def test_jit_membership_maps_groups_to_roles() -> None:
    store = _FakeStore()
    conn = _conn(group_mapping={"eng": "engineer", "ops": "operator"})
    provision_enterprise_login(
        store, conn, _asserted("jane@acme.test", groups=["eng", "ops", "unmapped"])
    )
    created = store._memberships[-1]
    assert created.roles == ["engineer", "operator"]  # unmapped group contributes nothing


def test_map_groups_to_roles_default_deny_and_dedup() -> None:
    assert map_groups_to_roles(["a", "b"], {}) == []  # nothing mapped → no roles
    assert map_groups_to_roles(["a", "x", "b"], {"a": "r1", "b": "r1"}) == ["r1"]  # dedup
    assert map_groups_to_roles(["a", "b"], {"a": "r1", "b": "r2"}) == ["r1", "r2"]


# ---- concurrent create race ----


def test_concurrent_unique_violation_reresolves() -> None:
    existing = _FakeUser("uid-1", "jane@acme.test")
    store = _FakeStore(
        users={"jane@acme.test": existing},
        create_membership_error=UniqueViolation("dup"),
    )
    # The reuse-scan saw nothing, create_membership raises UniqueViolation (a concurrent
    # login won the race) — simulate the winner's row appearing for the re-resolve.
    store._memberships.append(_FakeMembership("mem-winner", "org-1", "uid-1"))
    _, mid = provision_enterprise_login(store, _conn(), _asserted("jane@acme.test"))
    assert mid == "mem-winner"


def test_unique_violation_with_no_winner_row_reraises() -> None:
    store = _FakeStore(create_membership_error=UniqueViolation("dup"))
    # UniqueViolation but no membership materializes on re-scan → re-raise (don't swallow).
    with pytest.raises(UniqueViolation):
        provision_enterprise_login(store, _conn(), _asserted("ghost@acme.test"))


# ---- error never leaks the email ----


def test_error_message_omits_email() -> None:
    store = _FakeStore()
    conn = _conn(verified_domains=["acme.test"])
    try:
        provision_enterprise_login(store, conn, _asserted("secret-user@evil.test"))
    except EnterpriseLoginError as exc:
        assert "secret-user" not in str(exc)
    else:  # pragma: no cover
        pytest.fail("expected refusal")


# ---- sanity: SimpleNamespace connection shape is not required (frozen ConnectionRecord) ----


def test_uses_connection_record_not_namespace() -> None:
    # Guard against accidentally relying on a mutable namespace — the real call site
    # passes a frozen ConnectionRecord.
    assert isinstance(_conn(), ConnectionRecord)
    assert not isinstance(_conn(), SimpleNamespace)


def test_saml_assertion_source_is_trusted_without_email_verified() -> None:
    # A signature-validated SAML assertion is a trusted source (like an id_token) — the
    # join must NOT require email_verified for it (Plan 5.i trust-model generalization).
    store = _FakeStore()
    asserted = _asserted("jane@acme.test", claims_source="saml_assertion")  # no email_verified
    user, mid = provision_enterprise_login(store, _conn(), asserted)
    assert user.email == "jane@acme.test" and mid
