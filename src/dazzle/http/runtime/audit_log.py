"""
Audit logging for access control decisions.

Provides async, non-blocking audit trail for all authorization decisions,
following the _dazzle_event_outbox pattern. PostgreSQL only.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# #1383: per-transaction advisory-lock key that serialises the hash-chain
# head-read + batch INSERT across concurrent workers. Without it, two workers
# seed `prev_hash` from the same row and interleave INSERTs, forking the linear
# chain that `verify_chain` later assumes (→ false-positive boot warnings).
# A fixed arbitrary 32-bit int ("audt"); distinct from the membership-events key.
_AUDIT_LOG_LOCK_KEY = 0x61756474


# Columns persisted as a row of `_dazzle_audit_log`. This is also the
# canonical ordering used for the INSERT and — when `audit_integrity ==
# "hash_chain"` — for building the canonical payload that feeds the
# row-hash. `row_hash` is deliberately NOT part of this list: it depends
# on the canonical payload, so it cannot be one of its inputs.
_AUDIT_ROW_COLUMNS: tuple[str, ...] = (
    "id",
    "timestamp",
    "user_id",
    "user_email",
    "user_roles",
    "operation",
    "entity_name",
    "entity_id",
    "decision",
    "matched_policy",
    "policy_effect",
    "ip_address",
    "request_path",
    "request_method",
    "tenant_id",
    "evaluation_time_us",
    "field_changes",
)


def _canonical_payload(row: dict[str, Any]) -> str:
    """Render an audit row to its canonical hash-input string.

    Deterministic and stable: `sort_keys=True`, no whitespace, `default=str`
    for anything not natively JSON-serialisable (e.g. UUIDs). `row_hash`
    itself is stripped because the hash is computed over the row *content*,
    not over a value that depends on the hash.
    """
    payload = {k: row[k] for k in _AUDIT_ROW_COLUMNS if k in row}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _compute_row_hash(prev_hash: str, row: dict[str, Any]) -> str:
    """sha256(prev_hash || canonical_payload(row)).hexdigest().

    Empty-prev sentinel is the empty string. Hex digest. No key, no salt —
    this is chain integrity, not authenticity.
    """
    return hashlib.sha256((prev_hash + _canonical_payload(row)).encode("utf-8")).hexdigest()


@dataclass
class ChainVerifyResult:
    """Result of :meth:`AuditLogger.verify_chain`.

    Attributes:
        ok: True iff every chained row's stored hash matches recomputation.
        total_rows: All rows considered (including NULL-`row_hash` rows
            from before integrity was enabled — those are skipped, not
            counted as mismatches; see ``skipped_legacy_rows``).
        first_mismatch_id: ID of the first row whose stored hash != the
            recomputed hash, or None if the chain is intact.
        mismatched_count: Number of rows whose stored hash != recomputed.
        skipped_legacy_rows: Rows with ``row_hash IS NULL`` — these
            pre-date integrity-mode being switched on. They are treated
            as a valid seed boundary: verification of subsequent rows
            uses the last NULL row's canonical payload as the seed.
    """

    ok: bool
    total_rows: int
    first_mismatch_id: str | None
    mismatched_count: int
    skipped_legacy_rows: int = 0


@dataclass
class AuditDecision:
    """The audit event schema — one access-control decision (#1172).

    Every field below is persisted as a column of `_dazzle_audit_log`:
    who (`user_id` / `user_email` / `user_roles` / `tenant_id`), what
    (`operation` / `entity_name` / `entity_id` / `field_changes`), the
    outcome (`decision` / `matched_policy` / `policy_effect`), and the
    request context (`ip_address` / `request_path` / `request_method` /
    `evaluation_time_us`). This dataclass is the canonical shape; the
    table DDL in `AuditLogger._init_db` mirrors it.
    """

    operation: str
    entity_name: str
    entity_id: str | None
    decision: str
    matched_policy: str
    policy_effect: str
    user_id: str | None = None
    user_email: str | None = None
    user_roles: list[str] | None = None
    ip_address: str | None = None
    request_path: str | None = None
    request_method: str | None = None
    tenant_id: str | None = None
    evaluation_time_us: int | None = None
    field_changes: str | None = None


# =============================================================================
# Audit Logger
# =============================================================================


class AuditLogger:
    """Production access-decision audit trail (#1172).

    The durable audit trail for the running app: writes every
    access-control decision (and CRUD field-change diff) to the
    `_dazzle_audit_log` PostgreSQL table, wired into every generated
    route via `_log_audit_decision`. Distinct from the verification
    seam in `dazzle.rbac.audit` — that one *observes* decisions for the
    conformance / verifier tooling; this one is the real trail.

    **Fail-open by design.** Writes go through a bounded async queue
    (`max_queue_size`, default 10000) flushed in the background. If the
    queue is full the entry is dropped and `_dropped_count` is
    incremented and logged — a slow database degrades audit
    completeness but never blocks or fails a request. Callers needing
    fail-*closed* semantics must add that explicitly.

    Requires PostgreSQL (psycopg); raises RuntimeError if unavailable.
    The boot path enforces a matching fail-closed invariant: a server
    with auditable entities refuses to start without a database_url
    (see `DazzleServer._setup_routes`).
    """

    def __init__(
        self,
        database_url: str,
        max_queue_size: int = 10000,
        flush_interval: float = 1.0,
        audit_integrity: str = "none",
    ):
        if audit_integrity not in ("none", "hash_chain"):
            raise ValueError(
                f"audit_integrity must be 'none' or 'hash_chain', got {audit_integrity!r}"
            )
        self._database_url = database_url
        self._max_queue_size = max_queue_size
        self._flush_interval = flush_interval
        self._audit_integrity = audit_integrity
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_queue_size)
        self._dropped_count = 0
        self._task: asyncio.Task[None] | None = None
        self._stopped = False
        self._init_db()
        # Startup verification — log a single WARNING (not raise) if the
        # chain is broken. A bootstrap failure here would deny legitimate
        # access for a non-malicious data event (e.g. partial restore);
        # the goal is signal, not bootstrap denial. #1197.
        if self._audit_integrity == "hash_chain":
            try:
                result = self.verify_chain()
                if not result.ok:
                    logger.warning(
                        "Audit hash-chain verification found %d mismatched row(s); "
                        "first mismatch at id=%s",
                        result.mismatched_count,
                        result.first_mismatch_id,
                    )
            except Exception:
                logger.warning("Audit hash-chain startup verification failed", exc_info=True)

    def _get_connection(self) -> Any:
        """Get a PostgreSQL database connection.

        Raises RuntimeError if psycopg is not installed or connection fails.
        """
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError:
            raise RuntimeError(
                "psycopg is required for audit logging. "
                "Install it with: pip install psycopg[binary]"
            )

        try:
            conn = psycopg.connect(self._database_url, row_factory=dict_row)
        except Exception as exc:
            raise RuntimeError(f"Failed to connect to PostgreSQL for audit logging: {exc}") from exc

        return conn

    def _init_db(self) -> None:
        """Create the audit log table if it doesn't exist."""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS _dazzle_audit_log (
                        id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        user_id TEXT,
                        user_email TEXT,
                        user_roles TEXT,
                        operation TEXT NOT NULL,
                        entity_name TEXT NOT NULL,
                        entity_id TEXT,
                        decision TEXT NOT NULL,
                        matched_policy TEXT,
                        policy_effect TEXT,
                        ip_address TEXT,
                        request_path TEXT,
                        request_method TEXT,
                        tenant_id TEXT,
                        evaluation_time_us INTEGER,
                        field_changes TEXT
                    )
                """)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_entity "
                    "ON _dazzle_audit_log(entity_name, timestamp)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_user "
                    "ON _dazzle_audit_log(user_id, timestamp)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON _dazzle_audit_log(timestamp)"
                )
                # Opt-in tamper-evident hash chain (#1197). Only when
                # `audit_integrity == "hash_chain"` do we touch the
                # schema; the default ("none") path leaves the table
                # byte-identical to today's behaviour.
                if self._audit_integrity == "hash_chain":
                    cursor.execute(
                        "ALTER TABLE _dazzle_audit_log ADD COLUMN IF NOT EXISTS row_hash TEXT"
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            logger.warning("Failed to initialize audit log table", exc_info=True)

    def start(self) -> None:
        """Start the background flush task.

        Must be called from within a running event loop — typically the
        app lifespan startup (see ``DazzleServer._lifespan``). Calling from a
        sync context with no running loop raises ``RuntimeError`` on
        Py3.12+ (#1214); the previous ``asyncio.ensure_future`` path
        silently relied on the deprecated implicit loop acquisition.
        """
        if self._task is None or self._task.done():
            self._stopped = False
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._flush_loop())

    async def stop(self) -> None:
        """Stop the background flush task and flush remaining entries."""
        self._stopped = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # Final flush
        await self._flush()

    async def log_decision(
        self,
        operation: str = "",
        entity_name: str = "",
        entity_id: str | None = None,
        decision: str = "",
        matched_policy: str = "",
        policy_effect: str = "",
        user_id: str | None = None,
        user_email: str | None = None,
        user_roles: list[str] | None = None,
        ip_address: str | None = None,
        request_path: str | None = None,
        request_method: str | None = None,
        tenant_id: str | None = None,
        evaluation_time_us: int | None = None,
        field_changes: str | None = None,
        *,
        audit_decision: AuditDecision | None = None,
    ) -> None:
        """
        Queue an audit log entry. Non-blocking — drops if queue is full.

        Args:
            operation: CRUD operation (create/read/update/delete/list)
            entity_name: Name of the entity type
            entity_id: ID of the specific record (None for list/create)
            decision: "allow" or "deny"
            matched_policy: Description of the matching policy rule
            policy_effect: "permit", "forbid", or "default"
            user_id: Authenticated user ID
            user_email: User email for readability
            user_roles: User roles as list
            ip_address: Request origin IP
            request_path: URL path
            request_method: HTTP method
            tenant_id: Multi-tenant scope
            evaluation_time_us: Policy evaluation latency in microseconds
        """
        if audit_decision is not None:
            d = audit_decision
            operation = d.operation
            entity_name = d.entity_name
            entity_id = d.entity_id
            decision = d.decision
            matched_policy = d.matched_policy
            policy_effect = d.policy_effect
            user_id = d.user_id
            user_email = d.user_email
            user_roles = d.user_roles
            ip_address = d.ip_address
            request_path = d.request_path
            request_method = d.request_method
            tenant_id = d.tenant_id
            evaluation_time_us = d.evaluation_time_us
            field_changes = d.field_changes

        import json
        from datetime import UTC, datetime

        entry = {
            "id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "user_id": user_id,
            "user_email": user_email,
            "user_roles": json.dumps(user_roles or []),
            "operation": operation,
            "entity_name": entity_name,
            "entity_id": entity_id,
            "decision": decision,
            "matched_policy": matched_policy,
            "policy_effect": policy_effect,
            "ip_address": ip_address,
            "request_path": request_path,
            "request_method": request_method,
            "tenant_id": tenant_id,
            "evaluation_time_us": evaluation_time_us,
            "field_changes": field_changes,
        }

        try:
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            self._dropped_count += 1
            if self._dropped_count % 100 == 1:
                logger.error("Audit log queue full, dropped %d entries", self._dropped_count)

    async def _flush_loop(self) -> None:
        """Background loop that flushes queued entries periodically."""
        while not self._stopped:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("Audit flush error", exc_info=True)

    def _drain_queue(self) -> list[dict[str, Any]]:
        """Pop every currently-queued entry off the queue (non-blocking)."""
        entries: list[dict[str, Any]] = []
        while not self._queue.empty():
            try:
                entries.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return entries

    def _write_entries(self, entries: list[dict[str, Any]]) -> None:
        """Synchronously INSERT a batch of audit entries into PostgreSQL.

        When ``audit_integrity == "hash_chain"`` each row's ``row_hash`` is
        threaded forward in memory: row N's prev = row N-1's hash. The
        previous-hash seed for the batch is fetched once with a single
        SELECT; we never query inside the loop. The default path (no
        integrity) is byte-identical to the pre-#1197 INSERT.
        """
        if not entries:
            return
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                if self._audit_integrity == "hash_chain":
                    # #1383: serialise the head-read + batch INSERT across
                    # workers. pg_advisory_xact_lock is held until conn.commit()
                    # below, so concurrent flushes can't seed from the same row
                    # and interleave — the chain stays linear.
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_AUDIT_LOG_LOCK_KEY,))
                    # Seed the chain from the most-recent existing row.
                    # `timestamp` is the only monotonically-increasing
                    # column we have ('id' is a uuid). Empty table → "".
                    cursor.execute(
                        "SELECT row_hash FROM _dazzle_audit_log ORDER BY timestamp DESC LIMIT 1"
                    )
                    seed_row = cursor.fetchone()
                    prev_hash = ""
                    if seed_row is not None:
                        # dict_row factory → mapping; psycopg also returns
                        # tuples in some configurations. Handle both.
                        if isinstance(seed_row, dict):
                            prev_hash = seed_row.get("row_hash") or ""
                        else:
                            prev_hash = seed_row[0] or ""
                    for entry in entries:
                        row_hash = _compute_row_hash(prev_hash, entry)
                        entry["row_hash"] = row_hash
                        prev_hash = row_hash
                        cursor.execute(
                            """
                            INSERT INTO _dazzle_audit_log
                                (id, timestamp, user_id, user_email, user_roles,
                                 operation, entity_name, entity_id, decision,
                                 matched_policy, policy_effect, ip_address,
                                 request_path, request_method, tenant_id,
                                 evaluation_time_us, field_changes, row_hash)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            tuple(entry[c] for c in _AUDIT_ROW_COLUMNS) + (row_hash,),
                        )
                else:
                    for entry in entries:
                        cursor.execute(
                            """
                            INSERT INTO _dazzle_audit_log
                                (id, timestamp, user_id, user_email, user_roles,
                                 operation, entity_name, entity_id, decision,
                                 matched_policy, policy_effect, ip_address,
                                 request_path, request_method, tenant_id,
                                 evaluation_time_us, field_changes)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            tuple(entry.values()),
                        )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            logger.warning("Failed to write %d audit entries", len(entries), exc_info=True)

    def verify_chain(self) -> ChainVerifyResult:
        """Walk `_dazzle_audit_log` in chain order and verify every row_hash.

        Rows with ``row_hash IS NULL`` are treated as a **valid seed
        boundary**, not a mismatch: they pre-date integrity-mode being
        switched on, and verifying them against the post-switch chain
        would always fail. They are counted in ``skipped_legacy_rows``.
        The verification "seed" for the first chained row after a run of
        NULL rows is the empty string ``""`` — the same seed used for an
        empty table. This means a clean ALTER (none → hash_chain) lets
        the chain begin from the next inserted row, with the legacy rows
        ignored.

        Returns:
            ChainVerifyResult with ok / first_mismatch_id / counts.
        """
        if self._audit_integrity != "hash_chain":
            # Not enabled — nothing to verify. Report ok=True, zero rows.
            return ChainVerifyResult(
                ok=True,
                total_rows=0,
                first_mismatch_id=None,
                mismatched_count=0,
                skipped_legacy_rows=0,
            )

        first_mismatch_id: str | None = None
        mismatched = 0
        skipped = 0
        total = 0
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM _dazzle_audit_log ORDER BY timestamp ASC, id ASC")
                rows = cursor.fetchall()
            finally:
                conn.close()
        except Exception:
            logger.warning("verify_chain: failed to read audit log", exc_info=True)
            return ChainVerifyResult(
                ok=False,
                total_rows=0,
                first_mismatch_id=None,
                mismatched_count=0,
                skipped_legacy_rows=0,
            )

        prev_hash = ""
        for raw in rows:
            row = dict(raw) if not isinstance(raw, dict) else raw
            total += 1
            stored = row.get("row_hash")
            if stored is None:
                # Pre-integrity legacy row: treat as seed boundary.
                # Reset prev_hash to "" so the first post-switch row
                # verifies the same way it was written.
                skipped += 1
                prev_hash = ""
                continue
            expected = _compute_row_hash(prev_hash, row)
            if expected != stored:
                mismatched += 1
                if first_mismatch_id is None:
                    first_mismatch_id = str(row.get("id"))
            # Even on mismatch, advance the chain using the STORED hash
            # so downstream rows are evaluated against what's actually
            # in the DB (otherwise one tampered row cascades into every
            # subsequent row also being flagged).
            prev_hash = stored

        return ChainVerifyResult(
            ok=mismatched == 0,
            total_rows=total,
            first_mismatch_id=first_mismatch_id,
            mismatched_count=mismatched,
            skipped_legacy_rows=skipped,
        )

    async def _flush(self) -> None:
        """Flush all queued entries to the database."""
        self._write_entries(self._drain_queue())

    def drain(self) -> int:
        """Synchronously flush every queued entry to the database, now.

        Unlike the background ``_flush_loop`` (which only runs on the timer
        and depends on event-loop scheduling), this writes the current queue
        contents inline and returns the number of entries persisted. It does
        no ``await`` and acquires its own short-lived connection, so it is
        safe to call from a synchronous context or from inside an async test
        without racing the background flush task.

        This is the deterministic observability seam: a test (or a graceful
        shutdown path) that needs the audit trail to be readable *right now*
        calls ``drain()`` instead of sleeping and hoping the 1s timer fired.
        """
        entries = self._drain_queue()
        self._write_entries(entries)
        return len(entries)

    def query_logs(
        self,
        entity_name: str | None = None,
        operation: str | None = None,
        user_id: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Query audit logs with optional filters.

        Args:
            entity_name: Filter by entity type
            operation: Filter by operation
            user_id: Filter by user
            since: ISO timestamp to filter from
            limit: Max results

        Returns:
            List of audit log entries
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            rows = _execute_query_logs(cursor, entity_name, operation, user_id, since, limit)
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def query_entity_logs(
        self,
        entity_name: str,
        entity_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query all audit entries for a specific record."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM _dazzle_audit_log "
                "WHERE entity_name = %s AND entity_id = %s "
                "ORDER BY timestamp DESC LIMIT %s",
                (entity_name, entity_id, limit),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def query_stats(
        self,
        entity_name: str | None = None,
        window_hours: int = 24,
    ) -> dict[str, Any]:
        """
        Get aggregated audit statistics.

        Returns counts by operation, decision, and entity.
        """
        from datetime import UTC, datetime, timedelta

        since = (datetime.now(UTC) - timedelta(hours=window_hours)).isoformat()
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            if entity_name:
                params: tuple[Any, ...] = (since, entity_name)
                cursor.execute(
                    "SELECT decision, COUNT(*) as count FROM _dazzle_audit_log "
                    "WHERE timestamp >= %s AND entity_name = %s "
                    "GROUP BY decision",
                    params,
                )
                by_decision = {row["decision"]: row["count"] for row in cursor.fetchall()}
                cursor.execute(
                    "SELECT operation, COUNT(*) as count FROM _dazzle_audit_log "
                    "WHERE timestamp >= %s AND entity_name = %s "
                    "GROUP BY operation",
                    params,
                )
                by_operation = {row["operation"]: row["count"] for row in cursor.fetchall()}
            else:
                cursor.execute(
                    "SELECT decision, COUNT(*) as count FROM _dazzle_audit_log "
                    "WHERE timestamp >= %s "
                    "GROUP BY decision",
                    (since,),
                )
                by_decision = {row["decision"]: row["count"] for row in cursor.fetchall()}
                cursor.execute(
                    "SELECT operation, COUNT(*) as count FROM _dazzle_audit_log "
                    "WHERE timestamp >= %s "
                    "GROUP BY operation",
                    (since,),
                )
                by_operation = {row["operation"]: row["count"] for row in cursor.fetchall()}

            return {
                "window_hours": window_hours,
                "by_decision": by_decision,
                "by_operation": by_operation,
                "total": sum(by_decision.values()),
            }
        finally:
            conn.close()


# Static query lookup for query_logs — every combination of the 4 optional
# filters is a pre-built literal string so no SQL concatenation happens at
# runtime.  Bits: entity_name=8, operation=4, user_id=2, since=1.
_QUERY_LOGS: dict[int, str] = {
    0b0000: ("SELECT * FROM _dazzle_audit_log ORDER BY timestamp DESC LIMIT %s"),
    0b1000: (
        "SELECT * FROM _dazzle_audit_log WHERE entity_name = %s ORDER BY timestamp DESC LIMIT %s"
    ),
    0b0100: (
        "SELECT * FROM _dazzle_audit_log WHERE operation = %s ORDER BY timestamp DESC LIMIT %s"
    ),
    0b1100: (
        "SELECT * FROM _dazzle_audit_log WHERE entity_name = %s AND operation = %s"
        " ORDER BY timestamp DESC LIMIT %s"
    ),
    0b0010: ("SELECT * FROM _dazzle_audit_log WHERE user_id = %s ORDER BY timestamp DESC LIMIT %s"),
    0b1010: (
        "SELECT * FROM _dazzle_audit_log WHERE entity_name = %s AND user_id = %s"
        " ORDER BY timestamp DESC LIMIT %s"
    ),
    0b0110: (
        "SELECT * FROM _dazzle_audit_log WHERE operation = %s AND user_id = %s"
        " ORDER BY timestamp DESC LIMIT %s"
    ),
    0b1110: (
        "SELECT * FROM _dazzle_audit_log"
        " WHERE entity_name = %s AND operation = %s AND user_id = %s"
        " ORDER BY timestamp DESC LIMIT %s"
    ),
    0b0001: (
        "SELECT * FROM _dazzle_audit_log WHERE timestamp >= %s ORDER BY timestamp DESC LIMIT %s"
    ),
    0b1001: (
        "SELECT * FROM _dazzle_audit_log WHERE entity_name = %s AND timestamp >= %s"
        " ORDER BY timestamp DESC LIMIT %s"
    ),
    0b0101: (
        "SELECT * FROM _dazzle_audit_log WHERE operation = %s AND timestamp >= %s"
        " ORDER BY timestamp DESC LIMIT %s"
    ),
    0b1101: (
        "SELECT * FROM _dazzle_audit_log"
        " WHERE entity_name = %s AND operation = %s AND timestamp >= %s"
        " ORDER BY timestamp DESC LIMIT %s"
    ),
    0b0011: (
        "SELECT * FROM _dazzle_audit_log WHERE user_id = %s AND timestamp >= %s"
        " ORDER BY timestamp DESC LIMIT %s"
    ),
    0b1011: (
        "SELECT * FROM _dazzle_audit_log"
        " WHERE entity_name = %s AND user_id = %s AND timestamp >= %s"
        " ORDER BY timestamp DESC LIMIT %s"
    ),
    0b0111: (
        "SELECT * FROM _dazzle_audit_log"
        " WHERE operation = %s AND user_id = %s AND timestamp >= %s"
        " ORDER BY timestamp DESC LIMIT %s"
    ),
    0b1111: (
        "SELECT * FROM _dazzle_audit_log"
        " WHERE entity_name = %s AND operation = %s AND user_id = %s AND timestamp >= %s"
        " ORDER BY timestamp DESC LIMIT %s"
    ),
}


def _execute_query_logs(
    cursor: Any,
    entity_name: str | None,
    operation: str | None,
    user_id: str | None,
    since: str | None,
    limit: int,
) -> list[Any]:
    """Execute a filtered query on _dazzle_audit_log.

    Uses a static query lookup keyed by a bitmask of which filters are active.
    All SQL strings are pre-built literals — no concatenation at call time.
    """
    key = 0
    params: list[Any] = []
    if entity_name:
        key |= 0b1000
        params.append(entity_name)
    if operation:
        key |= 0b0100
        params.append(operation)
    if user_id:
        key |= 0b0010
        params.append(user_id)
    if since:
        key |= 0b0001
        params.append(since)
    params.append(limit)

    cursor.execute(_QUERY_LOGS[key], tuple(params))
    return cursor.fetchall()  # type: ignore[no-any-return]


def create_audit_context_from_request(request: Any) -> dict[str, Any]:
    """Extract audit context fields from a FastAPI request."""
    ctx: dict[str, Any] = {
        "ip_address": None,
        "request_path": None,
        "request_method": None,
    }
    if hasattr(request, "client") and request.client:
        ctx["ip_address"] = request.client.host
    if hasattr(request, "url"):
        ctx["request_path"] = str(request.url.path)
    if hasattr(request, "method"):
        ctx["request_method"] = request.method
    return ctx


def measure_evaluation_time(func: Any) -> Any:
    """Measure policy evaluation time in microseconds."""
    start = time.perf_counter_ns()
    result = func()
    elapsed_us = (time.perf_counter_ns() - start) // 1000
    return result, elapsed_us
