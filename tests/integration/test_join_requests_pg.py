"""Real-PG CRUD proof for the join_requests table (#1424)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

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
