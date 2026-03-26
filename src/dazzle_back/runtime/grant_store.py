"""
Runtime grant store for dynamic RBAC grants.

Manages the _grants and _grant_events tables on PostgreSQL, providing CRUD
operations with atomic status transitions and audit event logging.

Requires: psycopg >= 3.2
"""

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class GrantStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REVOKED = "revoked"


class GrantStore:
    """Grant store backed by PostgreSQL.

    All SQL uses native PostgreSQL types (UUID, TIMESTAMPTZ, JSONB) and %s
    placeholders. Connections must have autocommit=False (psycopg default).
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _grants (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                schema_name     TEXT NOT NULL,
                relation        TEXT NOT NULL,
                principal_id    UUID NOT NULL,
                scope_entity    TEXT NOT NULL,
                scope_id        UUID NOT NULL,
                status          TEXT NOT NULL CHECK (status IN (
                    'pending_approval', 'active', 'rejected',
                    'cancelled', 'expired', 'revoked'
                )),
                granted_by_id   UUID NOT NULL,
                approved_by_id  UUID,
                granted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                approved_at     TIMESTAMPTZ,
                expires_at      TIMESTAMPTZ,
                revoked_at      TIMESTAMPTZ,
                revoked_by_id   UUID
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_grants_lookup
            ON _grants (principal_id, relation, scope_id, status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_grants_expiry
            ON _grants (status, expires_at)
            WHERE status = 'active' AND expires_at IS NOT NULL
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _grant_events (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                grant_id    UUID NOT NULL REFERENCES _grants(id),
                event_type  TEXT NOT NULL CHECK (event_type IN (
                    'created', 'approved', 'rejected',
                    'cancelled', 'revoked', 'expired'
                )),
                actor_id    UUID NOT NULL,
                timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
                metadata    JSONB
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_grant_events_grant_id
            ON _grant_events (grant_id)
        """)
        self._conn.commit()

    def _record_event(
        self,
        grant_id: UUID,
        event_type: str,
        actor_id: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO _grant_events (id, grant_id, event_type, actor_id, timestamp, metadata)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                uuid4(),
                grant_id,
                event_type,
                actor_id,
                datetime.now(UTC),
                json.dumps(metadata) if metadata else None,
            ),
        )

    def _get_grant(self, grant_id: UUID) -> dict[str, Any]:
        row = self._conn.execute("SELECT * FROM _grants WHERE id = %s", (grant_id,)).fetchone()
        if row is None:
            raise ValueError(f"Grant {grant_id} not found")
        return dict(row)

    def create_grant(
        self,
        schema_name: str,
        relation: str,
        principal_id: UUID,
        scope_entity: str,
        scope_id: UUID,
        granted_by_id: UUID,
        approval_mode: str = "required",
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        grant_id = uuid4()
        now = datetime.now(UTC)

        if approval_mode == "required":
            status = GrantStatus.PENDING_APPROVAL
        else:
            status = GrantStatus.ACTIVE

        self._conn.execute(
            """INSERT INTO _grants
               (id, schema_name, relation, principal_id, scope_entity, scope_id,
                status, granted_by_id, granted_at, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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

    def _check_rowcount(self, rowcount: int, grant_id: UUID, event_type: str) -> None:
        """Raise ValueError if an atomic UPDATE matched zero rows."""
        if rowcount == 0:
            row = self._conn.execute(
                "SELECT status FROM _grants WHERE id = %s", (grant_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Grant {grant_id} not found")
            raise ValueError(f"Cannot {event_type} grant in status '{row['status']}'")

    def approve_grant(self, grant_id: UUID, approved_by_id: UUID) -> dict[str, Any]:
        now = datetime.now(UTC)
        cursor = self._conn.execute(
            """UPDATE _grants
               SET status = %s, approved_by_id = %s, approved_at = %s
               WHERE id = %s AND status = %s""",
            (GrantStatus.ACTIVE, approved_by_id, now, grant_id, GrantStatus.PENDING_APPROVAL),
        )
        self._check_rowcount(cursor.rowcount, grant_id, "approve")
        self._record_event(grant_id, "approved", approved_by_id)
        self._conn.commit()
        return self._get_grant(grant_id)

    def reject_grant(
        self, grant_id: UUID, rejected_by_id: UUID, reason: str | None = None
    ) -> dict[str, Any]:
        cursor = self._conn.execute(
            """UPDATE _grants SET status = %s
               WHERE id = %s AND status = %s""",
            (GrantStatus.REJECTED, grant_id, GrantStatus.PENDING_APPROVAL),
        )
        self._check_rowcount(cursor.rowcount, grant_id, "reject")
        metadata = {"reason": reason} if reason else None
        self._record_event(grant_id, "rejected", rejected_by_id, metadata)
        self._conn.commit()
        return self._get_grant(grant_id)

    def cancel_grant(self, grant_id: UUID, cancelled_by_id: UUID) -> dict[str, Any]:
        cursor = self._conn.execute(
            """UPDATE _grants SET status = %s
               WHERE id = %s AND status = %s""",
            (GrantStatus.CANCELLED, grant_id, GrantStatus.PENDING_APPROVAL),
        )
        self._check_rowcount(cursor.rowcount, grant_id, "cancel")
        self._record_event(grant_id, "cancelled", cancelled_by_id)
        self._conn.commit()
        return self._get_grant(grant_id)

    def revoke_grant(self, grant_id: UUID, revoked_by_id: UUID) -> dict[str, Any]:
        now = datetime.now(UTC)
        cursor = self._conn.execute(
            """UPDATE _grants
               SET status = %s, revoked_at = %s, revoked_by_id = %s
               WHERE id = %s AND status = %s""",
            (GrantStatus.REVOKED, now, revoked_by_id, grant_id, GrantStatus.ACTIVE),
        )
        self._check_rowcount(cursor.rowcount, grant_id, "revoke")
        self._record_event(grant_id, "revoked", revoked_by_id)
        self._conn.commit()
        return self._get_grant(grant_id)

    def has_active_grant(self, principal_id: UUID, relation: str, scope_id: UUID) -> bool:
        now = datetime.now(UTC)
        row = self._conn.execute(
            """SELECT 1 FROM _grants
               WHERE principal_id = %s AND relation = %s AND scope_id = %s
               AND status = %s
               AND (expires_at IS NULL OR expires_at > %s)
               LIMIT 1""",
            (principal_id, relation, scope_id, GrantStatus.ACTIVE, now),
        ).fetchone()
        return row is not None

    def list_grants(
        self,
        scope_entity: str | None = None,
        scope_id: UUID | None = None,
        principal_id: UUID | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if scope_entity is not None:
            clauses.append("scope_entity = %s")
            params.append(scope_entity)
        if scope_id is not None:
            clauses.append("scope_id = %s")
            params.append(scope_id)
        if principal_id is not None:
            clauses.append("principal_id = %s")
            params.append(principal_id)
        if status is not None:
            clauses.append("status = %s")
            params.append(status)
        where = " AND ".join(clauses) if clauses else "TRUE"
        # Column names in `where` are hardcoded literals above, not user input.
        rows = self._conn.execute(  # nosemgrep
            f"SELECT * FROM _grants WHERE {where} ORDER BY granted_at DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def expire_stale_grants(self) -> int:
        now = datetime.now(UTC)
        cursor = self._conn.execute(
            """UPDATE _grants SET status = %s
               WHERE status = %s AND expires_at IS NOT NULL AND expires_at <= %s
               RETURNING id""",
            (GrantStatus.EXPIRED, GrantStatus.ACTIVE, now),
        )
        expired = cursor.fetchall()
        system_actor = UUID(int=0)
        for row in expired:
            self._record_event(row["id"], "expired", system_actor)
        if expired:
            self._conn.commit()
        return len(expired)
