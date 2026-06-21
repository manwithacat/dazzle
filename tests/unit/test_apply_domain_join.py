"""Tests for apply_domain_join orchestration (#1424 phase 3)."""

import pytest

from dazzle.http.runtime.auth.domain_join import DomainNotAdmissibleError
from dazzle.http.runtime.auth.join_requests import apply_domain_join

# ---------------------------------------------------------------------------
# Minimal fake store pieces
# ---------------------------------------------------------------------------


class _FakeConn:
    def __init__(self, tenant_id: str, verified_domains: list[str]) -> None:
        self.tenant_id = tenant_id
        self.verified_domains = verified_domains


class _FakeMembership:
    def __init__(self, tenant_id: str, membership_id: str = "m1") -> None:
        self.tenant_id = tenant_id
        self.id = membership_id


class _FakeJoinRequest:
    def __init__(self, request_id: str = "jr1") -> None:
        self.id = request_id


class _BaseStore:
    """Shared stub — subclasses override what they need."""

    _tenant_id: str = "t1"
    _domain: str = "bigcorp.com"
    _settings: dict = {}
    _memberships: list = []

    def get_connection_by_verified_domain(self, domain: str) -> _FakeConn | None:
        if domain == self._domain:
            return _FakeConn(tenant_id=self._tenant_id, verified_domains=[self._domain])
        return None

    def get_connections_for_tenant(self, tenant_id: str) -> list[_FakeConn]:
        return [_FakeConn(tenant_id=self._tenant_id, verified_domains=[self._domain])]

    def get_org_settings(self, tenant_id: str) -> dict:
        return self._settings

    def get_memberships_for_identity(self, identity_id: str) -> list:
        return list(self._memberships)

    def create_membership(self, *, tenant_id, identity_id, roles, reason) -> _FakeMembership:
        raise NotImplementedError("override in subclass")

    def create_join_request(self, *, tenant_id, identity_id, email) -> _FakeJoinRequest:
        raise NotImplementedError("override in subclass")


class _AutoJoinStore(_BaseStore):
    _settings = {"domain_join_policy": "auto_join"}

    def create_membership(self, *, tenant_id, identity_id, roles, reason) -> _FakeMembership:
        assert roles == []
        assert reason == "verified-domain self-service join"
        return _FakeMembership(tenant_id=tenant_id)


class _ApprovalStore(_BaseStore):
    _settings = {"domain_join_policy": "admin_approval"}

    def create_join_request(self, *, tenant_id, identity_id, email) -> _FakeJoinRequest:
        return _FakeJoinRequest()


class _OffStore(_BaseStore):
    _settings = {"domain_join_policy": "off"}


class _EmptyStore(_BaseStore):
    """No matching verified domain."""

    def get_connection_by_verified_domain(self, domain: str) -> None:
        return None


class _PreexistingMemberStore(_BaseStore):
    """User already has a membership in the matched tenant → Noop."""

    _settings = {"domain_join_policy": "auto_join"}
    _memberships = [_FakeMembership(tenant_id="t1")]


class _RestrictedAutoJoinStore(_BaseStore):
    """restrict_membership_to_verified_domains=True but email is NOT in verified set.

    This tests that assert_domain_admissible is still called even for auto_join,
    and that DomainNotAdmissibleError propagates.
    """

    _domain = "corp.example"  # domain for the tenant connection
    _settings = {
        "domain_join_policy": "auto_join",
        "restrict_membership_to_verified_domains": True,
    }

    def get_connection_by_verified_domain(self, domain: str) -> _FakeConn | None:
        # The domain lookup succeeds (so the tenant IS found) …
        if domain == "corp.example":
            return _FakeConn(tenant_id=self._tenant_id, verified_domains=["corp.example"])
        return None

    def get_connections_for_tenant(self, tenant_id: str) -> list[_FakeConn]:
        # … but the connections list does NOT contain the caller's email domain.
        # Simulating: tenant verifies corp.example but the email is outsider@other.com.
        return [_FakeConn(tenant_id=self._tenant_id, verified_domains=[])]

    def create_membership(self, *, tenant_id, identity_id, roles, reason) -> _FakeMembership:
        # Should not be reached.
        raise AssertionError("create_membership called despite domain not admissible")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_auto_join_creates_membership():
    store = _AutoJoinStore()
    res = apply_domain_join(store, identity_id="u1", email="a@bigcorp.com", email_verified=True)
    assert res.kind == "joined"
    assert res.membership_id is not None


def test_admin_approval_creates_request():
    store = _ApprovalStore()
    res = apply_domain_join(store, identity_id="u1", email="a@bigcorp.com", email_verified=True)
    assert res.kind == "pending"


def test_off_policy_returns_none():
    store = _OffStore()
    res = apply_domain_join(store, identity_id="u1", email="a@bigcorp.com", email_verified=True)
    assert res.kind == "none"


def test_no_tenant_is_none():
    store = _EmptyStore()
    res = apply_domain_join(store, identity_id="u1", email="a@unknown.com", email_verified=True)
    assert res.kind == "none"


def test_unverified_email_is_none():
    """Caller passes email_verified=False → short-circuit before any tenant lookup → "none".

    The store's get_connection_by_verified_domain raises if called, proving the
    early return fires before the DB round-trip (M2 hardening, #1424).
    """

    class _RaisesOnLookupStore(_AutoJoinStore):
        def get_connection_by_verified_domain(self, domain: str) -> None:  # type: ignore[override]
            raise AssertionError(
                "get_connection_by_verified_domain must not be called for unverified email"
            )

    store = _RaisesOnLookupStore()
    res = apply_domain_join(store, identity_id="u1", email="a@bigcorp.com", email_verified=False)
    assert res.kind == "none"


def test_preexisting_membership_is_none():
    """Identity already has membership in the matched tenant → Noop."""
    store = _PreexistingMemberStore()
    res = apply_domain_join(store, identity_id="u1", email="a@bigcorp.com", email_verified=True)
    assert res.kind == "none"


def test_restricted_off_domain_auto_join_raises():
    """Even when policy=auto_join, assert_domain_admissible must run and raise when
    the tenant restricts to verified domains but the email domain is not in the set."""
    store = _RestrictedAutoJoinStore()
    with pytest.raises(DomainNotAdmissibleError):
        apply_domain_join(
            store, identity_id="u1", email="outsider@corp.example", email_verified=True
        )
