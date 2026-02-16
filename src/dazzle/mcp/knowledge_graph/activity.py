"""
Knowledge Graph activity mixin — telemetry and activity event streaming.

Provides tool invocation logging, activity session management,
event streaming, and aggregate statistics.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from .models import ActivityEvent


class KnowledgeGraphActivity:
    """Mixin providing telemetry logging and activity event streaming."""

    # =========================================================================
    # Telemetry
    # =========================================================================

    def log_tool_invocation(
        self,
        *,
        tool_name: str,
        operation: str | None = None,
        argument_keys: list[str] | None = None,
        project_path: str | None = None,
        success: bool = True,
        error_message: str | None = None,
        result_size: int | None = None,
        duration_ms: float,
    ) -> None:
        """
        Log a single MCP tool invocation.

        Args:
            tool_name: Consolidated tool name (e.g. "dsl", "story").
            operation: Operation within the tool (e.g. "validate").
            argument_keys: JSON-serializable list of argument key names (never values).
            project_path: Active project path at call time.
            success: Whether the call succeeded.
            error_message: Truncated error message on failure.
            result_size: Length of the result string in characters.
            duration_ms: Wall-clock duration in milliseconds.
        """
        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            conn.execute(
                """
                INSERT INTO tool_invocations
                    (tool_name, operation, argument_keys, project_path,
                     success, error_message, result_size, duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tool_name,
                    operation,
                    json.dumps(argument_keys) if argument_keys else None,
                    project_path,
                    1 if success else 0,
                    error_message,
                    result_size,
                    duration_ms,
                    time.time(),
                ),
            )
            conn.commit()
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    def get_tool_invocations(
        self,
        limit: int = 50,
        tool_name_filter: str | None = None,
        since: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve recent tool invocations.

        Args:
            limit: Max rows to return.
            tool_name_filter: Filter to a specific tool name.
            since: Only return invocations after this Unix timestamp.

        Returns:
            List of invocation dicts ordered by created_at DESC.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if tool_name_filter:
            conditions.append("tool_name = ?")
            params.append(tool_name_filter)
        if since is not None:
            conditions.append("created_at >= ?")
            params.append(since)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            rows = conn.execute(
                f"SELECT * FROM tool_invocations {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    def get_tool_stats(self) -> dict[str, Any]:
        """
        Aggregate telemetry statistics.

        Returns:
            Dict with total_calls and by_tool breakdown including
            call_count, error_count, avg_duration_ms, max_duration_ms,
            first_call, and last_call per tool.
        """
        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            total = conn.execute("SELECT COUNT(*) FROM tool_invocations").fetchone()[0]
            rows = conn.execute(
                """
                SELECT
                    tool_name,
                    COUNT(*) AS call_count,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS error_count,
                    AVG(duration_ms) AS avg_duration_ms,
                    MAX(duration_ms) AS max_duration_ms,
                    MIN(created_at) AS first_call,
                    MAX(created_at) AS last_call
                FROM tool_invocations
                GROUP BY tool_name
                ORDER BY call_count DESC
                """
            ).fetchall()
            by_tool = [
                {
                    "tool_name": row["tool_name"],
                    "call_count": row["call_count"],
                    "error_count": row["error_count"],
                    "avg_duration_ms": round(row["avg_duration_ms"], 2),
                    "max_duration_ms": round(row["max_duration_ms"], 2),
                    "first_call": row["first_call"],
                    "last_call": row["last_call"],
                }
                for row in rows
            ]
            return {"total_calls": total, "by_tool": by_tool}
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    # =========================================================================
    # Activity Event Stream
    # =========================================================================

    def start_activity_session(
        self,
        project_name: str | None = None,
        project_path: str | None = None,
        version: str | None = None,
    ) -> str:
        """Start a new activity session. Returns the session_id (UUID)."""
        session_id = str(uuid.uuid4())
        now = time.time()
        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            conn.execute(
                """
                INSERT INTO activity_sessions
                    (id, project_name, project_path, dazzle_version, started_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, project_name, project_path, version, now),
            )
            conn.commit()
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]
        return session_id

    def end_activity_session(self, session_id: str) -> None:
        """Mark an activity session as ended."""
        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            conn.execute(
                "UPDATE activity_sessions SET ended_at = ? WHERE id = ?",
                (time.time(), session_id),
            )
            conn.commit()
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    def log_activity_event(
        self,
        session_id: str | ActivityEvent = "",
        event_type: str = "",
        tool: str = "",
        operation: str | None = None,
        *,
        success: bool | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
        warnings: int = 0,
        progress_current: int | None = None,
        progress_total: int | None = None,
        message: str | None = None,
        level: str = "info",
        context_json: str | None = None,
        source: str = "mcp",
        event: ActivityEvent | None = None,
    ) -> int:
        """Log an activity event. Returns the event id.

        Accepts either individual parameters or an ActivityEvent dataclass.
        """
        if isinstance(session_id, ActivityEvent):
            event = session_id
        if event is not None:
            session_id = event.session_id
            event_type = event.event_type
            tool = event.tool
            operation = event.operation
            success = event.success
            duration_ms = event.duration_ms
            error = event.error
            warnings = event.warnings
            progress_current = event.progress_current
            progress_total = event.progress_total
            message = event.message
            level = event.level
            context_json = event.context_json
            source = event.source
        now = time.time()
        ts = datetime.now(UTC).isoformat(timespec="milliseconds")
        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            cursor = conn.execute(
                """
                INSERT INTO activity_events
                    (session_id, event_type, tool, operation, ts, created_at,
                     success, duration_ms, error, warnings,
                     progress_current, progress_total, message, level, context_json,
                     source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    event_type,
                    tool,
                    operation,
                    ts,
                    now,
                    (1 if success else 0) if success is not None else None,
                    duration_ms,
                    error,
                    warnings,
                    progress_current,
                    progress_total,
                    message,
                    level,
                    context_json,
                    source,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    def get_activity_events(
        self,
        since_id: int = 0,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Cursor-based polling for activity events.

        Returns events with id > since_id, ordered by id ASC.
        """
        conditions = ["id > ?"]
        params: list[Any] = [since_id]

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        params.append(limit)
        where = " AND ".join(conditions)

        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            rows = conn.execute(
                f"SELECT * FROM activity_events WHERE {where} ORDER BY id ASC LIMIT ?",
                params,
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    def get_activity_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent activity sessions, newest first."""
        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            rows = conn.execute(
                "SELECT * FROM activity_sessions ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    def get_activity_stats(self, session_id: str | None = None) -> dict[str, Any]:
        """Aggregate activity statistics, optionally filtered by session."""
        where = ""
        params: list[Any] = []
        if session_id:
            where = "WHERE session_id = ?"
            params = [session_id]

        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM activity_events {where}", params
            ).fetchone()[0]

            tool_end_where = (
                f"WHERE event_type = 'tool_end'{' AND session_id = ?' if session_id else ''}"
            )
            tool_end_params = [session_id] if session_id else []

            success_count = conn.execute(
                f"SELECT COUNT(*) FROM activity_events {tool_end_where} AND success = 1",
                tool_end_params,
            ).fetchone()[0]

            error_count = conn.execute(
                f"SELECT COUNT(*) FROM activity_events {tool_end_where} AND success = 0",
                tool_end_params,
            ).fetchone()[0]

            by_tool_rows = conn.execute(
                f"""
                SELECT
                    tool,
                    COUNT(*) AS call_count,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS error_count,
                    AVG(duration_ms) AS avg_duration_ms,
                    MAX(duration_ms) AS max_duration_ms
                FROM activity_events
                {tool_end_where}
                GROUP BY tool
                ORDER BY call_count DESC
                """,
                tool_end_params,
            ).fetchall()

            by_tool = [
                {
                    "tool": row["tool"],
                    "call_count": row["call_count"],
                    "error_count": row["error_count"],
                    "avg_duration_ms": round(row["avg_duration_ms"], 2)
                    if row["avg_duration_ms"]
                    else None,
                    "max_duration_ms": round(row["max_duration_ms"], 2)
                    if row["max_duration_ms"]
                    else None,
                }
                for row in by_tool_rows
            ]

            return {
                "total_events": total,
                "tool_calls_ok": success_count,
                "tool_calls_error": error_count,
                "success_rate": round(success_count / (success_count + error_count) * 100, 1)
                if (success_count + error_count) > 0
                else None,
                "by_tool": by_tool,
            }
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]
