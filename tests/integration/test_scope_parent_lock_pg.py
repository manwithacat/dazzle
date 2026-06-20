"""#1316 — scope-parent ``FOR SHARE`` lock blocks a concurrent ``UPDATE`` (ADR-0029 inv 4).

Proves ``_acquire_scope_parent_share_locks`` (the atomic-flow TOCTOU hardening)
acquires a *real* ``SELECT … FOR SHARE`` row lock that blocks a concurrent
``UPDATE`` of the same parent until the locking transaction ends. This is the
security property: without the share lock, a concurrent write could move the
scope parent out of the principal's scope between the scope check and the flow's
commit (the read-then-write race).

A full end-to-end test through the atomic HTTP route would deadlock — the runtime
uses synchronous psycopg, so a blocked ``FOR SHARE`` inside a flow request would
freeze the single test event loop. So this drives the lock helper directly with
two real connections + a worker thread, which is deterministic.

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
def test_for_share_blocks_concurrent_update() -> None:
    import psycopg

    from dazzle.http.runtime.atomic_flow_executor import _acquire_scope_parent_share_locks

    table = f"_lock_test_{uuid.uuid4().hex[:8]}"
    qtable = f'"{table}"'  # the already-quoted shape `_path_check_subquery` emits
    row_id = str(uuid.uuid4())

    # `qtable` is a server-generated `_lock_test_<hex>` identifier — not user
    # input. The two suppressions below are the same pair the verifier harness
    # uses for its scratch-DB DDL (formatted-sql + sqlalchemy-raw-query).
    create_sql = f"CREATE TABLE {qtable} (id uuid primary key, dept text)"
    insert_sql = f"INSERT INTO {qtable} (id, dept) VALUES (%s, %s)"
    # Setup: a minimal scope-parent table with a uuid pk + a scope-ish column.
    with psycopg.connect(_PG_URL, autocommit=True) as setup:
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        setup.execute(create_sql)
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        setup.execute(insert_sql, [row_id, "math"])

    try:
        # The "flow" connection holds an open transaction and share-locks the row,
        # exactly as the executor does before running the scope probe.
        locker = psycopg.connect(_PG_URL)  # autocommit=False → open txn
        try:
            _acquire_scope_parent_share_locks(locker, "X", {qtable: {row_id}})

            # A concurrent writer tries to move the parent's scope column. With the
            # FOR SHARE lock held it must BLOCK until `locker` ends; without the
            # lock it would commit immediately (READ COMMITTED).
            updated = threading.Event()

            update_sql = f"UPDATE {qtable} SET dept = %s WHERE id = %s"

            def _try_update() -> None:
                with psycopg.connect(_PG_URL, autocommit=True) as writer:
                    # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                    writer.execute(update_sql, ["science", row_id])
                updated.set()

            worker = threading.Thread(target=_try_update, daemon=True)
            worker.start()

            # The UPDATE must not complete while the share lock is held.
            assert not updated.wait(timeout=2.0), (
                "concurrent UPDATE completed despite the scope-parent FOR SHARE lock — "
                "the TOCTOU window is open"
            )

            # Releasing the share lock lets the blocked UPDATE proceed.
            locker.rollback()
            assert updated.wait(timeout=5.0), "UPDATE did not proceed after the lock was released"
            worker.join(timeout=5.0)
        finally:
            locker.close()
    finally:
        drop_sql = f"DROP TABLE IF EXISTS {qtable}"
        with psycopg.connect(_PG_URL, autocommit=True) as cleanup:
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            cleanup.execute(drop_sql)
