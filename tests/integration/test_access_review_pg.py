"""Real-PG proof of the access-review export (auth Plan 2b)."""

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
    scratch = f"dazzle_axrev_{uuid.uuid4().hex[:8]}"
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


def test_get_memberships_for_tenant_returns_current_roster(store_url: str) -> None:
    store = _store(store_url)
    ua = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    ub = store.create_user(email="b@b.test", password="pw123456", roles=["worker"])
    store.create_membership(tenant_id="org-1", identity_id=str(ua.id), roles=["admin"])
    store.create_membership(tenant_id="org-1", identity_id=str(ub.id), roles=["member"])
    store.create_membership(tenant_id="org-2", identity_id=str(ua.id), roles=["member"])

    roster = store.get_memberships_for_tenant("org-1")
    assert {m.identity_id for m in roster} == {str(ua.id), str(ub.id)}
    assert all(m.tenant_id == "org-1" for m in roster)


def test_build_access_review_current_and_as_of(store_url: str) -> None:
    from dazzle.rbac.access_evidence import AccessReview, build_access_review

    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])
    store.update_membership_roles(m.id, ["member", "approver"], actor_id="admin-1")

    review = build_access_review(store, "org-1", generated_at="2026-06-05T00:00:00+00:00")
    # Current roster reflects the latest roles; JML has the provision + role change.
    assert len(review.snapshot.members) == 1
    assert review.snapshot.members[0].roles == ["member", "approver"]
    assert [j.jml for j in review.jml] == ["joiner", "mover"]
    assert review.chain.ok is True
    # Reconciliation: the current table agrees with a replay of the event log.
    assert review.reconciliation is not None
    assert review.reconciliation.consistent is True
    # JSON round-trips (owner-attestable artifact).
    import json

    blob = json.dumps(review.to_dict())
    assert "org-1" in blob and "approver" in blob
    assert isinstance(review, AccessReview)


def test_cli_access_review_json_emits_pack(store_url: str) -> None:
    import json

    from typer.testing import CliRunner

    from dazzle.cli.rbac import rbac_app

    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["admin"])

    result = CliRunner().invoke(
        rbac_app,
        ["access-review", "--tenant", "org-1", "--format", "json", "--database-url", store_url],
    )
    assert result.exit_code == 0, result.output
    pack = json.loads(result.stdout)
    assert pack["tenant_id"] == "org-1"
    assert pack["chain"]["ok"] is True
    assert len(pack["snapshot"]["members"]) == 1
    assert pack["jml"][0]["jml"] == "joiner"


def test_cli_access_review_rejects_bad_as_of(store_url: str) -> None:
    from typer.testing import CliRunner

    from dazzle.cli.rbac import rbac_app

    _store(store_url)
    result = CliRunner().invoke(
        rbac_app,
        [
            "access-review",
            "--tenant",
            "org-1",
            "--as-of",
            "not-a-date",
            "--database-url",
            store_url,
        ],
    )
    assert result.exit_code == 1
    assert "Invalid date input" in result.output


def test_access_review_as_of_excludes_later_changes(store_url: str) -> None:
    from dazzle.rbac.access_evidence import build_org_snapshot

    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])
    # An as-of date in the far past (before any event) → empty roster.
    snap = build_org_snapshot(store, "org-1", as_of="2020-01-01T00:00:00+00:00")
    assert snap.source == "replay"
    assert snap.members == []
    # An as-of date in the future → includes the membership.
    snap_now = build_org_snapshot(store, "org-1", as_of="2099-01-01T00:00:00+00:00")
    assert {mm.membership_id for mm in snap_now.members} == {m.id}
