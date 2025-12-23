"""
Operations Database for Control Plane.

Separate database for operational data:
- Health check history
- Event logs (with retention)
- API call tracking
- Tenant-scoped analytics

This database is isolated from the application database for:
1. Security: Ops data access doesn't grant app data access
2. Performance: Heavy analytics queries don't impact app
3. Compliance: Different retention policies
4. Portability: Ops data can be backed up/migrated independently
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4


class HealthStatus(str, Enum):
    """Health check status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ComponentType(str, Enum):
    """System component types."""

    DATABASE = "database"
    EVENT_BUS = "event_bus"
    CACHE = "cache"
    EXTERNAL_API = "external_api"
    BACKGROUND_WORKER = "background_worker"
    WEBSOCKET = "websocket"
    FILE_STORAGE = "file_storage"


@dataclass
class HealthCheckRecord:
    """Health check result record."""

    id: str
    component: str
    component_type: ComponentType
    status: HealthStatus
    latency_ms: float | None
    message: str | None
    metadata: dict[str, Any]
    checked_at: datetime
    tenant_id: str | None = None


@dataclass
class ApiCallRecord:
    """External API call tracking record."""

    id: str
    service_name: str
    endpoint: str
    method: str
    status_code: int | None
    latency_ms: float
    request_size_bytes: int | None
    response_size_bytes: int | None
    error_message: str | None
    cost_cents: float | None  # For metered APIs
    metadata: dict[str, Any]
    called_at: datetime
    tenant_id: str | None = None


@dataclass
class AnalyticsEvent:
    """Tenant-scoped analytics event."""

    id: str
    tenant_id: str
    event_type: str  # page_view, action, conversion, etc.
    event_name: str
    user_id: str | None
    session_id: str | None
    properties: dict[str, Any]
    recorded_at: datetime


@dataclass
class RetentionConfig:
    """Data retention configuration."""

    health_checks_days: int = 30
    api_calls_days: int = 90
    analytics_days: int = 730  # 2 years - UK GDPR default
    events_days: int = 365

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetentionConfig:
        return cls(
            health_checks_days=data.get("health_checks_days", 30),
            api_calls_days=data.get("api_calls_days", 90),
            analytics_days=data.get("analytics_days", 730),
            events_days=data.get("events_days", 365),
        )


@dataclass
class OpsCredentials:
    """Ops database credentials (separate from app)."""

    username: str = "ops_admin"
    password_hash: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_login: datetime | None = None

    @classmethod
    def create(cls, username: str, password: str) -> OpsCredentials:
        """Create credentials with hashed password."""
        import hashlib

        # Simple hash for now - in production use bcrypt/argon2
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return cls(username=username, password_hash=password_hash)

    def verify(self, password: str) -> bool:
        """Verify password against hash."""
        import hashlib

        return self.password_hash == hashlib.sha256(password.encode()).hexdigest()


