"""Real-Postgres proof of the `claim_due_work` lease primitive (coordination §4).

Exercises:
 * No double-claim across 4 concurrent workers (300-row table, 4 threads).
 * Expired-lease reclaim — a row with a timed-out lease is claimed again.
 * fail_work retry→dead path — attempts counter drives the transition.

Marked ``postgres``: skipped locally without ``TEST_DATABASE_URL`` / ``DATABASE_URL``;
CI's ``postgres-tests`` job runs it against a real ``postgres:16``.
"""

from __future__ import annotations

import concurrent.futures
import os
import time
import uuid

import pytest

pytestmark = pytest.mark.postgres

_PG = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.mark.skipif(not _PG, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_no_double_claim_and_reclaim() -> None:
    import psycopg

    from dazzle.core.coordination.claim import (
        claim_due_work,
        complete_work,
        queue_columns_ddl,
    )

    tbl = f"claim_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(_PG, autocommit=True) as c:
        c.execute(f"CREATE TABLE {tbl} (id uuid PRIMARY KEY, {queue_columns_ddl(tbl)})")
    try:
        with psycopg.connect(_PG, autocommit=True) as c, c.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {tbl} (id, deliver_at) VALUES (%s, now())",
                [(str(uuid.uuid4()),) for _ in range(300)],
            )

        def drain(wid: int) -> list[str]:
            got: list[str] = []
            conn = psycopg.connect(_PG)
            try:
                while True:
                    ids = claim_due_work(
                        conn, table=tbl, worker=f"w{wid}", lease_seconds=30, batch=10
                    )
                    if not ids:
                        break
                    for i in ids:
                        complete_work(conn, table=tbl, row_id=i)
                    got += ids
            finally:
                conn.close()
            return got

        claimed: list[str] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            for f in [ex.submit(drain, i) for i in range(4)]:
                claimed += f.result()
        assert len(claimed) == 300 and len(set(claimed)) == 300, (
            f"Double-claim detected: {len(claimed)} claims, {len(set(claimed))} unique"
        )
    finally:
        with psycopg.connect(_PG, autocommit=True) as c:
            c.execute(f"DROP TABLE IF EXISTS {tbl}")


@pytest.mark.skipif(not _PG, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_expired_lease_is_reclaimed() -> None:
    """A row whose lease expires is reclaimable (crash recovery)."""
    import psycopg

    from dazzle.core.coordination.claim import (
        claim_due_work,
        queue_columns_ddl,
    )

    tbl = f"claim_expire_{uuid.uuid4().hex[:8]}"
    row_id = str(uuid.uuid4())
    with psycopg.connect(_PG, autocommit=True) as c:
        c.execute(f"CREATE TABLE {tbl} (id uuid PRIMARY KEY, {queue_columns_ddl(tbl)})")
        c.execute(f"INSERT INTO {tbl} (id, deliver_at) VALUES (%s, now())", (row_id,))
    try:
        conn = psycopg.connect(_PG)
        try:
            # Claim with a 1-second lease — but do NOT complete it.
            ids = claim_due_work(conn, table=tbl, worker="w0", lease_seconds=1, batch=1)
            assert ids == [row_id], f"Expected to claim {row_id}, got {ids}"

            # Wait for the lease to expire.
            time.sleep(1.2)

            # A second worker should now be able to reclaim the expired row.
            ids2 = claim_due_work(conn, table=tbl, worker="w1", lease_seconds=30, batch=1)
            assert ids2 == [row_id], f"Expected reclaim of expired row {row_id}, got {ids2}"
        finally:
            conn.close()
    finally:
        with psycopg.connect(_PG, autocommit=True) as c:
            c.execute(f"DROP TABLE IF EXISTS {tbl}")


@pytest.mark.skipif(not _PG, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_fail_work_retry_then_dead() -> None:
    """fail_work: row retries until max_attempts, then transitions to 'dead'."""
    import psycopg

    from dazzle.core.coordination.claim import (
        claim_due_work,
        fail_work,
        queue_columns_ddl,
    )

    tbl = f"claim_fail_{uuid.uuid4().hex[:8]}"
    row_id = str(uuid.uuid4())
    with psycopg.connect(_PG, autocommit=True) as c:
        c.execute(f"CREATE TABLE {tbl} (id uuid PRIMARY KEY, {queue_columns_ddl(tbl)})")
        c.execute(f"INSERT INTO {tbl} (id, deliver_at) VALUES (%s, now())", (row_id,))
    try:
        conn = psycopg.connect(_PG)
        try:
            max_attempts = 3
            # Cycle: claim → fail → claim → fail → ... until dead.
            for attempt in range(1, max_attempts + 1):
                ids = claim_due_work(conn, table=tbl, worker="w0", lease_seconds=30, batch=1)
                assert ids == [row_id], f"Attempt {attempt}: expected {row_id}, got {ids}"
                outcome = fail_work(
                    conn,
                    table=tbl,
                    row_id=row_id,
                    error=f"err{attempt}",
                    max_attempts=max_attempts,
                )
                if attempt < max_attempts:
                    assert outcome == "retry", f"Attempt {attempt}: expected retry, got {outcome}"
                    # Row should be back to 'pending' so the next claim loop finds it.
                    with conn.cursor() as cur:
                        cur.execute(f"SELECT status FROM {tbl} WHERE id=%s", (row_id,))
                        row = cur.fetchone()
                    assert row and row[0] == "pending", (
                        f"Attempt {attempt}: expected pending after retry, got {row}"
                    )
                else:
                    assert outcome == "dead", f"Final attempt: expected dead, got {outcome}"
                    with conn.cursor() as cur:
                        cur.execute(f"SELECT status FROM {tbl} WHERE id=%s", (row_id,))
                        row = cur.fetchone()
                    assert row and row[0] == "dead", (
                        f"Final attempt: expected dead status, got {row}"
                    )
        finally:
            conn.close()
    finally:
        with psycopg.connect(_PG, autocommit=True) as c:
            c.execute(f"DROP TABLE IF EXISTS {tbl}")
