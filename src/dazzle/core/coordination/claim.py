"""Postgres claim/lease primitive — the shared queue mechanism (spec §4).

State tables ARE the queue. ``claim_due_work`` atomically claims due rows with
FOR UPDATE SKIP LOCKED and a visibility-timeout lease; an expired lease is
reclaimable (crash recovery). Takes a connection — no driver import here, so
it's reusable by both the process adapter and the job queue, and layer-clean.

Security note: ``table`` in the SQL strings below is ``.format``-interpolated
(not a parameter placeholder), because Postgres does not allow parameterised
table names. This is safe **only** because every caller supplies a
framework-controlled identifier (never raw user input). Do not expose
``table`` to user-controlled values.
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


_CLAIM = """
WITH due AS (
    SELECT id FROM {table}
    WHERE (status = 'pending' AND deliver_at <= now())
       OR (status = 'claimed' AND lease_expires_at <= now())
    ORDER BY deliver_at
    FOR UPDATE SKIP LOCKED
    LIMIT %(batch)s
)
UPDATE {table} t
SET status='claimed', claimed_by=%(worker)s, claimed_at=now(),
    lease_expires_at = now() + (%(lease)s || ' seconds')::interval,
    attempts = t.attempts + 1
FROM due WHERE t.id = due.id
RETURNING t.id;
"""


def claim_due_work(
    conn,
    *,
    table: str,
    worker: str,
    lease_seconds: int,
    batch: int = 1,
) -> list[str]:
    """Atomically claim up to *batch* due rows and return their ids.

    A row is due when:
    * ``status='pending'`` and ``deliver_at <= now()``, or
    * ``status='claimed'`` and ``lease_expires_at <= now()`` (expired lease —
      allows crash recovery without a separate reaper).

    The SELECT uses FOR UPDATE SKIP LOCKED so concurrent workers never
    double-claim the same row.
    """
    with conn.cursor() as cur:
        cur.execute(
            _CLAIM.format(table=table),
            {"batch": batch, "worker": worker, "lease": lease_seconds},
        )
        rows = cur.fetchall()
    conn.commit()
    return [str(r[0]) for r in rows]


def renew_lease(conn, *, table: str, row_id: str, lease_seconds: int) -> None:
    """Extend the visibility-timeout lease on a row that is still being processed."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {table} SET lease_expires_at = now() + (%s||' seconds')::interval "
            "WHERE id=%s AND status='claimed'",
            (lease_seconds, row_id),
        )
    conn.commit()


def complete_work(conn, *, table: str, row_id: str) -> None:
    """Mark a claimed row as successfully processed (``status='done'``)."""
    with conn.cursor() as cur:
        cur.execute(f"UPDATE {table} SET status='done' WHERE id=%s", (row_id,))
    conn.commit()


def fail_work(
    conn,
    *,
    table: str,
    row_id: str,
    error: str,
    retry_at: datetime | None = None,
    max_attempts: int = 5,
) -> str:
    """Retry (reset to pending with deliver_at=retry_at) until max_attempts, then dead-letter.

    Mirrors PostgresBus's nack/DLQ split (spike 'carry forward'): ``attempts``
    is the discriminator; a row at or over *max_attempts* goes
    ``status='dead'``.

    Returns ``"retry"`` or ``"dead"``.
    """
    with conn.cursor() as cur:
        cur.execute(f"SELECT attempts FROM {table} WHERE id=%s", (row_id,))
        row = cur.fetchone()
        attempts = row[0] if row else 0
        if attempts >= max_attempts:
            cur.execute(
                f"UPDATE {table} SET status='dead', payload = payload || %s WHERE id=%s",
                ('{"last_error": ' + _json(error) + "}", row_id),
            )
            outcome = "dead"
        else:
            cur.execute(
                f"UPDATE {table} SET status='pending', deliver_at=%s, "
                "payload = payload || %s WHERE id=%s",
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
