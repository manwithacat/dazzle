"""Join-request approval queue — approve/deny helpers + route gate (#1424 Task 4.3).

Security-sensitive: approving a request CREATES a membership. These tests assert:

  * ``approve_join_request`` creates exactly one membership and marks the request
    ``approved``;
  * ``deny_join_request`` marks the request ``denied`` and creates NO membership;
  * a non-``manage_members`` caller is fail-closed on every endpoint (403);
  * **double-approve creates exactly ONE membership** (the double-decide guard
    carried over from the Task 1.5 review — a second approve must not overwrite an
    already-decided request nor create a second membership);
  * approve re-runs ``assert_domain_admissible`` at decision time, so a tenant that
    has since restricted membership to its verified domains blocks the approval.

A ``FakeStore`` stands in for ``AuthStore``: its ``decide_join_request`` mirrors the
real ``WHERE id = %s AND status = 'pending'`` guard (rowcount 0 → already-decided),
so the double-decide invariant is exercised at the same altitude the route relies on.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest

from dazzle.http.runtime.auth.domain_join import DomainNotAdmissibleError
from dazzle.http.runtime.auth.join_requests import (
    AlreadyDecidedError,
    approve_join_request,
    deny_join_request,
)
from dazzle.http.runtime.auth.models import JoinRequestRecord, MembershipRecord


@dataclass
class _Conn:
    verified_domains: list[str]


@dataclass
class FakeStore:
    """In-memory auth store double for the approval helpers.

    ``decide_join_request`` enforces the same pending-only transition as the real
    store (``AND status = 'pending'``), so a double-approve cannot create a second
    membership through these helpers.
    """

    join_requests: dict[str, JoinRequestRecord] = field(default_factory=dict)
    memberships: list[MembershipRecord] = field(default_factory=list)
    org_settings: dict[str, dict[str, Any]] = field(default_factory=dict)
    connections: dict[str, list[_Conn]] = field(default_factory=dict)
    _next_membership: int = 0

    # -- join requests ------------------------------------------------------
    def get_join_request(self, request_id: str) -> JoinRequestRecord | None:
        return self.join_requests.get(request_id)

    def decide_join_request(
        self, request_id: str, *, status: str, decided_by: str
    ) -> JoinRequestRecord:
        jr = self.join_requests.get(request_id)
        # Mirror the real UPDATE ... WHERE id=%s AND status='pending': rowcount 0
        # when the row is missing or already decided.
        if jr is None or jr.status != "pending":
            raise AlreadyDecidedError(request_id)
        from datetime import UTC, datetime

        updated = jr.model_copy(
            update={
                "status": status,
                "decided_at": datetime.now(UTC),
                "decided_by": decided_by,
            }
        )
        self.join_requests[request_id] = updated
        return updated

    # -- memberships --------------------------------------------------------
    def create_membership(
        self, *, tenant_id: str, identity_id: str, roles: list[str], reason: str = ""
    ) -> MembershipRecord:
        self._next_membership += 1
        m = MembershipRecord(
            id=f"mem-{self._next_membership}",
            tenant_id=tenant_id,
            identity_id=identity_id,
            roles=list(roles),
        )
        self.memberships.append(m)
        return m

    def approve_join_request_atomic(
        self,
        request_id: str,
        *,
        decided_by: str,
        roles: list[str] | None = None,
        reason: str = "",
    ) -> JoinRequestRecord:
        """Mirror the real lock-serialized atomic approve (#1430).

        In-memory there is no row lock, but the re-check-pending → create → decide
        sequence reproduces the same invariant the real ``SELECT … FOR UPDATE`` path
        enforces: a second approve of an already-decided request raises
        ``AlreadyDecidedError`` *before* creating a duplicate membership.
        """
        jr = self.join_requests.get(request_id)
        if jr is None or jr.status != "pending":
            raise AlreadyDecidedError(request_id)
        self.create_membership(
            tenant_id=jr.tenant_id, identity_id=jr.identity_id, roles=roles or [], reason=reason
        )
        return self.decide_join_request(request_id, status="approved", decided_by=decided_by)

    # -- admission gate deps ------------------------------------------------
    def get_org_settings(self, tenant_id: str) -> dict[str, Any]:
        return self.org_settings.get(tenant_id, {})

    def get_connections_for_tenant(self, tenant_id: str) -> list[_Conn]:
        return self.connections.get(tenant_id, [])


def _pending(store: FakeStore, *, request_id: str = "r1", email: str = "alice@acme.test") -> None:
    store.join_requests[request_id] = JoinRequestRecord(
        id=request_id, tenant_id="t-acme", identity_id="ident-alice", email=email
    )


# ---------------------------------------------------------------------------
# Helper-level: approve / deny
# ---------------------------------------------------------------------------


def test_approve_creates_membership_and_marks_approved() -> None:
    store = FakeStore()
    _pending(store)

    jr = approve_join_request(store, "r1", decided_by="admin-1")

    assert jr.status == "approved"
    assert jr.decided_by == "admin-1"
    assert len(store.memberships) == 1
    m = store.memberships[0]
    assert m.tenant_id == "t-acme"
    assert m.identity_id == "ident-alice"
    assert m.roles == []  # default-deny roles


def test_deny_marks_denied_with_no_membership() -> None:
    store = FakeStore()
    _pending(store)

    jr = deny_join_request(store, "r1", decided_by="admin-1")

    assert jr.status == "denied"
    assert jr.decided_by == "admin-1"
    assert store.memberships == []


def test_double_approve_creates_exactly_one_membership() -> None:
    """The double-decide guard: a second approve of an already-approved request
    must NOT create a second membership."""
    store = FakeStore()
    _pending(store)

    approve_join_request(store, "r1", decided_by="admin-1")
    with pytest.raises(AlreadyDecidedError):
        approve_join_request(store, "r1", decided_by="admin-2")

    assert len(store.memberships) == 1  # exactly one — no duplicate


def test_approve_after_deny_is_rejected_and_creates_no_membership() -> None:
    store = FakeStore()
    _pending(store)

    deny_join_request(store, "r1", decided_by="admin-1")
    with pytest.raises(AlreadyDecidedError):
        approve_join_request(store, "r1", decided_by="admin-2")

    assert store.memberships == []


def test_approve_unknown_request_is_rejected() -> None:
    store = FakeStore()
    with pytest.raises(AlreadyDecidedError):
        approve_join_request(store, "nope", decided_by="admin-1")
    assert store.memberships == []


def test_approve_rechecks_domain_admissibility_at_decision_time() -> None:
    """The tenant restricted membership to its verified domains AFTER the request
    was filed — approval must re-run the admission gate and refuse."""
    store = FakeStore()
    _pending(store, email="alice@evil.test")
    store.org_settings["t-acme"] = {"restrict_membership_to_verified_domains": True}
    store.connections["t-acme"] = [_Conn(verified_domains=["acme.test"])]

    with pytest.raises(DomainNotAdmissibleError):
        approve_join_request(store, "r1", decided_by="admin-1")

    assert store.memberships == []  # no membership created
    assert store.join_requests["r1"].status == "pending"  # not marked approved


def test_approve_passes_admissibility_for_a_verified_domain() -> None:
    store = FakeStore()
    _pending(store, email="alice@acme.test")
    store.org_settings["t-acme"] = {"restrict_membership_to_verified_domains": True}
    store.connections["t-acme"] = [_Conn(verified_domains=["acme.test"])]

    jr = approve_join_request(store, "r1", decided_by="admin-1")
    assert jr.status == "approved"
    assert len(store.memberships) == 1


# ---------------------------------------------------------------------------
# Route-level: the gate is fail-closed for a non-manage_members caller.
# ---------------------------------------------------------------------------


def _app(store: Any):
    from fastapi import FastAPI

    from dazzle.http.runtime.auth.member_admin_routes import create_member_admin_routes

    app = FastAPI()
    app.state.auth_store = store
    app.state.org_admin_roles = ["owner"]
    app.state.sitespec = {}
    app.include_router(create_member_admin_routes())
    return app


@dataclass
class _Ctx:
    is_authenticated: bool
    user: Any
    active_membership: Any


class _GateStore:
    """Minimal store for the route gate: an authenticated NON-admin session."""

    def __init__(self) -> None:
        self.created: list[Any] = []

    def validate_session(self, session_id: str) -> Any:
        # An authenticated session whose active membership holds only "member"
        # (not the app's org_admin_roles=["owner"]) — the gate must deny.
        member = MembershipRecord(id="m", tenant_id="t-acme", identity_id="i", roles=["member"])

        class _U:
            id = "i"

        return _Ctx(is_authenticated=True, user=_U(), active_membership=member)

    # if a (buggy) handler reached the store these would record the breach
    def get_pending_join_requests(self, tenant_id: str) -> list[Any]:
        self.created.append(("list", tenant_id))
        return []

    def get_join_request(self, request_id: str) -> Any:
        self.created.append(("get", request_id))
        return None

    def create_membership(self, **kw: Any) -> Any:
        self.created.append(("membership", kw))
        raise AssertionError("create_membership must not be reached by a non-admin")


def _client(store: Any):
    from fastapi.testclient import TestClient

    c = TestClient(_app(store), follow_redirects=False)
    c.cookies.set("dazzle_session", "sid")
    return c


def test_join_requests_queue_denies_non_admin() -> None:
    store = _GateStore()
    r = _client(store).get("/auth/join-requests")
    assert r.status_code == 403


def test_approve_denies_non_admin_and_creates_no_membership() -> None:
    store = _GateStore()
    r = _client(store).post("/auth/join-requests/approve?request_id=r1")
    assert r.status_code == 403
    assert store.created == []  # fail-closed before any store mutation


def test_deny_denies_non_admin() -> None:
    store = _GateStore()
    r = _client(store).post("/auth/join-requests/deny?request_id=r1")
    assert r.status_code == 403
    assert store.created == []


# ---------------------------------------------------------------------------
# CSRF: the new state-changing POSTs are origin-primary protected.
# ---------------------------------------------------------------------------


def test_approval_posts_are_csrf_protected() -> None:
    from dazzle.http.runtime.csrf import CSRFConfig

    protected = CSRFConfig().protected_paths
    assert "/auth/join-requests/approve" in protected
    assert "/auth/join-requests/deny" in protected
