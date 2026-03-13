"""
Runtime grant store for dynamic RBAC grants.

Manages the _grants and _grant_events tables, providing CRUD operations
with status transitions and audit event logging.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


class GrantStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REVOKED = "revoked"


class GrantStore:
    """Synchronous grant store backed by SQLite."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _grants (
                id TEXT PRIMARY KEY,
                schema_name TEXT NOT NULL,
                relation TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                scope_entity TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                status TEXT NOT NULL,
                granted_by_id TEXT NOT NULL,
                approved_by_id TEXT,
                granted_at TEXT NOT NULL,
                approved_at TEXT,
                expires_at TEXT,
                revoked_at TEXT,
                revoked_by_id TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_grants_lookup
            ON _grants (principal_id, relation, scope_id, status)
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _grant_events (
                id TEXT PRIMARY KEY,
                grant_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata TEXT,
                FOREIGN KEY (grant_id) REFERENCES _grants(id)
            )
        """)
        self._conn.commit()

    def _record_event(
        self,
        grant_id: str,
        event_type: str,
        actor_id: str,
        metadata: dict | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO _grant_events (id, grant_id, event_type, actor_id, timestamp, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()),
                grant_id,
                event_type,
                actor_id,
                datetime.now(UTC).isoformat(),
                json.dumps(metadata) if metadata else None,
            ),
        )

    def _get_grant(self, grant_id: str) -> dict:
        row = self._conn.execute("SELECT * FROM _grants WHERE id = ?", (grant_id,)).fetchone()
        if row is None:
            raise ValueError(f"Grant {grant_id} not found")
        return dict(row)

    def create_grant(
        self,
        schema_name: str,
        relation: str,
        principal_id: str,
        scope_entity: str,
        scope_id: str,
        granted_by_id: str,
        approval_mode: str = "required",
        expires_at: str | None = None,
    ) -> dict:
        grant_id = str(uuid4())
        now = datetime.now(UTC).isoformat()

        if approval_mode == "required":
            status = GrantStatus.PENDING_APPROVAL
        else:
            status = GrantStatus.ACTIVE

        self._conn.execute(
            """INSERT INTO _grants
               (id, schema_name, relation, principal_id, scope_entity, scope_id,
                status, granted_by_id, granted_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                grant_id,
                schema_name,
                relation,
                principal_id,
                scope_entity,
                scope_id,
                status,
                granted_by_id,
                now,
                expires_at,
            ),
        )
        self._record_event(grant_id, "created", granted_by_id)
        self._conn.commit()
        return self._get_grant(grant_id)

    def approve_grant(self, grant_id: str, approved_by_id: str) -> dict:
        grant = self._get_grant(grant_id)
        if grant["status"] != GrantStatus.PENDING_APPROVAL:
            raise ValueError(f"Cannot approve grant in status '{grant['status']}'")
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """UPDATE _grants
               SET status = ?, approved_by_id = ?, approved_at = ?
               WHERE id = ?""",
            (GrantStatus.ACTIVE, approved_by_id, now, grant_id),
        )
        self._record_event(grant_id, "approved", approved_by_id)
        self._conn.commit()
        return self._get_grant(grant_id)

    def reject_grant(self, grant_id: str, rejected_by_id: str, reason: str | None = None) -> dict:
        grant = self._get_grant(grant_id)
        if grant["status"] != GrantStatus.PENDING_APPROVAL:
            raise ValueError(f"Cannot reject grant in status '{grant['status']}'")
        self._conn.execute(
            "UPDATE _grants SET status = ? WHERE id = ?",
            (GrantStatus.REJECTED, grant_id),
        )
        metadata = {"reason": reason} if reason else None
        self._record_event(grant_id, "rejected", rejected_by_id, metadata)
        self._conn.commit()
        return self._get_grant(grant_id)

    def revoke_grant(self, grant_id: str, revoked_by_id: str) -> dict:
        grant = self._get_grant(grant_id)
        if grant["status"] != GrantStatus.ACTIVE:
            raise ValueError(f"Cannot revoke grant in status '{grant['status']}'")
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """UPDATE _grants
               SET status = ?, revoked_at = ?, revoked_by_id = ?
               WHERE id = ?""",
            (GrantStatus.REVOKED, now, revoked_by_id, grant_id),
        )
        self._record_event(grant_id, "revoked", revoked_by_id)
        self._conn.commit()
        return self._get_grant(grant_id)

    def has_active_grant(self, principal_id: str, relation: str, scope_id: str) -> bool:
        now = datetime.now(UTC).isoformat()
        row = self._conn.execute(
            """SELECT 1 FROM _grants
               WHERE principal_id = ? AND relation = ? AND scope_id = ?
               AND status = ?
               AND (expires_at IS NULL OR expires_at > ?)
               LIMIT 1""",
            (principal_id, relation, scope_id, GrantStatus.ACTIVE, now),
        ).fetchone()
        return row is not None

    def list_grants(
        self,
        scope_entity: str | None = None,
        scope_id: str | None = None,
        principal_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        # Fully static SQL — no string concatenation anywhere.
        # Each optional filter uses (? IS NULL OR col = ?) so the query text
        # never varies; passing NULL for a parameter means "no filter" for that
        # column.  All values flow through bound parameters only.
        rows = self._conn.execute(
            """SELECT * FROM _grants
               WHERE (? IS NULL OR scope_entity = ?)
                 AND (? IS NULL OR scope_id = ?)
                 AND (? IS NULL OR principal_id = ?)
                 AND (? IS NULL OR status = ?)
               ORDER BY granted_at DESC""",
            (
                scope_entity,
                scope_entity,
                scope_id,
                scope_id,
                principal_id,
                principal_id,
                status,
                status,
            ),
        ).fetchall()
        return [dict(r) for r in rows]

    def expire_stale_grants(self) -> int:
        now = datetime.now(UTC).isoformat()
        cursor = self._conn.execute(
            """SELECT id FROM _grants
               WHERE status = ? AND expires_at IS NOT NULL AND expires_at <= ?""",
            (GrantStatus.ACTIVE, now),
        )
        expired_ids = [row[0] for row in cursor.fetchall()]
        for gid in expired_ids:
            self._conn.execute(
                "UPDATE _grants SET status = ? WHERE id = ?",
                (GrantStatus.EXPIRED, gid),
            )
            self._record_event(gid, "expired", "system")
        if expired_ids:
            self._conn.commit()
        return len(expired_ids)
