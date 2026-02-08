"""
Version manager for DSL process migrations.

This module provides version tracking and migration management for
ProcessSpec workflows, enabling safe deployments with hard boundaries
between DSL versions.

Usage:
    version_manager = VersionManager(adapter, db_path)
    await version_manager.initialize()

    # Deploy a new version
    await version_manager.deploy_version(
        "v20250115_001",
        "abc123",
        {"app_name": "my_app"}
    )

    # Start migration to drain old processes
    remaining = await version_manager.start_migration("v1", "v2")
    print(f"{remaining} processes still running")

    # Monitor migration progress
    status = await version_manager.check_migration_status(migration_id)
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite

if TYPE_CHECKING:
    from .adapter import ProcessAdapter

logger = logging.getLogger(__name__)


@dataclass
class VersionInfo:
    """Information about a DSL version."""

    version_id: str
    deployed_at: datetime
    dsl_hash: str
    manifest: dict[str, Any]
    status: str  # active, draining, archived


@dataclass
class MigrationInfo:
    """Information about a version migration."""

    id: int
    from_version: str | None
    to_version: str
    started_at: datetime
    completed_at: datetime | None
    status: str  # in_progress, completed, failed, rolled_back
    runs_drained: int
    runs_remaining: int


@dataclass
class MigrationStatus:
    """Current status of an in-progress migration."""

    status: str
    from_version: str | None = None
    to_version: str | None = None
    runs_remaining: int = 0
    runs_drained: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


class VersionManager:
    """
    Manages DSL version lifecycle and migrations.

    Responsibilities:
    - Track deployed DSL versions with hashes
    - Manage version transitions (draining, activation)
    - Monitor running processes during migrations
    - Support rollback when issues arise
    """

    def __init__(
        self,
        db_path: str | Path,
        adapter: ProcessAdapter | None = None,
        database_url: str | None = None,
    ):
        """
        Initialize version manager.

        Args:
            db_path: Path to SQLite database
            adapter: Optional ProcessAdapter for process queries
            database_url: PostgreSQL connection URL (takes precedence over db_path)
        """
        self._db_path = Path(db_path)
        self._adapter = adapter
        self._database_url = database_url
        self._use_postgres = bool(database_url)
        self._current_version: str | None = None
        self._initialized = False

    async def _connect(self) -> Any:
        """Get a database connection for the configured backend."""
        if self._use_postgres:
            import asyncpg

            pg_url = self._database_url
            if pg_url and pg_url.startswith("postgres://"):
                pg_url = pg_url.replace("postgres://", "postgresql://", 1)
            return await asyncpg.connect(pg_url)
        else:
            return await aiosqlite.connect(self._db_path)

    async def initialize(self) -> None:
        """Initialize database tables if needed."""
        if self._initialized:
            return

        conn = await self._connect()
        try:
            if self._use_postgres:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS dsl_versions (
                        version_id TEXT PRIMARY KEY,
                        deployed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        dsl_hash TEXT NOT NULL,
                        manifest_json TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active'
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS version_migrations (
                        id SERIAL PRIMARY KEY,
                        from_version TEXT REFERENCES dsl_versions(version_id),
                        to_version TEXT NOT NULL,
                        started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        status TEXT NOT NULL DEFAULT 'in_progress',
                        runs_drained INTEGER DEFAULT 0,
                        runs_remaining INTEGER DEFAULT 0
                    )
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS process_runs (
                        run_id TEXT PRIMARY KEY,
                        process_name TEXT NOT NULL,
                        process_version TEXT NOT NULL DEFAULT 'v1',
                        dsl_version TEXT NOT NULL DEFAULT '0.1',
                        status TEXT NOT NULL DEFAULT 'pending',
                        current_step TEXT,
                        inputs TEXT NOT NULL DEFAULT '{}',
                        context TEXT NOT NULL DEFAULT '{}',
                        outputs TEXT,
                        error TEXT,
                        idempotency_key TEXT UNIQUE,
                        started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP
                    )
                    """
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_versions_status ON dsl_versions(status)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_versions_deployed ON dsl_versions(deployed_at DESC)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_migrations_status ON version_migrations(status)"
                )
            else:
                await conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS dsl_versions (
                        version_id TEXT PRIMARY KEY,
                        deployed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        dsl_hash TEXT NOT NULL,
                        manifest_json JSON NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active'
                    );

                    CREATE TABLE IF NOT EXISTS version_migrations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        from_version TEXT REFERENCES dsl_versions(version_id),
                        to_version TEXT NOT NULL,
                        started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        status TEXT NOT NULL DEFAULT 'in_progress',
                        runs_drained INTEGER DEFAULT 0,
                        runs_remaining INTEGER DEFAULT 0
                    );

                    -- Process runs table for migration queries
                    -- (May already exist from LiteProcessAdapter)
                    CREATE TABLE IF NOT EXISTS process_runs (
                        run_id TEXT PRIMARY KEY,
                        process_name TEXT NOT NULL,
                        process_version TEXT NOT NULL DEFAULT 'v1',
                        dsl_version TEXT NOT NULL DEFAULT '0.1',
                        status TEXT NOT NULL DEFAULT 'pending',
                        current_step TEXT,
                        inputs JSON NOT NULL DEFAULT '{}',
                        context JSON NOT NULL DEFAULT '{}',
                        outputs JSON,
                        error TEXT,
                        idempotency_key TEXT UNIQUE,
                        started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP
                    );

                    CREATE INDEX IF NOT EXISTS idx_versions_status
                        ON dsl_versions(status);
                    CREATE INDEX IF NOT EXISTS idx_versions_deployed
                        ON dsl_versions(deployed_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_migrations_status
                        ON version_migrations(status);
                    CREATE INDEX IF NOT EXISTS idx_runs_dsl_version
                        ON process_runs(dsl_version) WHERE dsl_version IS NOT NULL;
                    """
                )
                await conn.commit()
        finally:
            await conn.close()

        self._initialized = True
        logger.debug("VersionManager initialized")

    async def get_current_version(self) -> str | None:
        """Get the currently active DSL version."""
        await self.initialize()

        conn = await self._connect()
        try:
            if self._use_postgres:
                row = await conn.fetchrow(
                    """
                    SELECT version_id FROM dsl_versions
                    WHERE status = 'active'
                    ORDER BY deployed_at DESC
                    LIMIT 1
                    """
                )
                return row["version_id"] if row else None
            else:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    """
                    SELECT version_id FROM dsl_versions
                    WHERE status = 'active'
                    ORDER BY deployed_at DESC
                    LIMIT 1
                    """
                ) as cursor:
                    row = await cursor.fetchone()
                    return row["version_id"] if row else None
        finally:
            await conn.close()

    async def get_version(self, version_id: str) -> VersionInfo | None:
        """Get information about a specific version."""
        await self.initialize()

        conn = await self._connect()
        try:
            if self._use_postgres:
                row = await conn.fetchrow(
                    "SELECT * FROM dsl_versions WHERE version_id = $1",
                    version_id,
                )
            else:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM dsl_versions WHERE version_id = ?",
                    (version_id,),
                ) as cursor:
                    row = await cursor.fetchone()

            if not row:
                return None

            deployed_at = row["deployed_at"]
            if isinstance(deployed_at, str):
                deployed_at = datetime.fromisoformat(deployed_at)

            return VersionInfo(
                version_id=row["version_id"],
                deployed_at=deployed_at,
                dsl_hash=row["dsl_hash"],
                manifest=json.loads(row["manifest_json"]),
                status=row["status"],
            )
        finally:
            await conn.close()

    async def list_versions(
        self,
        status: str | None = None,
        limit: int = 10,
    ) -> list[VersionInfo]:
        """List deployed versions with optional status filter."""
        await self.initialize()

        conn = await self._connect()
        try:
            if self._use_postgres:
                if status:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM dsl_versions
                        WHERE status = $1
                        ORDER BY deployed_at DESC
                        LIMIT $2
                        """,
                        status,
                        limit,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM dsl_versions
                        ORDER BY deployed_at DESC
                        LIMIT $1
                        """,
                        limit,
                    )
            else:
                conn.row_factory = aiosqlite.Row

                if status:
                    query = """
                        SELECT * FROM dsl_versions
                        WHERE status = ?
                        ORDER BY deployed_at DESC
                        LIMIT ?
                    """
                    params: tuple[str | int, ...] = (status, limit)
                else:
                    query = """
                        SELECT * FROM dsl_versions
                        ORDER BY deployed_at DESC
                        LIMIT ?
                    """
                    params = (limit,)

                async with conn.execute(query, params) as cursor:
                    rows = await cursor.fetchall()

            results = []
            for row in rows:
                deployed_at = row["deployed_at"]
                if isinstance(deployed_at, str):
                    deployed_at = datetime.fromisoformat(deployed_at)
                results.append(
                    VersionInfo(
                        version_id=row["version_id"],
                        deployed_at=deployed_at,
                        dsl_hash=row["dsl_hash"],
                        manifest=json.loads(row["manifest_json"]),
                        status=row["status"],
                    )
                )
            return results
        finally:
            await conn.close()

    @staticmethod
    def compute_version_hash(dsl_files: list[Path]) -> str:
        """
        Compute deterministic hash of DSL files.

        Args:
            dsl_files: List of DSL file paths

        Returns:
            16-character hex hash of file contents
        """
        hasher = sha256()
        for path in sorted(dsl_files):
            if path.exists():
                content = path.read_text()
                hasher.update(f"{path.name}:{content}".encode())
        return hasher.hexdigest()[:16]

    async def deploy_version(
        self,
        version_id: str,
        dsl_hash: str,
        manifest: dict[str, Any],
    ) -> None:
        """
        Deploy a new DSL version.

        Args:
            version_id: Unique version identifier (e.g., "v20250115_001_abc123")
            dsl_hash: Hash of DSL file contents
            manifest: Project manifest data
        """
        await self.initialize()

        conn = await self._connect()
        try:
            if self._use_postgres:
                row = await conn.fetchrow(
                    "SELECT 1 FROM dsl_versions WHERE version_id = $1",
                    version_id,
                )
                if row:
                    raise ValueError(f"Version {version_id} already exists")

                await conn.execute(
                    """
                    INSERT INTO dsl_versions (version_id, dsl_hash, manifest_json, status)
                    VALUES ($1, $2, $3, 'active')
                    """,
                    version_id,
                    dsl_hash,
                    json.dumps(manifest),
                )
            else:
                async with conn.execute(
                    "SELECT 1 FROM dsl_versions WHERE version_id = ?",
                    (version_id,),
                ) as cursor:
                    if await cursor.fetchone():
                        raise ValueError(f"Version {version_id} already exists")

                await conn.execute(
                    """
                    INSERT INTO dsl_versions (version_id, dsl_hash, manifest_json, status)
                    VALUES (?, ?, ?, 'active')
                    """,
                    (version_id, dsl_hash, json.dumps(manifest)),
                )
                await conn.commit()
        finally:
            await conn.close()

        self._current_version = version_id
        logger.info(f"Deployed version: {version_id}")

    async def start_migration(
        self,
        from_version: str,
        to_version: str,
    ) -> int:
        """
        Start a migration, marking old version as draining.

        Args:
            from_version: Version being migrated away from
            to_version: Version being migrated to

        Returns:
            Number of running processes that need to drain
        """
        await self.initialize()

        conn = await self._connect()
        try:
            if self._use_postgres:
                row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) as count FROM process_runs
                    WHERE dsl_version = $1 AND status IN ('pending', 'running', 'suspended', 'waiting')
                    """,
                    from_version,
                )
                runs_remaining = row["count"] if row else 0

                await conn.execute(
                    "UPDATE dsl_versions SET status = 'draining' WHERE version_id = $1",
                    from_version,
                )

                await conn.execute(
                    """
                    INSERT INTO version_migrations
                    (from_version, to_version, runs_remaining, status)
                    VALUES ($1, $2, $3, 'in_progress')
                    """,
                    from_version,
                    to_version,
                    runs_remaining,
                )
            else:
                conn.row_factory = aiosqlite.Row

                async with conn.execute(
                    """
                    SELECT COUNT(*) as count FROM process_runs
                    WHERE dsl_version = ? AND status IN ('pending', 'running', 'suspended', 'waiting')
                    """,
                    (from_version,),
                ) as cursor:
                    row = await cursor.fetchone()
                    runs_remaining = row["count"] if row else 0

                await conn.execute(
                    "UPDATE dsl_versions SET status = 'draining' WHERE version_id = ?",
                    (from_version,),
                )

                await conn.execute(
                    """
                    INSERT INTO version_migrations
                    (from_version, to_version, runs_remaining, status)
                    VALUES (?, ?, ?, 'in_progress')
                    """,
                    (from_version, to_version, runs_remaining),
                )
                await conn.commit()
        finally:
            await conn.close()

        logger.info(
            f"Started migration: {from_version} -> {to_version}, "
            f"{runs_remaining} processes to drain"
        )
        return runs_remaining

    async def get_active_migrations(self) -> list[MigrationInfo]:
        """Get all in-progress migrations."""
        await self.initialize()

        conn = await self._connect()
        try:
            if self._use_postgres:
                rows = await conn.fetch(
                    """
                    SELECT * FROM version_migrations
                    WHERE status = 'in_progress'
                    ORDER BY started_at DESC
                    """
                )
            else:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    """
                    SELECT * FROM version_migrations
                    WHERE status = 'in_progress'
                    ORDER BY started_at DESC
                    """
                ) as cursor:
                    rows = await cursor.fetchall()

            results = []
            for row in rows:
                started_at = row["started_at"]
                if isinstance(started_at, str):
                    started_at = datetime.fromisoformat(started_at)
                completed_at = row["completed_at"]
                if isinstance(completed_at, str):
                    completed_at = datetime.fromisoformat(completed_at)

                results.append(
                    MigrationInfo(
                        id=row["id"],
                        from_version=row["from_version"],
                        to_version=row["to_version"],
                        started_at=started_at,
                        completed_at=completed_at,
                        status=row["status"],
                        runs_drained=row["runs_drained"],
                        runs_remaining=row["runs_remaining"],
                    )
                )
            return results
        finally:
            await conn.close()

    async def check_migration_status(self, migration_id: int) -> MigrationStatus:
        """
        Check status of an in-progress migration.

        Args:
            migration_id: ID of the migration to check

        Returns:
            MigrationStatus with current progress
        """
        await self.initialize()

        conn = await self._connect()
        try:
            if self._use_postgres:
                migration = await conn.fetchrow(
                    "SELECT * FROM version_migrations WHERE id = $1",
                    migration_id,
                )
            else:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM version_migrations WHERE id = ?",
                    (migration_id,),
                ) as cursor:
                    migration = await cursor.fetchone()

            if not migration:
                return MigrationStatus(status="not_found")

            # Count remaining runs if migration is in progress
            runs_remaining = migration["runs_remaining"]
            if migration["status"] == "in_progress" and migration["from_version"]:
                if self._use_postgres:
                    row = await conn.fetchrow(
                        """
                        SELECT COUNT(*) as count FROM process_runs
                        WHERE dsl_version = $1
                            AND status IN ('pending', 'running', 'suspended', 'waiting')
                        """,
                        migration["from_version"],
                    )
                    runs_remaining = row["count"] if row else 0
                else:
                    async with conn.execute(
                        """
                        SELECT COUNT(*) as count FROM process_runs
                        WHERE dsl_version = ?
                            AND status IN ('pending', 'running', 'suspended', 'waiting')
                        """,
                        (migration["from_version"],),
                    ) as cursor:
                        row = await cursor.fetchone()
                        runs_remaining = row["count"] if row else 0

            started_at = migration["started_at"]
            if isinstance(started_at, str):
                started_at = datetime.fromisoformat(started_at)
            completed_at = migration["completed_at"]
            if isinstance(completed_at, str):
                completed_at = datetime.fromisoformat(completed_at)

            return MigrationStatus(
                status=migration["status"],
                from_version=migration["from_version"],
                to_version=migration["to_version"],
                runs_remaining=runs_remaining,
                runs_drained=migration["runs_drained"],
                started_at=started_at,
                completed_at=completed_at,
            )
        finally:
            await conn.close()

    async def complete_migration(self, migration_id: int) -> None:
        """
        Mark migration as complete, archive old version.

        Args:
            migration_id: ID of the migration to complete
        """
        await self.initialize()

        conn = await self._connect()
        try:
            if self._use_postgres:
                migration = await conn.fetchrow(
                    "SELECT from_version, to_version FROM version_migrations WHERE id = $1",
                    migration_id,
                )
            else:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT from_version, to_version FROM version_migrations WHERE id = ?",
                    (migration_id,),
                ) as cursor:
                    migration = await cursor.fetchone()

            if not migration:
                logger.warning(f"Migration {migration_id} not found")
                return

            if self._use_postgres:
                if migration["from_version"]:
                    await conn.execute(
                        "UPDATE dsl_versions SET status = 'archived' WHERE version_id = $1",
                        migration["from_version"],
                    )
                await conn.execute(
                    """
                    UPDATE version_migrations
                    SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    migration_id,
                )
            else:
                if migration["from_version"]:
                    await conn.execute(
                        "UPDATE dsl_versions SET status = 'archived' WHERE version_id = ?",
                        (migration["from_version"],),
                    )
                await conn.execute(
                    """
                    UPDATE version_migrations
                    SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (migration_id,),
                )
                await conn.commit()
        finally:
            await conn.close()

        logger.info(f"Completed migration {migration_id}")

    async def rollback_migration(self, migration_id: int) -> None:
        """
        Rollback a migration, reactivating old version.

        Args:
            migration_id: ID of the migration to rollback
        """
        await self.initialize()

        conn = await self._connect()
        try:
            if self._use_postgres:
                migration = await conn.fetchrow(
                    "SELECT from_version, to_version FROM version_migrations WHERE id = $1",
                    migration_id,
                )
            else:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT from_version, to_version FROM version_migrations WHERE id = ?",
                    (migration_id,),
                ) as cursor:
                    migration = await cursor.fetchone()

            if not migration:
                logger.warning(f"Migration {migration_id} not found")
                return

            if self._use_postgres:
                if migration["from_version"]:
                    await conn.execute(
                        "UPDATE dsl_versions SET status = 'active' WHERE version_id = $1",
                        migration["from_version"],
                    )
                await conn.execute(
                    "UPDATE dsl_versions SET status = 'archived' WHERE version_id = $1",
                    migration["to_version"],
                )
                await conn.execute(
                    """
                    UPDATE version_migrations
                    SET status = 'rolled_back', completed_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    migration_id,
                )
            else:
                if migration["from_version"]:
                    await conn.execute(
                        "UPDATE dsl_versions SET status = 'active' WHERE version_id = ?",
                        (migration["from_version"],),
                    )
                await conn.execute(
                    "UPDATE dsl_versions SET status = 'archived' WHERE version_id = ?",
                    (migration["to_version"],),
                )
                await conn.execute(
                    """
                    UPDATE version_migrations
                    SET status = 'rolled_back', completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (migration_id,),
                )
                await conn.commit()
        finally:
            await conn.close()

        logger.info(
            f"Rolled back migration {migration_id}: "
            f"{migration['to_version']} -> {migration['from_version']}"
        )

    async def suspend_remaining_processes(self, version_id: str) -> int:
        """
        Suspend all remaining processes for a version.

        Used when force-draining before a migration timeout.

        Args:
            version_id: Version to suspend processes for

        Returns:
            Number of processes suspended
        """
        if not self._adapter:
            logger.warning("No adapter configured, cannot suspend processes")
            return 0

        await self.initialize()

        # Get all running processes for this version
        runs = await self._adapter.list_runs(status=None)
        suspended = 0

        for run in runs:
            if run.dsl_version == version_id and run.status.value in (
                "pending",
                "running",
                "waiting",
            ):
                await self._adapter.suspend_process(run.run_id)
                suspended += 1

        logger.info(f"Suspended {suspended} processes for version {version_id}")
        return suspended