class OpsDatabase:
    """
    Operations database manager.

    Manages a separate SQLite database for operational data with:
    - Automatic schema creation
    - Data retention enforcement
    - Credential management
    """

    SCHEMA_VERSION = 1

    def __init__(
        self,
        db_path: Path | None = None,
        retention: RetentionConfig | None = None,
    ):
        """
        Initialize ops database.

        Args:
            db_path: Path to database file. Defaults to .dazzle/ops.db
            retention: Data retention configuration
        """
        self.db_path = db_path or Path(".dazzle/ops.db")
        self.retention = retention or RetentionConfig()
        self._ensure_directory()
        self._init_schema()

    def _ensure_directory(self) -> None:
        """Ensure database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Get database connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self.connection() as conn:
            # Schema version tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _ops_schema (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)

            # Check current version
            cursor = conn.execute("SELECT MAX(version) FROM _ops_schema")
            current_version = cursor.fetchone()[0] or 0

            if current_version < self.SCHEMA_VERSION:
                self._apply_migrations(conn, current_version)

    def _apply_migrations(self, conn: sqlite3.Connection, from_version: int) -> None:
        """Apply schema migrations."""
        if from_version < 1:
            # Initial schema
            conn.executescript("""
                -- Ops credentials (separate auth)
                CREATE TABLE IF NOT EXISTS ops_credentials (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login TEXT
                );

                -- Health checks
                CREATE TABLE IF NOT EXISTS health_checks (
                    id TEXT PRIMARY KEY,
                    component TEXT NOT NULL,
                    component_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    latency_ms REAL,
                    message TEXT,
                    metadata TEXT,
                    checked_at TEXT NOT NULL,
                    tenant_id TEXT,

                    -- Indexes for common queries
                    CONSTRAINT fk_status CHECK (status IN ('healthy', 'degraded', 'unhealthy', 'unknown'))
                );
                CREATE INDEX IF NOT EXISTS idx_health_component ON health_checks(component, checked_at DESC);
                CREATE INDEX IF NOT EXISTS idx_health_status ON health_checks(status, checked_at DESC);
                CREATE INDEX IF NOT EXISTS idx_health_tenant ON health_checks(tenant_id, checked_at DESC);

                -- API call tracking
                CREATE TABLE IF NOT EXISTS api_calls (
                    id TEXT PRIMARY KEY,
                    service_name TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER,
                    latency_ms REAL NOT NULL,
                    request_size_bytes INTEGER,
                    response_size_bytes INTEGER,
                    error_message TEXT,
                    cost_cents REAL,
                    metadata TEXT,
                    called_at TEXT NOT NULL,
                    tenant_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_api_service ON api_calls(service_name, called_at DESC);
                CREATE INDEX IF NOT EXISTS idx_api_tenant ON api_calls(tenant_id, called_at DESC);
                CREATE INDEX IF NOT EXISTS idx_api_errors ON api_calls(status_code, called_at DESC)
                    WHERE status_code >= 400;

                -- Analytics events (tenant-scoped)
                CREATE TABLE IF NOT EXISTS analytics_events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    user_id TEXT,
                    session_id TEXT,
                    properties TEXT,
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_analytics_tenant ON analytics_events(tenant_id, recorded_at DESC);
                CREATE INDEX IF NOT EXISTS idx_analytics_type ON analytics_events(tenant_id, event_type, recorded_at DESC);
                CREATE INDEX IF NOT EXISTS idx_analytics_user ON analytics_events(tenant_id, user_id, recorded_at DESC);

                -- Event log (for Event Explorer)
                CREATE TABLE IF NOT EXISTS event_log (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    entity_name TEXT,
                    entity_id TEXT,
                    payload TEXT,
                    correlation_id TEXT,
                    causation_id TEXT,
                    user_id TEXT,
                    tenant_id TEXT,
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_event_type ON event_log(event_type, recorded_at DESC);
                CREATE INDEX IF NOT EXISTS idx_event_entity ON event_log(entity_name, entity_id, recorded_at DESC);
                CREATE INDEX IF NOT EXISTS idx_event_correlation ON event_log(correlation_id);
                CREATE INDEX IF NOT EXISTS idx_event_tenant ON event_log(tenant_id, recorded_at DESC);

                -- Retention config
                CREATE TABLE IF NOT EXISTS retention_config (
                    key TEXT PRIMARY KEY,
                    value_days INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # Record migration
            conn.execute(
                "INSERT INTO _ops_schema (version, applied_at) VALUES (?, ?)",
                (1, datetime.utcnow().isoformat()),
            )

    # =========================================================================
    # Credential Management
    # =========================================================================

    def create_credentials(self, username: str, password: str) -> OpsCredentials:
        """Create ops admin credentials."""
        creds = OpsCredentials.create(username, password)
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_credentials
                (id, username, password_hash, created_at, last_login)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    creds.username,
                    creds.password_hash,
                    creds.created_at.isoformat(),
                    None,
                ),
            )
        return creds

    def verify_credentials(self, username: str, password: str) -> bool:
        """Verify ops credentials."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT password_hash FROM ops_credentials WHERE username = ?",
                (username,),
            )
            row = cursor.fetchone()
            if not row:
                return False

            import hashlib

            expected = hashlib.sha256(password.encode()).hexdigest()
            if row["password_hash"] == expected:
                # Update last login
                conn.execute(
                    "UPDATE ops_credentials SET last_login = ? WHERE username = ?",
                    (datetime.utcnow().isoformat(), username),
                )
                return True
            return False

    def has_credentials(self) -> bool:
        """Check if any ops credentials exist."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM ops_credentials")
            row = cursor.fetchone()
            return bool(row[0] > 0) if row else False

    # =========================================================================
    # Health Checks
    # =========================================================================

    def record_health_check(self, record: HealthCheckRecord) -> None:
        """Record a health check result."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO health_checks
                (id, component, component_type, status, latency_ms, message, metadata, checked_at, tenant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.component,
                    record.component_type.value,
                    record.status.value,
                    record.latency_ms,
                    record.message,
                    json.dumps(record.metadata) if record.metadata else None,
                    record.checked_at.isoformat(),
                    record.tenant_id,
                ),
            )

    def get_latest_health(self, component: str | None = None) -> list[HealthCheckRecord]:
        """Get latest health check for each component."""
        with self.connection() as conn:
            if component:
                cursor = conn.execute(
                    """
                    SELECT * FROM health_checks
                    WHERE component = ?
                    ORDER BY checked_at DESC
                    LIMIT 1
                    """,
                    (component,),
                )
            else:
                cursor = conn.execute("""
                    SELECT h1.* FROM health_checks h1
                    INNER JOIN (
                        SELECT component, MAX(checked_at) as max_checked
                        FROM health_checks
                        GROUP BY component
                    ) h2 ON h1.component = h2.component AND h1.checked_at = h2.max_checked
                """)

            return [self._row_to_health_check(row) for row in cursor.fetchall()]

    def get_health_history(
        self,
        component: str,
        hours: int = 24,
    ) -> list[HealthCheckRecord]:
        """Get health check history for a component."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM health_checks
                WHERE component = ? AND checked_at >= ?
                ORDER BY checked_at DESC
                """,
                (component, cutoff),
            )
            return [self._row_to_health_check(row) for row in cursor.fetchall()]

    def _row_to_health_check(self, row: sqlite3.Row) -> HealthCheckRecord:
        """Convert database row to HealthCheckRecord."""
        return HealthCheckRecord(
            id=row["id"],
            component=row["component"],
            component_type=ComponentType(row["component_type"]),
            status=HealthStatus(row["status"]),
            latency_ms=row["latency_ms"],
            message=row["message"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            checked_at=datetime.fromisoformat(row["checked_at"]),
            tenant_id=row["tenant_id"],
        )

    # =========================================================================
    # API Call Tracking
    # =========================================================================

    def record_api_call(self, record: ApiCallRecord) -> None:
        """Record an external API call."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO api_calls
                (id, service_name, endpoint, method, status_code, latency_ms,
                 request_size_bytes, response_size_bytes, error_message, cost_cents,
                 metadata, called_at, tenant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.service_name,
                    record.endpoint,
                    record.method,
                    record.status_code,
                    record.latency_ms,
                    record.request_size_bytes,
                    record.response_size_bytes,
                    record.error_message,
                    record.cost_cents,
                    json.dumps(record.metadata) if record.metadata else None,
                    record.called_at.isoformat(),
                    record.tenant_id,
                ),
            )

    def get_api_call_stats(
        self,
        service_name: str | None = None,
        hours: int = 24,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Get API call statistics."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        with self.connection() as conn:
            # Build query based on filters
            where_clauses = ["called_at >= ?"]
            params: list[Any] = [cutoff]

            if service_name:
                where_clauses.append("service_name = ?")
                params.append(service_name)

            if tenant_id:
                where_clauses.append("tenant_id = ?")
                params.append(tenant_id)

            where_sql = " AND ".join(where_clauses)

            # Get aggregate stats
            cursor = conn.execute(
                f"""
                SELECT
                    service_name,
                    COUNT(*) as total_calls,
                    AVG(latency_ms) as avg_latency,
                    MAX(latency_ms) as max_latency,
                    SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as error_count,
                    SUM(COALESCE(cost_cents, 0)) as total_cost_cents
                FROM api_calls
                WHERE {where_sql}
                GROUP BY service_name
                """,
                params,
            )

            stats = {}
            for row in cursor.fetchall():
                stats[row["service_name"]] = {
                    "total_calls": row["total_calls"],
                    "avg_latency_ms": round(row["avg_latency"], 2) if row["avg_latency"] else 0,
                    "max_latency_ms": row["max_latency"],
                    "error_count": row["error_count"],
                    "error_rate": round(row["error_count"] / row["total_calls"] * 100, 2),
                    "total_cost_cents": row["total_cost_cents"] or 0,
                }

            return stats

    # =========================================================================
    # Analytics (Tenant-Scoped)
    # =========================================================================

    def record_analytics_event(self, event: AnalyticsEvent) -> None:
        """Record a tenant-scoped analytics event."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO analytics_events
                (id, tenant_id, event_type, event_name, user_id, session_id, properties, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.tenant_id,
                    event.event_type,
                    event.event_name,
                    event.user_id,
                    event.session_id,
                    json.dumps(event.properties) if event.properties else None,
                    event.recorded_at.isoformat(),
                ),
            )

    def get_analytics_summary(
        self,
        tenant_id: str,
        event_type: str | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """Get analytics summary for a tenant."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        with self.connection() as conn:
            # Event counts by type
            type_filter = "AND event_type = ?" if event_type else ""
            params: list[Any] = [tenant_id, cutoff]
            if event_type:
                params.append(event_type)

            cursor = conn.execute(
                f"""
                SELECT event_type, event_name, COUNT(*) as count
                FROM analytics_events
                WHERE tenant_id = ? AND recorded_at >= ? {type_filter}
                GROUP BY event_type, event_name
                ORDER BY count DESC
                """,
                params,
            )

            events_by_type: dict[str, dict[str, int]] = {}
            for row in cursor.fetchall():
                event_type_key = row["event_type"]
                if event_type_key not in events_by_type:
                    events_by_type[event_type_key] = {}
                events_by_type[event_type_key][row["event_name"]] = row["count"]

            # Unique users
            cursor = conn.execute(
                f"""
                SELECT COUNT(DISTINCT user_id) as unique_users,
                       COUNT(DISTINCT session_id) as unique_sessions
                FROM analytics_events
                WHERE tenant_id = ? AND recorded_at >= ? {type_filter}
                """,
                params,
            )
            row = cursor.fetchone()

            return {
                "tenant_id": tenant_id,
                "period_days": days,
                "events_by_type": events_by_type,
                "unique_users": row["unique_users"] if row else 0,
                "unique_sessions": row["unique_sessions"] if row else 0,
            }

    # =========================================================================
    # Event Log
    # =========================================================================

    def record_event(
        self,
        event_type: str,
        entity_name: str | None = None,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> str:
        """Record an event to the log."""
        event_id = str(uuid4())
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO event_log
                (id, event_type, entity_name, entity_id, payload,
                 correlation_id, causation_id, user_id, tenant_id, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event_type,
                    entity_name,
                    entity_id,
                    json.dumps(payload) if payload else None,
                    correlation_id,
                    causation_id,
                    user_id,
                    tenant_id,
                    datetime.utcnow().isoformat(),
                ),
            )
        return event_id

    def get_events(
        self,
        entity_name: str | None = None,
        entity_id: str | None = None,
        event_type: str | None = None,
        correlation_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query events from the log."""
        where_clauses = []
        params: list[Any] = []

        if entity_name:
            where_clauses.append("entity_name = ?")
            params.append(entity_name)
        if entity_id:
            where_clauses.append("entity_id = ?")
            params.append(entity_id)
        if event_type:
            where_clauses.append("event_type = ?")
            params.append(event_type)
        if correlation_id:
            where_clauses.append("correlation_id = ?")
            params.append(correlation_id)
        if tenant_id:
            where_clauses.append("tenant_id = ?")
            params.append(tenant_id)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        with self.connection() as conn:
            cursor = conn.execute(
                f"""
                SELECT * FROM event_log
                WHERE {where_sql}
                ORDER BY recorded_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            )

            return [
                {
                    "id": row["id"],
                    "event_type": row["event_type"],
                    "entity_name": row["entity_name"],
                    "entity_id": row["entity_id"],
                    "payload": json.loads(row["payload"]) if row["payload"] else None,
                    "correlation_id": row["correlation_id"],
                    "causation_id": row["causation_id"],
                    "user_id": row["user_id"],
                    "tenant_id": row["tenant_id"],
                    "recorded_at": row["recorded_at"],
                }
                for row in cursor.fetchall()
            ]

    # =========================================================================
    # Retention Enforcement
    # =========================================================================

    def enforce_retention(self) -> dict[str, int]:
        """Delete data older than retention period. Returns counts of deleted rows."""
        deleted = {}

        with self.connection() as conn:
            # Health checks
            cutoff = (
                datetime.utcnow() - timedelta(days=self.retention.health_checks_days)
            ).isoformat()
            cursor = conn.execute("DELETE FROM health_checks WHERE checked_at < ?", (cutoff,))
            deleted["health_checks"] = cursor.rowcount

            # API calls
            cutoff = (datetime.utcnow() - timedelta(days=self.retention.api_calls_days)).isoformat()
            cursor = conn.execute("DELETE FROM api_calls WHERE called_at < ?", (cutoff,))
            deleted["api_calls"] = cursor.rowcount

            # Analytics
            cutoff = (datetime.utcnow() - timedelta(days=self.retention.analytics_days)).isoformat()
            cursor = conn.execute("DELETE FROM analytics_events WHERE recorded_at < ?", (cutoff,))
            deleted["analytics_events"] = cursor.rowcount

            # Events
            cutoff = (datetime.utcnow() - timedelta(days=self.retention.events_days)).isoformat()
            cursor = conn.execute("DELETE FROM event_log WHERE recorded_at < ?", (cutoff,))
            deleted["event_log"] = cursor.rowcount

        return deleted

    def get_retention_config(self) -> RetentionConfig:
        """Get current retention configuration."""
        return self.retention

    def set_retention_config(self, config: RetentionConfig) -> None:
        """Update retention configuration."""
        self.retention = config
        with self.connection() as conn:
            now = datetime.utcnow().isoformat()
            for key, value in [
                ("health_checks_days", config.health_checks_days),
                ("api_calls_days", config.api_calls_days),
                ("analytics_days", config.analytics_days),
                ("events_days", config.events_days),
            ]:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO retention_config (key, value_days, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (key, value, now),
                )
