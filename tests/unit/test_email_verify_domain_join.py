"""Verified-domain self-service join evaluated at email verification (#1424 Task 3.4).

This is the path that lets a fresh password signup — created *unverified* — join
once they verify their email. After ``GET /auth/verify-email`` validates the
token, marks the email verified, and emits the ``email_verified`` event, the
handler calls ``apply_domain_join``:

  * ``auto_join`` tenant → a membership is created; the normal success redirect
    (``?verified=ok``) still applies — the next authenticated request routes via
    apex discovery.
  * ``admin_approval`` tenant → no membership; redirect to ``/auth/join-requested``.

A join hiccup must NEVER break verification: if ``apply_domain_join`` raises, the
email is still verified and the handler still redirects with ``verified=ok``.

These tests drive the route end-to-end via a ``TestClient`` against a fake auth
store that exposes the domain-join reads, patching only the token primitive.
"""

import logging
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.email_verification_routes import (
    create_email_verification_routes,
)
from dazzle.http.runtime.auth.models import MembershipRecord

_TENANT_ID = "t-bigcorp"
_DOMAIN = "bigcorp.com"
_USER_ID = "user-123"
_EMAIL = f"alice@{_DOMAIN}"


class _FakeUser:
    def __init__(self, email: str) -> None:
        self.email = email
        self.email_verified = True


class _FakeConn:
    def __init__(self, tenant_id: str, verified_domains: list[str]) -> None:
        self.tenant_id = tenant_id
        self.verified_domains = verified_domains


class _DomainJoinStore:
    """Fake auth store: a verified user with no membership in a tenant that owns
    the user's email domain. ``domain_join_policy`` is parametrised."""

    def __init__(self, *, policy: str) -> None:
        self._policy = policy
        self._memberships: list[MembershipRecord] = []
        self.created_join_requests: list[dict[str, Any]] = []
        self.created_memberships: list[MembershipRecord] = []

    # ── route read: user lookup after token validation ─────────────────────
    def get_user_by_id(self, user_id: str) -> _FakeUser:
        return _FakeUser(_EMAIL)

    # ── domain-join reads ──────────────────────────────────────────────────
    def get_memberships_for_identity(self, identity_id: str) -> list[MembershipRecord]:
        return list(self._memberships)

    def get_connection_by_verified_domain(self, domain: str) -> _FakeConn | None:
        if domain == _DOMAIN:
            return _FakeConn(tenant_id=_TENANT_ID, verified_domains=[_DOMAIN])
        return None

    def get_connections_for_tenant(self, tenant_id: str) -> list[_FakeConn]:
        return [_FakeConn(tenant_id=_TENANT_ID, verified_domains=[_DOMAIN])]

    def get_org_settings(self, tenant_id: str) -> dict[str, Any]:
        return {"domain_join_policy": self._policy}

    # ── domain-join writes ─────────────────────────────────────────────────
    def create_membership(
        self, *, tenant_id: str, identity_id: str, roles: list[str], reason: str
    ) -> MembershipRecord:
        membership = MembershipRecord(
            id=f"m-{len(self._memberships) + 1}",
            tenant_id=tenant_id,
            identity_id=identity_id,
            roles=roles,
            status="active",
        )
        self._memberships.append(membership)
        self.created_memberships.append(membership)
        return membership

    def create_join_request(
        self, *, tenant_id: str, identity_id: str, email: str
    ) -> dict[str, Any]:
        record = {"tenant_id": tenant_id, "identity_id": identity_id, "email": email}
        self.created_join_requests.append(record)
        return {"id": f"jr-{len(self.created_join_requests)}", **record}


def _client(store: Any) -> TestClient:
    app = FastAPI()
    app.state.auth_store = store
    app.include_router(create_email_verification_routes())
    return TestClient(app, follow_redirects=False)


def _verify(client: TestClient) -> Any:
    with patch(
        "dazzle.http.runtime.auth.email_verification_routes.validate_email_verification_token",
        return_value=_USER_ID,
    ):
        return client.get("/auth/verify-email?token=valid")


def test_auto_join_creates_membership_and_redirects_ok() -> None:
    store = _DomainJoinStore(policy="auto_join")
    response = _verify(_client(store))

    assert response.status_code == 303
    # A membership was created via the verified-domain join …
    assert len(store.created_memberships) == 1
    assert store.created_memberships[0].tenant_id == _TENANT_ID
    assert store.created_join_requests == []
    # … and the normal success redirect still applies (apex discovery routes
    # the next authenticated request).
    assert "verified=ok" in response.headers["location"]
    assert response.headers["location"] != "/auth/join-requested"


def test_admin_approval_creates_join_request_and_redirects_to_join_requested() -> None:
    store = _DomainJoinStore(policy="admin_approval")
    response = _verify(_client(store))

    assert response.status_code == 303
    # No membership created; a join request was recorded instead.
    assert store.created_memberships == []
    assert len(store.created_join_requests) == 1
    assert store.created_join_requests[0]["tenant_id"] == _TENANT_ID
    assert response.headers["location"] == "/auth/join-requested"


def test_apply_domain_join_exception_does_not_break_verification(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """If apply_domain_join raises, the email is still verified and the handler
    still redirects with verified=ok (no 500, no join-requested page)."""
    store = _DomainJoinStore(policy="auto_join")
    client = _client(store)

    def _boom(*args: object, **kwargs: object) -> object:  # noqa: ARG001
        raise RuntimeError("DB connection lost")

    import dazzle.http.runtime.auth.join_requests as _jr

    monkeypatch.setattr(_jr, "apply_domain_join", _boom)

    logger_name = "dazzle.http.runtime.auth.email_verification_routes"
    with caplog.at_level(logging.WARNING, logger=logger_name):
        response = _verify(client)

    # Verification must succeed — not a 500, not the join-requested page.
    assert response.status_code == 303
    assert "verified=ok" in response.headers["location"]
    assert response.headers["location"] != "/auth/join-requested"
    assert store.created_memberships == []
    assert store.created_join_requests == []
    # A warning was emitted.
    assert any("Domain-join evaluation failed" in r.message for r in caplog.records)
