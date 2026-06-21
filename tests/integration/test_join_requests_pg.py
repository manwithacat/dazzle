"""Real-PG CRUD proof for the join_requests table (#1424) + lock-serialized
concurrent-approve hardening (#1430)."""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from dazzle.http.runtime.auth.join_requests import AlreadyDecidedError

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture
def store_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _PG_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _old = admin.rpartition("/")
    scratch = f"dazzle_jr_{uuid.uuid4().hex[:8]}"
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


def _store(url: str):
    from dazzle.http.runtime.auth.store import AuthStore

    s = AuthStore(database_url=url)
    s._init_db()
    return s


def test_join_request_crud(store_url: str) -> None:
    store = _store(store_url)

    # create
    jr = store.create_join_request(tenant_id="t1", identity_id="u1", email="alice@example.com")
    assert jr.status == "pending"
    assert jr.decided_at is None
    assert jr.decided_by is None

    # list pending
    pending = store.get_pending_join_requests("t1")
    assert len(pending) == 1
    assert pending[0].id == jr.id

    # idempotent re-create returns the same row
    jr2 = store.create_join_request(tenant_id="t1", identity_id="u1", email="alice@example.com")
    assert jr2.id == jr.id

    # decide approved
    decided = store.decide_join_request(jr.id, status="approved", decided_by="admin")
    assert decided.status == "approved"
    assert decided.decided_by == "admin"
    assert decided.decided_at is not None

    # no longer pending
    pending_after = store.get_pending_join_requests("t1")
    assert pending_after == []

    # get_join_request returns the decided row
    fetched = store.get_join_request(jr.id)
    assert fetched is not None
    assert fetched.status == "approved"

    # get_join_request returns None for unknown id
    assert store.get_join_request("does-not-exist") is None


# ---------------------------------------------------------------------------
# #1430 — approve_join_request_atomic: lock-serialized decision
# ---------------------------------------------------------------------------


def _membership_count(store: Any, tenant_id: str, identity_id: str) -> int:
    rows = store._execute(
        "SELECT count(*) AS n FROM memberships WHERE tenant_id = %s AND identity_id = %s",
        (tenant_id, identity_id),
    )
    return int(rows[0]["n"])


def _user_with_request(store: Any, *, email: str) -> tuple[str, str]:
    """Create a real user + a pending join request; return (identity_id, request_id)."""
    user = store.create_user(email=email, password="pw-12345678")
    jr = store.create_join_request(tenant_id="t1", identity_id=str(user.id), email=email)
    return str(user.id), jr.id


def test_approve_atomic_creates_membership_and_approves(store_url: str) -> None:
    store = _store(store_url)
    identity_id, request_id = _user_with_request(store, email="alice@example.com")

    decided = store.approve_join_request_atomic(request_id, decided_by="admin", roles=[])

    assert decided.status == "approved"
    assert decided.decided_by == "admin"
    assert decided.decided_at is not None
    assert _membership_count(store, "t1", identity_id) == 1


def test_approve_atomic_sequential_double_rejected_one_membership(store_url: str) -> None:
    store = _store(store_url)
    identity_id, request_id = _user_with_request(store, email="alice@example.com")

    store.approve_join_request_atomic(request_id, decided_by="a1", roles=[])
    with pytest.raises(AlreadyDecidedError):
        store.approve_join_request_atomic(request_id, decided_by="a2", roles=[])

    assert _membership_count(store, "t1", identity_id) == 1


def test_concurrent_double_approve_creates_exactly_one_membership(store_url: str) -> None:
    """Two approvers (independent connections) race on the same request.

    The ``SELECT … FOR UPDATE`` row lock serializes them: one commits the
    membership + approval, the other blocks then sees the row already non-pending
    and raises ``AlreadyDecidedError`` — exactly one membership, by construction.
    """
    s1 = _store(store_url)
    identity_id, request_id = _user_with_request(s1, email="bob@example.com")
    s2 = _store(store_url)

    barrier = threading.Barrier(2)
    results: dict[str, str] = {}

    def _approve(name: str, store: Any) -> None:
        barrier.wait()  # release both threads as simultaneously as possible
        try:
            store.approve_join_request_atomic(request_id, decided_by=name, roles=[])
            results[name] = "ok"
        except AlreadyDecidedError:
            results[name] = "already"
        except Exception as exc:  # surface anything unexpected in the assertion
            results[name] = f"error:{type(exc).__name__}"

    threads = [
        threading.Thread(target=_approve, args=("a1", s1)),
        threading.Thread(target=_approve, args=("a2", s2)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results.values()) == ["already", "ok"], (
        f"expected one ok + one already-decided, got {results}"
    )
    assert _membership_count(s1, "t1", identity_id) == 1
