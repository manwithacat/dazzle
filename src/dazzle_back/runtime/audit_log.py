"""
Audit logging for access control decisions.

Provides async, non-blocking audit trail for all authorization decisions,
following the _dazzle_event_outbox pattern. PostgreSQL only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

logger = logging.getLogger("dazzle.audit")


@dataclass
class AuditDecision:
    """Parameters for an audit log decision entry, replacing 14 individual parameters."""

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
    """
    Async audit logger with bounded queue.

    Writes access control decisions to the _dazzle_audit_log table.
    Non-blocking — entries are queued and flushed in background.
    Dropped entries are counted and logged to stderr.

    Requires PostgreSQL (psycopg). Raises RuntimeError if unavailable.
    """

    def __init__(
        self,
        database_url: str,
        max_queue_size: int = 10000,
        flush_interval: float = 1.0,
    ):
        self._database_url = database_url
        self._max_queue_size = max_queue_size
        self._flush_interval = flush_interval
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_queue_size)
        self._dropped_count = 0
        self._task: asyncio.Task[None] | None = None
        self._stopped = False
        self._init_db()

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
                conn.commit()
            finally:
                conn.close()
        except Exception:
            logger.warning("Failed to initialize audit log table", exc_info=True)

    def start(self) -> None:
        """Start the background flush task."""
        if self._task is None or self._task.done():
            self._stopped = False
            self._task = asyncio.ensure_future(self._flush_loop())

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

    async def _flush(self) -> None:
        """Flush all queued entries to the database."""
        entries: list[dict[str, Any]] = []
        while not self._queue.empty():
            try:
                entries.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not entries:
            return

        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
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
