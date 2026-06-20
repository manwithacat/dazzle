"""Verified-domain self-service join evaluated at password login (#1424 Task 3.3).

After a successful password login with **no** resolved membership, if the
authenticating identity's email is verified, ``submit_login_password`` calls
``apply_domain_join``:

  * ``auto_join`` tenant → a membership is created, the session re-activates and
    binds the new membership, redirect goes to the host path (``/app``).
  * ``admin_approval`` tenant → no membership; redirect to ``/auth/join-requested``.

These tests drive the route end-to-end via a ``TestClient`` against a fake
auth store that exposes the domain-join reads plus the activation reads.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth import hash_password
from dazzle.http.runtime.auth.models import (
    MembershipRecord,
    SessionRecord,
    UserRecord,
)
from dazzle.http.runtime.auth.password_login_routes import (
    create_password_login_routes,
)

_TENANT_ID = "t-bigcorp"
_DOMAIN = "bigcorp.com"


class _FakeConn:
    def __init__(self, tenant_id: str, verified_domains: list[str]) -> None:
        self.tenant_id = tenant_id
        self.verified_domains = verified_domains


class _DomainJoinStore:
    """Fake auth store: a verified user with no membership in a tenant that
    owns the user's email domain. ``domain_join_policy`` is parametrised."""

    def __init__(self, *, policy: str, user: UserRecord) -> None:
        self._policy = policy
        self._user = user
        self._memberships: list[MembershipRecord] = []
        self.created_join_requests: list[dict[str, Any]] = []
        self.created_memberships: list[MembershipRecord] = []
        self.sessions: list[SessionRecord] = []

    # ── Phase 1: authenticate ──────────────────────────────────────────────
    def authenticate(self, email: str, password: str) -> UserRecord | None:
        if email == self._user.email and password:
            return self._user
        return None

    # ── Phase 2: activation reads ──────────────────────────────────────────
    def get_memberships_for_identity(self, identity_id: str) -> list[MembershipRecord]:
        return list(self._memberships)

    # ── domain-join reads ──────────────────────────────────────────────────
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
        # Make the new membership visible to the next activation read — this is
        # what lets the re-run of activate_session_for_login resolve Activated.
        self._memberships.append(membership)
        self.created_memberships.append(membership)
        return membership

    def create_join_request(
        self, *, tenant_id: str, identity_id: str, email: str
    ) -> dict[str, Any]:
        record = {"tenant_id": tenant_id, "identity_id": identity_id, "email": email}
        self.created_join_requests.append(record)
        return {"id": f"jr-{len(self.created_join_requests)}", **record}

    # ── session writes ─────────────────────────────────────────────────────
    def create_session(
        self, user: UserRecord, active_membership_id: str | None = None
    ) -> SessionRecord:
        session = SessionRecord(
            id=secrets.token_urlsafe(16),
            user_id=user.id,
            active_membership_id=active_membership_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=60),
        )
        self.sessions.append(session)
        return session

    def delete_session(self, sid: str) -> None:  # pragma: no cover - no pre-auth cookie
        pass


def _make_verified_user(email: str = f"alice@{_DOMAIN}") -> UserRecord:
    return UserRecord(email=email, password_hash=hash_password("password"), email_verified=True)


def _client(store: Any) -> TestClient:
    app = FastAPI()
    app.state.auth_store = store
    app.include_router(create_password_login_routes())
    return TestClient(app, follow_redirects=False)


def test_auto_join_binds_membership_and_redirects_to_host() -> None:
    user = _make_verified_user()
    store = _DomainJoinStore(policy="auto_join", user=user)
    client = _client(store)

    response = client.post(
        "/auth/login/password",
        data={"email": user.email, "password": "password"},
    )

    assert response.status_code == 303
    # A membership was created via the verified-domain join …
    assert len(store.created_memberships) == 1
    bound = store.created_memberships[0]
    assert bound.tenant_id == _TENANT_ID
    # … and the session that was issued is bound to that new membership.
    assert store.sessions[-1].active_membership_id == bound.id
    # The redirect routes to the host path, not the no-orgs page.
    assert response.headers["location"] == "/app"


def test_admin_approval_redirects_to_join_requested() -> None:
    user = _make_verified_user()
    store = _DomainJoinStore(policy="admin_approval", user=user)
    client = _client(store)

    response = client.post(
        "/auth/login/password",
        data={"email": user.email, "password": "password"},
    )

    assert response.status_code == 303
    # No membership created; a join request was recorded instead.
    assert store.created_memberships == []
    assert len(store.created_join_requests) == 1
    assert response.headers["location"] == "/auth/join-requested"


def test_unverified_user_does_not_evaluate_join() -> None:
    """A user whose email is not verified never reaches apply_domain_join."""
    user = UserRecord(
        email=f"bob@{_DOMAIN}",
        password_hash=hash_password("password"),
        email_verified=False,
    )
    store = _DomainJoinStore(policy="auto_join", user=user)
    client = _client(store)

    response = client.post(
        "/auth/login/password",
        data={"email": user.email, "password": "password"},
    )

    assert response.status_code == 303
    assert store.created_memberships == []
    assert store.created_join_requests == []
    # Legacy transition path: membership-less session proceeds to /app.
    assert response.headers["location"] == "/app"


@pytest.mark.parametrize("policy", ["auto_join", "admin_approval"])
def test_join_evaluated_only_when_no_membership(policy: str) -> None:
    """If activation already resolves a membership, the join branch is skipped."""
    user = _make_verified_user()
    store = _DomainJoinStore(policy=policy, user=user)
    store._memberships.append(
        MembershipRecord(
            id="pre-existing",
            tenant_id=_TENANT_ID,
            identity_id=str(user.id),
            status="active",
        )
    )
    client = _client(store)

    response = client.post(
        "/auth/login/password",
        data={"email": user.email, "password": "password"},
    )

    assert response.status_code == 303
    # No new membership and no join request — activation already bound the org.
    assert store.created_memberships == []
    assert store.created_join_requests == []
    assert store.sessions[-1].active_membership_id == "pre-existing"
    assert response.headers["location"] == "/app"