@dataclass
class DrainWatcherConfig:
    """Configuration for the DrainWatcher."""

    check_interval_seconds: float = 30.0
    auto_complete: bool = True


class DrainWatcher:
    """
    Background task that monitors draining processes.

    Automatically completes migrations when all processes have drained.

    Usage:
        watcher = DrainWatcher(version_manager)
        await watcher.start()
        # ... later ...
        await watcher.stop()
    """

    def __init__(
        self,
        version_manager: VersionManager,
        config: DrainWatcherConfig | None = None,
    ):
        """
        Initialize drain watcher.

        Args:
            version_manager: VersionManager instance to monitor
            config: Optional configuration
        """
        self._version_manager = version_manager
        self._config = config or DrainWatcherConfig()
        self._task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._running and self._task is not None

    async def start(self) -> None:
        """Start watching for completed drains."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("DrainWatcher started")

    async def stop(self) -> None:
        """Stop the watcher."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("DrainWatcher stopped")

    async def _watch_loop(self) -> None:
        """Monitor draining versions and complete migrations."""
        while self._running:
            try:
                # Find in-progress migrations
                migrations = await self._version_manager.get_active_migrations()

                for migration in migrations:
                    status = await self._version_manager.check_migration_status(migration.id)

                    if status.runs_remaining == 0 and self._config.auto_complete:
                        await self._version_manager.complete_migration(migration.id)
                        logger.info(
                            f"Migration {migration.id} auto-completed: "
                            f"{migration.from_version} -> {migration.to_version}"
                        )

                await asyncio.sleep(self._config.check_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"DrainWatcher error: {e}")
                await asyncio.sleep(self._config.check_interval_seconds * 2)


def generate_version_id(dsl_hash: str, prefix: str = "v") -> str:
    """
    Generate a unique version ID.

    Args:
        dsl_hash: Hash of DSL file contents
        prefix: Prefix for version ID

    Returns:
        Version ID like "v20250115_143022_abc123"
    """

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}{timestamp}_{dsl_hash[:8]}"
