"""
Runtime grant store for dynamic RBAC grants.

Manages the _grants and _grant_events tables on PostgreSQL, providing CRUD
operations with atomic status transitions and audit event logging.

Requires: psycopg >= 3.2
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


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
