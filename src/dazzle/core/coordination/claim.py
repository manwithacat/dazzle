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


_TERMINAL_STATUSES = frozenset({"done", "dead", "completed", "failed", "cancelled"})

# SQL fragment — terminal statuses as a quoted tuple literal used in NOT IN.
_TERMINAL_SQL = ", ".join(f"'{s}'" for s in sorted(_TERMINAL_STATUSES))


def renew_lease(
    conn,
    *,
    table: str,
    row_id: str,
    lease_seconds: int,
    id_column: str = "id",
    worker: str | None = None,
) -> None:
    """Extend the visibility-timeout lease on a row that is still being processed.

    Matches *any* non-terminal row that currently holds a lease (i.e.
    ``lease_expires_at IS NOT NULL``), not just ``status='claimed'``.  This is
    required because ``execute_process_steps`` transitions the row to
    ``status='running'`` (via ``save_run``) *before* the first heartbeat fires,
    so a ``WHERE status='claimed'`` predicate would match zero rows and the
    heartbeat would be a no-op — the lease would expire and the run would be
    reclaimed while the worker is still healthy.

    When *worker* is supplied the update is additionally fenced on
    ``claimed_by = %(worker)s`` (ownership token).  This prevents a superseded
    worker from silently extending a lease that has already been reclaimed by a
    new worker — the fenced update matches zero rows for the old holder, which is
    the safe fail-closed outcome.

    ``id_column`` defaults to ``"id"``; pass ``"run_id"`` for ``process_runs``.

    NOTE: autonomous-commits (calls ``conn.commit()``).
    """
    fence = " AND claimed_by = %(worker)s" if worker else ""
    sql = (
        f"UPDATE {table} "
        f"SET lease_expires_at = now() + (%(lease)s || ' seconds')::interval "
        f"WHERE {id_column} = %(row_id)s "
        f"  AND lease_expires_at IS NOT NULL "
        f"  AND status NOT IN ({_TERMINAL_SQL})"
        f"{fence}"
    )
    params: dict[str, object] = {"lease": lease_seconds, "row_id": row_id}
    if worker:
        params["worker"] = worker
    with conn.cursor() as cur:
        cur.execute(sql, params)
    conn.commit()


def complete_work(
    conn,
    *,
    table: str,
    row_id: str,
    id_column: str = "id",
    worker: str | None = None,
) -> None:
    """Mark a claimed row as successfully processed (``status='done'``).

    When *worker* is supplied the update is fenced on ``claimed_by = %(worker)s``
    so only the current lease holder can complete the row.  A superseded worker's
    call matches zero rows (fail-safe).

    ``id_column`` defaults to ``"id"``; pass ``"run_id"`` for ``process_runs``.

    NOTE: autonomous-commits (calls ``conn.commit()``).
    """
    if worker:
        sql = (
            f"UPDATE {table} SET status='done' "
            f"WHERE {id_column} = %(row_id)s AND claimed_by = %(worker)s"
        )
        params: dict[str, object] = {"row_id": row_id, "worker": worker}
    else:
        sql = f"UPDATE {table} SET status='done' WHERE {id_column}=%s"
        params = {}
        with conn.cursor() as cur:
            cur.execute(sql, (row_id,))
        conn.commit()
        return
    with conn.cursor() as cur:
        cur.execute(sql, params)
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
    worker: str | None = None,
) -> str:
    """Retry (reset to pending with deliver_at=retry_at) until max_attempts, then dead-letter.

    Mirrors PostgresBus's nack/DLQ split (spike 'carry forward'): ``attempts``
    is the discriminator; a row at or over *max_attempts* goes
    ``status='dead'``.

    When *worker* is supplied the write is fenced on ``claimed_by = %(worker)s``:
    only the current lease holder can fail/retry the row.  A superseded worker's
    call skips the SELECT (row_id unchanged) and commits a no-op — fail-safe.

    ``id_column`` defaults to ``"id"``; pass ``"run_id"`` for ``process_runs``.

    Returns ``"retry"`` or ``"dead"``.

    NOTE: autonomous-commits (calls ``conn.commit()``).
    """
    worker_fence = " AND claimed_by = %(worker)s" if worker else ""
    worker_params: dict[str, object] = {"worker": worker} if worker else {}
    with conn.cursor() as cur:
        cur.execute(f"SELECT attempts FROM {table} WHERE {id_column}=%s", (row_id,))
        row = cur.fetchone()
        attempts = row[0] if row else 0
        if attempts >= max_attempts:
            cur.execute(
                f"UPDATE {table} SET status='dead', payload = payload || %(err)s "
                f"WHERE {id_column} = %(row_id)s{worker_fence}",
                {"err": '{"last_error": ' + _json(error) + "}", "row_id": row_id, **worker_params},
            )
            outcome = "dead"
        else:
            cur.execute(
                f"UPDATE {table} SET status='pending', deliver_at=%(at)s, "
                f"payload = payload || %(err)s WHERE {id_column} = %(row_id)s{worker_fence}",
                {
                    "at": retry_at or _now(),
                    "err": '{"last_error": ' + _json(error) + "}",
                    "row_id": row_id,
                    **worker_params,
                },
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
