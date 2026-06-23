"""Real-PG proof of org invitations (auth Plan 3a)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def store_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _admin_url()
    base, _, _old = admin.rpartition("/")
    scratch = f"dazzle_invite_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
    try:
        yield url
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (scratch,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def _store(store_url: str):
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=store_url)
    store._init_db()
    return store


def test_invite_then_accept_creates_active_membership(store_url: str) -> None:
    from dazzle.http.runtime.auth.invitations import (
        InvitationError,
        accept_invitation,
        create_invitation,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    invitee = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    store._execute_modify(
        "UPDATE users SET email_verified = true WHERE id = %s", (str(invitee.id),)
    )

    token = create_invitation(
        store,
        org_id="org-1",
        email="bob@acme.test",
        roles=["member"],
        invited_by=str(inviter.id),
    )
    membership = accept_invitation(
        store,
        token,
        identity_id=str(invitee.id),
        accepting_email="bob@acme.test",
        email_verified=True,
    )
    assert membership.tenant_id == "org-1"
    assert membership.roles == ["member"]
    assert membership.status == "active"
    assert membership.invited_by == str(inviter.id)
    # The accept created a PROVISIONED lifecycle event (Plan 2a), inviter-attributed.
    events = store.get_membership_events(membership_id=membership.id)
    assert [e.event_type for e in events] == ["provisioned"]
    assert events[0].actor_id == str(inviter.id)
    # Single-use: a second accept raises.
    with pytest.raises(InvitationError):
        accept_invitation(
            store,
            token,
            identity_id=str(invitee.id),
            accepting_email="bob@acme.test",
            email_verified=True,
        )


def test_accept_rejects_email_mismatch(store_url: str) -> None:
    from dazzle.http.runtime.auth.invitations import (
        InvitationError,
        accept_invitation,
        create_invitation,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    attacker = store.create_user(email="eve@evil.test", password="pw123456", roles=[])
    token = create_invitation(
        store, org_id="org-1", email="bob@acme.test", roles=["member"], invited_by=str(inviter.id)
    )
    with pytest.raises(InvitationError) as ei:
        accept_invitation(
            store,
            token,
            identity_id=str(attacker.id),
            accepting_email="eve@evil.test",
            email_verified=True,
        )
    assert ei.value.reason == "email_mismatch"


def test_accept_rejects_unverified_email(store_url: str) -> None:
    from dazzle.http.runtime.auth.invitations import (
        InvitationError,
        accept_invitation,
        create_invitation,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    invitee = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    token = create_invitation(
        store, org_id="org-1", email="bob@acme.test", roles=["member"], invited_by=str(inviter.id)
    )
    with pytest.raises(InvitationError) as ei:
        accept_invitation(
            store,
            token,
            identity_id=str(invitee.id),
            accepting_email="bob@acme.test",
            email_verified=False,
        )
    assert ei.value.reason == "unverified"


def test_accept_rejects_expired(store_url: str) -> None:
    from dazzle.http.runtime.auth.invitations import (
        InvitationError,
        accept_invitation,
        create_invitation,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    invitee = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    token = create_invitation(
        store,
        org_id="org-1",
        email="bob@acme.test",
        roles=["member"],
        invited_by=str(inviter.id),
        ttl_hours=0,
    )
    with pytest.raises(InvitationError) as ei:
        accept_invitation(
            store,
            token,
            identity_id=str(invitee.id),
            accepting_email="bob@acme.test",
            email_verified=True,
        )
    assert ei.value.reason == "expired"


def test_accept_rejects_already_member(store_url: str) -> None:
    from dazzle.http.runtime.auth.invitations import (
        InvitationError,
        accept_invitation,
        create_invitation,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    invitee = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    store.create_membership(tenant_id="org-1", identity_id=str(invitee.id), roles=["member"])
    token = create_invitation(
        store, org_id="org-1", email="bob@acme.test", roles=["admin"], invited_by=str(inviter.id)
    )
    with pytest.raises(InvitationError) as ei:
        accept_invitation(
            store,
            token,
            identity_id=str(invitee.id),
            accepting_email="bob@acme.test",
            email_verified=True,
        )
    assert ei.value.reason == "already_member"


def test_accept_unique_violation_maps_to_already_member(store_url: str) -> None:
    # A membership created between accept's guard-read and its insert (i.e. a
    # concurrent winner) must surface as a clean already_member, not a 500/raw
    # UniqueViolation. Simulate by monkeypatching get_memberships_for_identity to
    # report "no membership" while the row in fact already exists.
    from dazzle.http.runtime.auth.invitations import (
        InvitationError,
        accept_invitation,
        create_invitation,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    invitee = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    # The race winner: a membership already exists, but the guard read won't see it.
    store.create_membership(tenant_id="org-1", identity_id=str(invitee.id), roles=["member"])
    token = create_invitation(
        store, org_id="org-1", email="bob@acme.test", roles=["admin"], invited_by=str(inviter.id)
    )
    store.get_memberships_for_identity = lambda _id: []  # type: ignore[method-assign]
    with pytest.raises(InvitationError) as ei:
        accept_invitation(
            store,
            token,
            identity_id=str(invitee.id),
            accepting_email="bob@acme.test",
            email_verified=True,
        )
    assert ei.value.reason == "already_member"  # UniqueViolation mapped, not a 500


def _invite_app(store, org_admin_roles):
    from fastapi import FastAPI

    from dazzle.http.runtime.auth.invitation_routes import create_invitation_routes

    app = FastAPI()
    app.state.auth_store = store
    app.state.org_admin_roles = list(org_admin_roles)
    app.state.sitespec = {}
    app.include_router(create_invitation_routes())
    return app


def test_invite_route_authz_gate(store_url: str) -> None:
    from fastapi.testclient import TestClient

    from dazzle.http.runtime.auth.invitations import list_pending_invitations

    store = _store(store_url)
    inviter = store.create_user(email="boss@acme.test", password="pw123456", roles=[])
    org = store.create_organization(slug="acme", name="Acme")
    membership = store.create_membership(
        tenant_id=org.id, identity_id=str(inviter.id), roles=["member"]
    )
    sid = store.create_session(inviter).id
    store.set_session_active_membership(sid, membership.id, identity_id=str(inviter.id))

    client = TestClient(_invite_app(store, org_admin_roles=["owner"]), follow_redirects=False)
    client.cookies.set("dazzle_session", sid)

    # A plain member (role not in org_admin_roles) is denied (fail-closed authz).
    r = client.post("/auth/invite", data={"email": "new@acme.test", "roles": "member"})
    assert r.status_code == 403
    assert list_pending_invitations(store, org.id) == []  # nothing created

    # Promote to an admin role → invite succeeds and creates a pending invitation.
    store.update_membership_roles(membership.id, ["owner"], actor_id=str(inviter.id))
    r2 = client.post("/auth/invite", data={"email": "new@acme.test", "roles": "member"})
    assert r2.status_code == 200
    pending = list_pending_invitations(store, org.id)
    assert [p.email for p in pending] == ["new@acme.test"]
    assert pending[0].invited_by == str(inviter.id)


def test_list_pending_invitations_excludes_accepted_and_expired(store_url: str) -> None:
    from dazzle.http.runtime.auth.invitations import (
        accept_invitation,
        create_invitation,
        list_pending_invitations,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    invitee = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    open_tok = create_invitation(
        store, org_id="org-1", email="carol@acme.test", roles=["member"], invited_by=str(inviter.id)
    )
    create_invitation(
        store,
        org_id="org-1",
        email="dan@acme.test",
        roles=["member"],
        invited_by=str(inviter.id),
        ttl_hours=0,
    )
    accepted = create_invitation(
        store, org_id="org-1", email="bob@acme.test", roles=["member"], invited_by=str(inviter.id)
    )
    accept_invitation(
        store,
        accepted,
        identity_id=str(invitee.id),
        accepting_email="bob@acme.test",
        email_verified=True,
    )
    pending = list_pending_invitations(store, "org-1")
    assert {p.token for p in pending} == {open_tok}
