import pytest

from dazzle.http.runtime.auth.domain_join import (
    DomainNotAdmissibleError,
    assert_domain_admissible,
    email_domain,
    tenant_verified_domains,
)


class _Conn:
    def __init__(self, verified):
        self.verified_domains = verified


class _Store:
    def __init__(self, settings, conns):
        self._s = settings
        self._c = conns

    def get_org_settings(self, t):
        return self._s

    def get_connections_for_tenant(self, t):
        return self._c


def test_email_domain_lowercased():
    assert email_domain("Alice@BigCorp.COM") == "bigcorp.com"


def test_union_of_verified_domains():
    store = _Store({}, [_Conn(["a.com"]), _Conn(["B.com", "a.com"])])
    assert tenant_verified_domains(store, "t1") == {"a.com", "b.com"}


def test_admissible_noop_when_unrestricted():
    store = _Store({"restrict_membership_to_verified_domains": False}, [])
    assert_domain_admissible(store, "t1", "x@anywhere.com")  # no raise


def test_restricted_rejects_outside_domain():
    store = _Store({"restrict_membership_to_verified_domains": True}, [_Conn(["bigcorp.com"])])
    with pytest.raises(DomainNotAdmissibleError):
        assert_domain_admissible(store, "t1", "x@other.com")


def test_restricted_allows_verified_domain():
    store = _Store({"restrict_membership_to_verified_domains": True}, [_Conn(["bigcorp.com"])])
    assert_domain_admissible(store, "t1", "x@BigCorp.com")  # no raise
