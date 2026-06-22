"""Postgres claim/lease primitive — the shared queue mechanism (spec §4).

State tables ARE the queue. ``claim_due_work`` atomically claims due rows with
FOR UPDATE SKIP LOCKED and a visibility-timeout lease; an expired lease is
reclaimable (crash recovery). Takes a connection — no driver import here, so
it's reusable by both the process adapter and the job queue, and layer-clean.

Security note: ``table`` and ``id_column`` in the SQL strings below are
``.format``-interpolated (not parameter placeholders), because Postgres does
not allow parameterised table/column names.  This is safe **only** because
every caller supplies framework-controlled identifiers (never raw user input).
Do not expose ``table`` or ``id_column`` to user-controlled values.
"""

from __future__ import annotations

from datetime import datetime


def queue_columns_ddl(table: str) -> str:
    """Column set any queue table carries.

    ``table`` is accepted for API symmetry / future index naming — currently
    unused in the DDL fragment itself (the caller owns the CREATE INDEX).
    """
    return (
        "status text NOT NULL DEFAULT 'pending', "
        "deliver_at timestamptz NOT NULL DEFAULT now(), "
        "claimed_by text, claimed_at timestamptz, lease_expires_at timestamptz, "
        "attempts int NOT NULL DEFAULT 0, "
        "payload jsonb NOT NULL DEFAULT '{}'::jsonb"
    )


# Dead-letter sweep: move crash-looping rows (lease expired, attempts exhausted)
# to 'dead' BEFORE the claim CTE so they are never re-claimed.
_DEAD_LETTER_SWEEP = """
UPDATE {table}
SET status = 'dead'
WHERE status = 'claimed'
  AND lease_expires_at <= now()
  AND attempts >= %(max)s;
"""

_CLAIM = """
WITH due AS (
    SELECT {id_column} FROM {table}
    WHERE (status = 'pending' AND deliver_at <= now())
       OR (status = 'claimed' AND lease_expires_at <= now() AND attempts < %(max)s)
    ORDER BY deliver_at, {id_column}
    FOR UPDATE SKIP LOCKED
    LIMIT %(batch)s
)
UPDATE {table} t
SET status='claimed', claimed_by=%(worker)s, claimed_at=now(),
    lease_expires_at = now() + (%(lease)s || ' seconds')::interval,
    attempts = t.attempts + 1
FROM due WHERE t.{id_column} = due.{id_column}
RETURNING t.{id_column};
"""


def claim_due_work(
    conn,
    *,
    table: str,
    worker: str,
    lease_seconds: int,
    batch: int = 1,
    max_attempts: int = 5,
    id_column: str = "id",
) -> list[str]:
    """Atomically claim up to *batch* due rows and return their ids.

    A row is due when:
    * ``status='pending'`` and ``deliver_at <= now()``, or
    * ``status='claimed'`` and ``lease_expires_at <= now()`` and
      ``attempts < max_attempts`` (expired lease — crash recovery).

    Before claiming, rows whose lease has expired AND whose ``attempts`` have
    reached *max_attempts* are swept to ``status='dead'`` (crash-loop
    dead-lettering).  This ensures a worker that crashes without calling
    ``fail_work`` does not loop forever.

    The SELECT uses FOR UPDATE SKIP LOCKED so concurrent workers never
    double-claim the same row.

    ``id_column`` names the primary-key column of *table*.  Defaults to
    ``"id"`` (job_messages / generic queue tables).  Pass ``"run_id"`` for
    ``process_runs``.  The value is format-interpolated, never a SQL parameter
    — callers must supply a framework-controlled identifier.

    NOTE: this helper autonomous-commits (calls ``conn.commit()``).  A future
    transactional-outbox caller that needs a commit-less variant must factor
    out the cursor work separately.
    """
    params = {"batch": batch, "worker": worker, "lease": lease_seconds, "max": max_attempts}
    sql_vars = {"table": table, "id_column": id_column}
    with conn.cursor() as cur:
        cur.execute(_DEAD_LETTER_SWEEP.format(**sql_vars), params)
        cur.execute(_CLAIM.format(**sql_vars), params)
        rows = cur.fetchall()
    conn.commit()
    return [str(r[0]) for r in rows]


def renew_lease(
    conn, *, table: str, row_id: str, lease_seconds: int, id_column: str = "id"
) -> None:
    """Extend the visibility-timeout lease on a row that is still being processed.

    ``id_column`` defaults to ``"id"``; pass ``"run_id"`` for ``process_runs``.

    NOTE: autonomous-commits (calls ``conn.commit()``).
    """
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {table} SET lease_expires_at = now() + (%s||' seconds')::interval "
            f"WHERE {id_column}=%s AND status='claimed'",
            (lease_seconds, row_id),
        )
    conn.commit()


def complete_work(conn, *, table: str, row_id: str, id_column: str = "id") -> None:
    """Mark a claimed row as successfully processed (``status='done'``).

    ``id_column`` defaults to ``"id"``; pass ``"run_id"`` for ``process_runs``.

    NOTE: autonomous-commits (calls ``conn.commit()``).
    """
    with conn.cursor() as cur:
        cur.execute(f"UPDATE {table} SET status='done' WHERE {id_column}=%s", (row_id,))
    conn.commit()


def fail_work(
    conn,
    *,
    table: str,
    row_id: str,
    error: str,
    retry_at: datetime | None = None,
    max_attempts: int = 5,
    id_column: str = "id",
) -> str:
    """Retry (reset to pending with deliver_at=retry_at) until max_attempts, then dead-letter.

    Mirrors PostgresBus's nack/DLQ split (spike 'carry forward'): ``attempts``
    is the discriminator; a row at or over *max_attempts* goes
    ``status='dead'``.

    ``id_column`` defaults to ``"id"``; pass ``"run_id"`` for ``process_runs``.

    Returns ``"retry"`` or ``"dead"``.

    NOTE: autonomous-commits (calls ``conn.commit()``).
    """
    with conn.cursor() as cur:
        cur.execute(f"SELECT attempts FROM {table} WHERE {id_column}=%s", (row_id,))
        row = cur.fetchone()
        attempts = row[0] if row else 0
        if attempts >= max_attempts:
            cur.execute(
                f"UPDATE {table} SET status='dead', payload = payload || %s WHERE {id_column}=%s",
                ('{"last_error": ' + _json(error) + "}", row_id),
            )
            outcome = "dead"
        else:
            cur.execute(
                f"UPDATE {table} SET status='pending', deliver_at=%s, "
                f"payload = payload || %s WHERE {id_column}=%s",
                (retry_at or _now(), '{"last_error": ' + _json(error) + "}", row_id),
            )
            outcome = "retry"
    conn.commit()
    return outcome


def _now() -> datetime:
    from datetime import UTC
    from datetime import datetime as _dt

    return _dt.now(UTC)


def _json(s: str) -> str:
    import json

    return json.dumps(s)
