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
    ):
        """
        Initialize version manager.

        Args:
            db_path: Path to SQLite database
            adapter: Optional ProcessAdapter for process queries
        """
        self._db_path = Path(db_path)
        self._adapter = adapter
        self._current_version: str | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize database tables if needed."""
        if self._initialized:
            return

        async with aiosqlite.connect(self._db_path) as db:
            # Create version tables if they don't exist
            await db.executescript(
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
            await db.commit()

        self._initialized = True
        logger.debug("VersionManager initialized")

    async def get_current_version(self) -> str | None:
        """Get the currently active DSL version."""
        await self.initialize()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT version_id FROM dsl_versions
                WHERE status = 'active'
                ORDER BY deployed_at DESC
                LIMIT 1
                """
            ) as cursor:
                row = await cursor.fetchone()
                return row["version_id"] if row else None

    async def get_version(self, version_id: str) -> VersionInfo | None:
        """Get information about a specific version."""
        await self.initialize()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM dsl_versions WHERE version_id = ?",
                (version_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                return VersionInfo(
                    version_id=row["version_id"],
                    deployed_at=datetime.fromisoformat(row["deployed_at"]),
                    dsl_hash=row["dsl_hash"],
                    manifest=json.loads(row["manifest_json"]),
                    status=row["status"],
                )

    async def list_versions(
        self,
        status: str | None = None,
        limit: int = 10,
    ) -> list[VersionInfo]:
        """List deployed versions with optional status filter."""
        await self.initialize()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

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

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()

            return [
                VersionInfo(
                    version_id=row["version_id"],
                    deployed_at=datetime.fromisoformat(row["deployed_at"]),
                    dsl_hash=row["dsl_hash"],
                    manifest=json.loads(row["manifest_json"]),
                    status=row["status"],
                )
                for row in rows
            ]

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

        async with aiosqlite.connect(self._db_path) as db:
            # Check if version already exists
            async with db.execute(
                "SELECT 1 FROM dsl_versions WHERE version_id = ?",
                (version_id,),
            ) as cursor:
                if await cursor.fetchone():
                    raise ValueError(f"Version {version_id} already exists")

            # Insert new version as active
            await db.execute(
                """
                INSERT INTO dsl_versions (version_id, dsl_hash, manifest_json, status)
                VALUES (?, ?, ?, 'active')
                """,
                (version_id, dsl_hash, json.dumps(manifest)),
            )
            await db.commit()

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

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            # Count running processes on old version
            async with db.execute(
                """
                SELECT COUNT(*) as count FROM process_runs
                WHERE dsl_version = ? AND status IN ('pending', 'running', 'suspended', 'waiting')
                """,
                (from_version,),
            ) as cursor:
                row = await cursor.fetchone()
                runs_remaining = row["count"] if row else 0

            # Mark old version as draining
            await db.execute(
                "UPDATE dsl_versions SET status = 'draining' WHERE version_id = ?",
                (from_version,),
            )

            # Create migration record
            await db.execute(
                """
                INSERT INTO version_migrations
                (from_version, to_version, runs_remaining, status)
                VALUES (?, ?, ?, 'in_progress')
                """,
                (from_version, to_version, runs_remaining),
            )
            await db.commit()

        logger.info(
            f"Started migration: {from_version} -> {to_version}, "
            f"{runs_remaining} processes to drain"
        )
        return runs_remaining

    async def get_active_migrations(self) -> list[MigrationInfo]:
        """Get all in-progress migrations."""
        await self.initialize()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM version_migrations
                WHERE status = 'in_progress'
                ORDER BY started_at DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()

            return [
                MigrationInfo(
                    id=row["id"],
                    from_version=row["from_version"],
                    to_version=row["to_version"],
                    started_at=datetime.fromisoformat(row["started_at"]),
                    completed_at=(
                        datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
                    ),
                    status=row["status"],
                    runs_drained=row["runs_drained"],
                    runs_remaining=row["runs_remaining"],
                )
                for row in rows
            ]

    async def check_migration_status(self, migration_id: int) -> MigrationStatus:
        """
        Check status of an in-progress migration.

        Args:
            migration_id: ID of the migration to check

        Returns:
            MigrationStatus with current progress
        """
        await self.initialize()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            # Get migration record
            async with db.execute(
                "SELECT * FROM version_migrations WHERE id = ?",
                (migration_id,),
            ) as cursor:
                migration = await cursor.fetchone()

            if not migration:
                return MigrationStatus(status="not_found")

            # Count remaining runs if migration is in progress
            runs_remaining = migration["runs_remaining"]
            if migration["status"] == "in_progress" and migration["from_version"]:
                async with db.execute(
                    """
                    SELECT COUNT(*) as count FROM process_runs
                    WHERE dsl_version = ?
                        AND status IN ('pending', 'running', 'suspended', 'waiting')
                    """,
                    (migration["from_version"],),
                ) as cursor:
                    row = await cursor.fetchone()
                    runs_remaining = row["count"] if row else 0

            return MigrationStatus(
                status=migration["status"],
                from_version=migration["from_version"],
                to_version=migration["to_version"],
                runs_remaining=runs_remaining,
                runs_drained=migration["runs_drained"],
                started_at=datetime.fromisoformat(migration["started_at"]),
                completed_at=(
                    datetime.fromisoformat(migration["completed_at"])
                    if migration["completed_at"]
                    else None
                ),
            )

    async def complete_migration(self, migration_id: int) -> None:
        """
        Mark migration as complete, archive old version.

        Args:
            migration_id: ID of the migration to complete
        """
        await self.initialize()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            # Get migration details
            async with db.execute(
                "SELECT from_version, to_version FROM version_migrations WHERE id = ?",
                (migration_id,),
            ) as cursor:
                migration = await cursor.fetchone()

            if not migration:
                logger.warning(f"Migration {migration_id} not found")
                return

            # Archive old version
            if migration["from_version"]:
                await db.execute(
                    "UPDATE dsl_versions SET status = 'archived' WHERE version_id = ?",
                    (migration["from_version"],),
                )

            # Update migration record
            await db.execute(
                """
                UPDATE version_migrations
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (migration_id,),
            )
            await db.commit()

        logger.info(f"Completed migration {migration_id}")

    async def rollback_migration(self, migration_id: int) -> None:
        """
        Rollback a migration, reactivating old version.

        Args:
            migration_id: ID of the migration to rollback
        """
        await self.initialize()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            # Get migration details
            async with db.execute(
                "SELECT from_version, to_version FROM version_migrations WHERE id = ?",
                (migration_id,),
            ) as cursor:
                migration = await cursor.fetchone()

            if not migration:
                logger.warning(f"Migration {migration_id} not found")
                return

            # Reactivate old version
            if migration["from_version"]:
                await db.execute(
                    "UPDATE dsl_versions SET status = 'active' WHERE version_id = ?",
                    (migration["from_version"],),
                )

            # Deactivate new version
            await db.execute(
                "UPDATE dsl_versions SET status = 'archived' WHERE version_id = ?",
                (migration["to_version"],),
            )

            # Mark migration as rolled back
            await db.execute(
                """
                UPDATE version_migrations
                SET status = 'rolled_back', completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (migration_id,),
            )
            await db.commit()

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
