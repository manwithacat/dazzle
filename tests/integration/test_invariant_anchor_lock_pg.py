"""#1318 — the invariant anchor ``FOR UPDATE`` lock serializes the same anchor row (ADR-0031).

Proves that the anchor-row lock ``enforce_flow_invariants`` takes —
``SELECT "id" FROM "<anchor_entity>" WHERE "id"=%s FOR UPDATE`` — is a *real*
exclusive row lock that blocks a concurrent transaction acquiring the same lock
on the same anchor row until the holder ends. This is the security property:
without it, two flows on the same anchor could both read the aggregate, both
find it under the cap, and both commit — overshooting the invariant (the
read-then-write race that an aggregate cap is meant to close).

A full end-to-end test through the atomic HTTP route would deadlock — the
runtime uses synchronous psycopg, so a blocked ``FOR UPDATE`` inside a flow
request would freeze the single test event loop. So this drives two real
connections + a worker thread directly, which is deterministic. Mirrors
``tests/integration/test_scope_parent_lock_pg.py``.

Marked ``postgres`` (+ ``e2e``): skipped locally without ``TEST_DATABASE_URL`` /
``DATABASE_URL``; CI's ``postgres-tests`` job runs it against a real ``postgres:16``.
"""

from __future__ import annotations

import os
import threading
import uuid

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_anchor_for_update_blocks_concurrent_anchor_lock() -> None:
    import psycopg

    table = f"_inv_anchor_test_{uuid.uuid4().hex[:8]}"
    qtable = f'"{table}"'  # the already-quoted shape `enforce_flow_invariants` emits
    row_id = str(uuid.uuid4())

    # `qtable` is a server-generated `_inv_anchor_test_<hex>` identifier — not user
    # input. The two suppressions below are the same pair the verifier harness
    # uses for its scratch-DB DDL (formatted-sql + sqlalchemy-raw-query).
    create_sql = f"CREATE TABLE {qtable} (id uuid primary key)"
    insert_sql = f"INSERT INTO {qtable} (id) VALUES (%s)"
    # The same lock shape `enforce_flow_invariants` takes before the aggregate.
    lock_sql = f'SELECT "id" FROM {qtable} WHERE "id"=%s FOR UPDATE'

    # Setup: a minimal Transaction-like anchor table with a uuid pk + one row.
    with psycopg.connect(_PG_URL, autocommit=True) as setup:
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        setup.execute(create_sql)
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        setup.execute(insert_sql, [row_id])

    try:
        # Connection A holds an open transaction and FOR UPDATE-locks the anchor
        # row, exactly as the invariant enforcer does before running the aggregate.
        locker = psycopg.connect(_PG_URL)  # autocommit=False → open txn
        try:
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            locker.execute(lock_sql, [row_id])

            # A second flow on the SAME anchor takes the SAME FOR UPDATE lock. With
            # A's lock held it must BLOCK until A ends; without the lock it would
            # acquire immediately.
            locked = threading.Event()

            def _try_lock() -> None:
                with psycopg.connect(_PG_URL) as writer:  # autocommit=False → open txn
                    # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                    writer.execute(lock_sql, [row_id])
                    writer.commit()
                locked.set()

            worker = threading.Thread(target=_try_lock, daemon=True)
            worker.start()

            # The second FOR UPDATE must not acquire while A holds the lock.
            assert not locked.wait(timeout=2.0), (
                "concurrent FOR UPDATE acquired the anchor row despite A holding it — "
                "the aggregate-invariant serialization window is open"
            )

            # Releasing A lets the blocked FOR UPDATE proceed.
            locker.rollback()
            assert locked.wait(timeout=5.0), (
                "second FOR UPDATE did not proceed after the anchor lock was released"
            )
            worker.join(timeout=5.0)
        finally:
            locker.close()
    finally:
        drop_sql = f"DROP TABLE IF EXISTS {qtable}"
        with psycopg.connect(_PG_URL, autocommit=True) as cleanup:
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            cleanup.execute(drop_sql)
