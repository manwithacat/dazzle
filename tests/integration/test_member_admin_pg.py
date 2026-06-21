"""Real-PG route tests for the member-admin surface (auth Plan 3b)."""

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
    scratch = f"dazzle_memadm_{uuid.uuid4().hex[:8]}"
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


def _app(store, org_admin_roles):
    from fastapi import FastAPI

    from dazzle.http.runtime.auth.member_admin_routes import create_member_admin_routes

    app = FastAPI()
    app.state.auth_store = store
    app.state.org_admin_roles = list(org_admin_roles)
    app.state.sitespec = {}
    app.include_router(create_member_admin_routes())
    return app


def _admin_client(store, org, roles=("owner",)):
    """An authenticated TestClient for an admin of ``org`` + the admin membership."""
    from fastapi.testclient import TestClient

    admin = store.create_user(email="admin@acme.test", password="pw123456", roles=[])
    m = store.create_membership(tenant_id=org.id, identity_id=str(admin.id), roles=list(roles))
    sid = store.create_session(admin).id
    store.set_session_active_membership(sid, m.id, identity_id=str(admin.id))
    client = TestClient(_app(store, org_admin_roles=["owner"]), follow_redirects=False)
    client.cookies.set("dazzle_session", sid)
    return client, admin, m


def test_members_page_lists_roster(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, _m = _admin_client(store, org)
    bob = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    store.create_membership(tenant_id=org.id, identity_id=str(bob.id), roles=["member"])

    r = client.get("/auth/members")
    assert r.status_code == 200
    assert "Members of Acme" in r.text
    assert "bob@acme.test" in r.text


def test_members_page_denies_non_admin(store_url: str) -> None:
    from fastapi.testclient import TestClient

    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    member = store.create_user(email="m@acme.test", password="pw123456", roles=[])
    m = store.create_membership(tenant_id=org.id, identity_id=str(member.id), roles=["member"])
    sid = store.create_session(member).id
    store.set_session_active_membership(sid, m.id, identity_id=str(member.id))
    client = TestClient(_app(store, org_admin_roles=["owner"]), follow_redirects=False)
    client.cookies.set("dazzle_session", sid)
    assert client.get("/auth/members").status_code == 403


def test_change_roles(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, _m = _admin_client(store, org)
    bob = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    bm = store.create_membership(tenant_id=org.id, identity_id=str(bob.id), roles=["member"])

    r = client.post(
        f"/auth/members/roles?membership_id={bm.id}", data={"roles": "member, approver"}
    )
    assert r.status_code in (204, 303)
    assert store.get_membership(bm.id).roles == ["member", "approver"]


def test_suspend_and_reactivate(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, _m = _admin_client(store, org)
    bob = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    bm = store.create_membership(tenant_id=org.id, identity_id=str(bob.id), roles=["member"])

    assert client.post(f"/auth/members/suspend?membership_id={bm.id}").status_code in (204, 303)
    assert store.get_membership(bm.id).status == "suspended"
    assert client.post(f"/auth/members/reactivate?membership_id={bm.id}").status_code in (204, 303)
    assert store.get_membership(bm.id).status == "active"


def test_remove(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, _m = _admin_client(store, org)
    bob = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    bm = store.create_membership(tenant_id=org.id, identity_id=str(bob.id), roles=["member"])

    assert client.post(f"/auth/members/remove?membership_id={bm.id}").status_code in (204, 303)
    assert store.get_membership(bm.id) is None


def test_cross_org_target_is_rejected(store_url: str) -> None:
    # An admin of org A cannot manage a membership in org B (cross-org guard).
    store = _store(store_url)
    org_a = store.create_organization(slug="acme", name="Acme")
    org_b = store.create_organization(slug="other", name="Other")
    client, _admin, _m = _admin_client(store, org_a)
    victim = store.create_user(email="v@other.test", password="pw123456", roles=[])
    vm = store.create_membership(tenant_id=org_b.id, identity_id=str(victim.id), roles=["member"])

    r = client.post(f"/auth/members/remove?membership_id={vm.id}")
    assert r.status_code == 404
    assert store.get_membership(vm.id) is not None  # untouched


def test_cannot_remove_or_demote_last_admin(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, am = _admin_client(store, org)  # the only admin

    assert client.post(f"/auth/members/remove?membership_id={am.id}").status_code == 409
    assert store.get_membership(am.id) is not None
    assert client.post(f"/auth/members/suspend?membership_id={am.id}").status_code == 409
    r = client.post(f"/auth/members/roles?membership_id={am.id}", data={"roles": "member"})
    assert r.status_code == 409
    assert store.get_membership(am.id).roles == ["owner"]  # unchanged


# -- Join-requests approval queue (#1424 Task 4.3) --------------------------


def _pending_request(store, org, email="newcomer@acme.test"):
    """A user with a pending join request for ``org``; returns (user, request)."""
    user = store.create_user(email=email, password="pw123456", roles=[])
    jr = store.create_join_request(tenant_id=org.id, identity_id=str(user.id), email=email)
    return user, jr


def test_join_requests_queue_lists_pending(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, _m = _admin_client(store, org)
    _user, _jr = _pending_request(store, org)

    r = client.get("/auth/join-requests")
    assert r.status_code == 200
    assert "Join requests for Acme" in r.text
    assert "newcomer@acme.test" in r.text


def test_join_requests_queue_denies_non_admin(store_url: str) -> None:
    from fastapi.testclient import TestClient

    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    member = store.create_user(email="m@acme.test", password="pw123456", roles=[])
    m = store.create_membership(tenant_id=org.id, identity_id=str(member.id), roles=["member"])
    sid = store.create_session(member).id
    store.set_session_active_membership(sid, m.id, identity_id=str(member.id))
    client = TestClient(_app(store, org_admin_roles=["owner"]), follow_redirects=False)
    client.cookies.set("dazzle_session", sid)
    assert client.get("/auth/join-requests").status_code == 403


def test_approve_creates_membership_and_marks_approved(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, _m = _admin_client(store, org)
    user, jr = _pending_request(store, org)

    r = client.post(f"/auth/join-requests/approve?request_id={jr.id}")
    assert r.status_code in (204, 303)
    assert store.get_join_request(jr.id).status == "approved"
    memberships = store.get_memberships_for_identity(str(user.id))
    assert [m.tenant_id for m in memberships] == [org.id]
    assert memberships[0].roles == []  # default-deny


def test_deny_marks_denied_with_no_membership(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, _m = _admin_client(store, org)
    user, jr = _pending_request(store, org)

    r = client.post(f"/auth/join-requests/deny?request_id={jr.id}")
    assert r.status_code in (204, 303)
    assert store.get_join_request(jr.id).status == "denied"
    assert store.get_memberships_for_identity(str(user.id)) == []


def test_double_approve_creates_exactly_one_membership(store_url: str) -> None:
    """The double-decide guard at the REAL store: a second approve is rejected
    (409) and the roster still holds exactly one membership."""
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, _m = _admin_client(store, org)
    user, jr = _pending_request(store, org)

    first = client.post(f"/auth/join-requests/approve?request_id={jr.id}")
    assert first.status_code in (204, 303)
    second = client.post(f"/auth/join-requests/approve?request_id={jr.id}")
    assert second.status_code == 409  # already decided

    memberships = store.get_memberships_for_identity(str(user.id))
    assert len(memberships) == 1  # exactly one — no duplicate


def test_approve_cross_org_request_is_rejected(store_url: str) -> None:
    store = _store(store_url)
    org_a = store.create_organization(slug="acme", name="Acme")
    org_b = store.create_organization(slug="other", name="Other")
    client, _admin, _m = _admin_client(store, org_a)
    other = store.create_user(email="x@other.test", password="pw123456", roles=[])
    jr = store.create_join_request(
        tenant_id=org_b.id, identity_id=str(other.id), email="x@other.test"
    )

    r = client.post(f"/auth/join-requests/approve?request_id={jr.id}")
    assert r.status_code == 404
    assert store.get_join_request(jr.id).status == "pending"  # untouched
    assert store.get_memberships_for_identity(str(other.id)) == []
