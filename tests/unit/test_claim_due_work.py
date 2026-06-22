"""Real-Postgres proof of the `claim_due_work` lease primitive (coordination §4).

Exercises:
 * No double-claim across 4 concurrent workers (300-row table, 4 threads).
 * Expired-lease reclaim — a row with a timed-out lease is claimed again.
 * fail_work retry→dead path — attempts counter drives the transition.
 * fail_work payload merge — last_error is actually written to the jsonb payload.
 * renew_lease — extending a lease prevents reclaim within the renewed window.
 * Crash-loop dead-letter — a row that is repeatedly claimed-and-expired (no
   fail_work) reaches status='dead' once attempts hits max_attempts.
 * Non-default id_column — claim_due_work/complete_work/fail_work work correctly
   against a table whose PK column is not ``id`` (e.g. ``run_id``).

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
                ids = claim_due_work(
                    conn,
                    table=tbl,
                    worker="w0",
                    lease_seconds=30,
                    batch=1,
                    max_attempts=max_attempts,
                )
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


@pytest.mark.skipif(not _PG, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_fail_work_payload_merge() -> None:
    """fail_work writes last_error into the jsonb payload (not just status)."""
    import psycopg

    from dazzle.core.coordination.claim import (
        claim_due_work,
        fail_work,
        queue_columns_ddl,
    )

    tbl = f"claim_payload_{uuid.uuid4().hex[:8]}"
    row_id = str(uuid.uuid4())
    with psycopg.connect(_PG, autocommit=True) as c:
        c.execute(f"CREATE TABLE {tbl} (id uuid PRIMARY KEY, {queue_columns_ddl(tbl)})")
        c.execute(f"INSERT INTO {tbl} (id, deliver_at) VALUES (%s, now())", (row_id,))
    try:
        conn = psycopg.connect(_PG)
        try:
            # Exhaust attempts so the final fail_work dead-letters.
            max_attempts = 2
            error_msg = "something went very wrong"
            for attempt in range(1, max_attempts + 1):
                claim_due_work(
                    conn,
                    table=tbl,
                    worker="w0",
                    lease_seconds=30,
                    batch=1,
                    max_attempts=max_attempts,
                )
                outcome = fail_work(
                    conn,
                    table=tbl,
                    row_id=row_id,
                    error=error_msg if attempt == max_attempts else f"interim-err{attempt}",
                    max_attempts=max_attempts,
                )
            assert outcome == "dead"

            # SELECT and assert the payload actually contains last_error.
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT status, payload->>'last_error' FROM {tbl} WHERE id=%s",
                    (row_id,),
                )
                row = cur.fetchone()
            assert row is not None
            status, last_error = row
            assert status == "dead", f"Expected dead, got {status!r}"
            assert last_error is not None, "last_error key missing from payload"
            assert error_msg in last_error, (
                f"Expected {error_msg!r} in last_error, got {last_error!r}"
            )
        finally:
            conn.close()
    finally:
        with psycopg.connect(_PG, autocommit=True) as c:
            c.execute(f"DROP TABLE IF EXISTS {tbl}")


@pytest.mark.skipif(not _PG, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_renew_lease() -> None:
    """renew_lease extends the lease so the row is not reclaimable mid-renewal window."""
    import psycopg

    from dazzle.core.coordination.claim import (
        claim_due_work,
        queue_columns_ddl,
        renew_lease,
    )

    tbl = f"claim_renew_{uuid.uuid4().hex[:8]}"
    row_id = str(uuid.uuid4())
    with psycopg.connect(_PG, autocommit=True) as c:
        c.execute(f"CREATE TABLE {tbl} (id uuid PRIMARY KEY, {queue_columns_ddl(tbl)})")
        c.execute(f"INSERT INTO {tbl} (id, deliver_at) VALUES (%s, now())", (row_id,))
    try:
        conn = psycopg.connect(_PG)
        try:
            # Claim with a very short lease (1 s).
            ids = claim_due_work(conn, table=tbl, worker="w0", lease_seconds=1, batch=1)
            assert ids == [row_id]

            # Renew to a 5-second lease BEFORE the original expires.
            renew_lease(conn, table=tbl, row_id=row_id, lease_seconds=5)

            # Sleep past the ORIGINAL 1-second window but within the renewed 5-second window.
            time.sleep(1.5)

            # A second worker must NOT be able to reclaim — lease is still valid.
            ids2 = claim_due_work(conn, table=tbl, worker="w1", lease_seconds=30, batch=1)
            assert ids2 == [], f"Row should NOT be reclaimable yet, but got {ids2}"

            # Sleep past the renewed lease (total > 5 s from renewal point + 1.5 s already slept).
            time.sleep(4.0)

            # Now the renewed lease has also expired — w1 should reclaim it.
            ids3 = claim_due_work(conn, table=tbl, worker="w1", lease_seconds=30, batch=1)
            assert ids3 == [row_id], f"Expected reclaim after renewed lease expired, got {ids3}"
        finally:
            conn.close()
    finally:
        with psycopg.connect(_PG, autocommit=True) as c:
            c.execute(f"DROP TABLE IF EXISTS {tbl}")


@pytest.mark.skipif(not _PG, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_crash_loop_dead_letter() -> None:
    """A row that is repeatedly claimed-and-expired (crash, no fail_work) is dead-lettered.

    Simulates max_attempts crashes: each cycle claims the row and then lets the
    lease expire without calling fail_work or complete_work.  After max_attempts
    expiries the row must transition to status='dead' via the claim-path sweep,
    with no explicit call to fail_work.
    """
    import psycopg

    from dazzle.core.coordination.claim import (
        claim_due_work,
        queue_columns_ddl,
    )

    tbl = f"claim_crash_{uuid.uuid4().hex[:8]}"
    row_id = str(uuid.uuid4())
    max_attempts = 3
    with psycopg.connect(_PG, autocommit=True) as c:
        c.execute(f"CREATE TABLE {tbl} (id uuid PRIMARY KEY, {queue_columns_ddl(tbl)})")
        c.execute(f"INSERT INTO {tbl} (id, deliver_at) VALUES (%s, now())", (row_id,))
    try:
        conn = psycopg.connect(_PG)
        try:
            # Simulate max_attempts crashes: claim then let lease expire each time.
            for crash_n in range(1, max_attempts + 1):
                ids = claim_due_work(
                    conn,
                    table=tbl,
                    worker="crasher",
                    lease_seconds=1,
                    batch=1,
                    max_attempts=max_attempts,
                )
                assert ids == [row_id], f"Crash {crash_n}: expected to claim {row_id}, got {ids}"
                # "Crash" — do NOT call complete_work or fail_work.
                # Wait for the lease to expire.
                time.sleep(1.2)

            # After max_attempts lease-expiries, the NEXT claim call's dead-letter
            # sweep should move the row to 'dead' (attempts == max_attempts, lease expired).
            ids_after = claim_due_work(
                conn,
                table=tbl,
                worker="sweeper",
                lease_seconds=30,
                batch=1,
                max_attempts=max_attempts,
            )
            assert ids_after == [], f"Over-limit row must not be claimed, got {ids_after}"

            # Verify the row is actually 'dead' in the DB.
            with conn.cursor() as cur:
                cur.execute(f"SELECT status, attempts FROM {tbl} WHERE id=%s", (row_id,))
                row = cur.fetchone()
            assert row is not None
            status, attempts = row
            assert status == "dead", (
                f"Expected status='dead' after {max_attempts} crash-loops, got {status!r} "
                f"(attempts={attempts})"
            )
            assert attempts >= max_attempts, f"Expected attempts >= {max_attempts}, got {attempts}"
        finally:
            conn.close()
    finally:
        with psycopg.connect(_PG, autocommit=True) as c:
            c.execute(f"DROP TABLE IF EXISTS {tbl}")


@pytest.mark.skipif(not _PG, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_non_default_id_column() -> None:
    """claim_due_work / complete_work / fail_work work against a table whose PK is not 'id'.

    Creates a temp table with PK column ``run_id`` (mirroring ``process_runs``),
    exercises the full claim → complete and claim → fail → dead-letter path,
    and verifies the crash-loop dead-letter sweep fires via the shared primitive.
    """
    import psycopg

    from dazzle.core.coordination.claim import (
        claim_due_work,
        complete_work,
        fail_work,
        queue_columns_ddl,
    )

    tbl = f"claim_runid_{uuid.uuid4().hex[:8]}"
    row_a = str(uuid.uuid4())
    row_b = str(uuid.uuid4())
    with psycopg.connect(_PG, autocommit=True) as c:
        c.execute(f"CREATE TABLE {tbl} (run_id text PRIMARY KEY, {queue_columns_ddl(tbl)})")
        c.execute(
            f"INSERT INTO {tbl} (run_id, deliver_at) VALUES (%s, now()), (%s, now())",
            (row_a, row_b),
        )

    try:
        conn = psycopg.connect(_PG)
        try:
            # ── claim → complete path ──────────────────────────────────────────
            ids = claim_due_work(
                conn, table=tbl, id_column="run_id", worker="w0", lease_seconds=30, batch=1
            )
            assert len(ids) == 1, f"Expected 1 claim, got {ids}"
            claimed_id = ids[0]
            assert claimed_id in (row_a, row_b)

            complete_work(conn, table=tbl, id_column="run_id", row_id=claimed_id)
            with conn.cursor() as cur:
                cur.execute(f"SELECT status FROM {tbl} WHERE run_id=%s", (claimed_id,))
                row = cur.fetchone()
            assert row and row[0] == "done", f"Expected 'done' after complete_work, got {row}"

            # ── claim → fail → dead-letter path for the other row ─────────────
            other_id = row_b if claimed_id == row_a else row_a
            max_attempts = 2
            for attempt in range(1, max_attempts + 1):
                ids2 = claim_due_work(
                    conn,
                    table=tbl,
                    id_column="run_id",
                    worker="w0",
                    lease_seconds=30,
                    batch=1,
                    max_attempts=max_attempts,
                )
                assert ids2 == [other_id], f"Attempt {attempt}: expected [{other_id}], got {ids2}"
                outcome = fail_work(
                    conn,
                    table=tbl,
                    id_column="run_id",
                    row_id=other_id,
                    error=f"err{attempt}",
                    max_attempts=max_attempts,
                )
                if attempt < max_attempts:
                    assert outcome == "retry"
                else:
                    assert outcome == "dead"

            with conn.cursor() as cur:
                cur.execute(f"SELECT status FROM {tbl} WHERE run_id=%s", (other_id,))
                row = cur.fetchone()
            assert row and row[0] == "dead", f"Expected 'dead' after fail exhaustion, got {row}"

            # ── crash-loop dead-letter via sweep (no fail_work) ───────────────
            row_c = str(uuid.uuid4())
            with conn.cursor() as cur:
                cur.execute(f"INSERT INTO {tbl} (run_id, deliver_at) VALUES (%s, now())", (row_c,))
                conn.commit()

            max_crash = 2
            for crash_n in range(1, max_crash + 1):
                ids3 = claim_due_work(
                    conn,
                    table=tbl,
                    id_column="run_id",
                    worker="crasher",
                    lease_seconds=1,
                    batch=1,
                    max_attempts=max_crash,
                )
                assert ids3 == [row_c], f"Crash {crash_n}: expected [{row_c}], got {ids3}"
                time.sleep(1.2)  # let lease expire without calling fail_work

            # The sweep on the next claim should dead-letter row_c.
            ids4 = claim_due_work(
                conn,
                table=tbl,
                id_column="run_id",
                worker="sweeper",
                lease_seconds=30,
                batch=1,
                max_attempts=max_crash,
            )
            assert ids4 == [], f"Over-limit row must not be claimed, got {ids4}"

            with conn.cursor() as cur:
                cur.execute(f"SELECT status, attempts FROM {tbl} WHERE run_id=%s", (row_c,))
                row = cur.fetchone()
            assert row is not None
            assert row[0] == "dead", (
                f"Expected status='dead' after {max_crash} crashes (non-default id_column), "
                f"got {row[0]!r} (attempts={row[1]})"
            )
        finally:
            conn.close()
    finally:
        with psycopg.connect(_PG, autocommit=True) as c:
            c.execute(f"DROP TABLE IF EXISTS {tbl}")
