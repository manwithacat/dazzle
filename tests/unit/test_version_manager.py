"""
Unit tests for VersionManager and migration functionality.

Tests cover:
- Version deployment and tracking
- Migration lifecycle (start, drain, complete, rollback)
- DrainWatcher background monitoring
- Version hash computation
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from dazzle.core.process import (
    DrainWatcher,
    DrainWatcherConfig,
    VersionManager,
    generate_version_id,
)


@pytest.fixture
def temp_db_path() -> Path:
    """Create temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_versions.db"


@pytest.fixture
async def version_manager(temp_db_path: Path) -> VersionManager:
    """Create initialized VersionManager."""
    vm = VersionManager(db_path=temp_db_path)
    await vm.initialize()
    return vm


class TestVersionManager:
    """Tests for VersionManager class."""

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, temp_db_path: Path) -> None:
        """Test that initialize creates required tables."""
        import aiosqlite

        vm = VersionManager(db_path=temp_db_path)
        await vm.initialize()

        # Check tables exist
        async with aiosqlite.connect(temp_db_path) as db:
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
                tables = [row[0] for row in await cursor.fetchall()]

        assert "dsl_versions" in tables
        assert "version_migrations" in tables

    @pytest.mark.asyncio
    async def test_deploy_version(self, version_manager: VersionManager) -> None:
        """Test deploying a new version."""
        await version_manager.deploy_version(
            version_id="v20250115_001_abc123",
            dsl_hash="abc123def456",
            manifest={"name": "test_app"},
        )

        current = await version_manager.get_current_version()
        assert current == "v20250115_001_abc123"

    @pytest.mark.asyncio
    async def test_deploy_duplicate_version_fails(self, version_manager: VersionManager) -> None:
        """Test that deploying duplicate version raises error."""
        await version_manager.deploy_version("v1", "hash1", {})

        with pytest.raises(ValueError, match="already exists"):
            await version_manager.deploy_version("v1", "hash2", {})

    @pytest.mark.asyncio
    async def test_get_version(self, version_manager: VersionManager) -> None:
        """Test retrieving version details."""
        await version_manager.deploy_version(
            version_id="v1",
            dsl_hash="abc123",
            manifest={"name": "test"},
        )

        version = await version_manager.get_version("v1")

        assert version is not None
        assert version.version_id == "v1"
        assert version.dsl_hash == "abc123"
        assert version.status == "active"
        assert version.manifest == {"name": "test"}

    @pytest.mark.asyncio
    async def test_get_nonexistent_version(self, version_manager: VersionManager) -> None:
        """Test retrieving nonexistent version returns None."""
        version = await version_manager.get_version("nonexistent")
        assert version is None

    @pytest.mark.asyncio
    async def test_list_versions(self, version_manager: VersionManager) -> None:
        """Test listing versions."""
        await version_manager.deploy_version("v1", "hash1", {})
        await version_manager.deploy_version("v2", "hash2", {})
        await version_manager.deploy_version("v3", "hash3", {})

        versions = await version_manager.list_versions()

        # All versions should be returned
        assert len(versions) == 3
        # All version IDs should be present
        version_ids = {v.version_id for v in versions}
        assert version_ids == {"v1", "v2", "v3"}

    @pytest.mark.asyncio
    async def test_list_versions_with_status_filter(self, version_manager: VersionManager) -> None:
        """Test listing versions filtered by status."""
        await version_manager.deploy_version("v1", "hash1", {})
        await version_manager.deploy_version("v2", "hash2", {})

        # Start migration to mark v1 as draining
        await version_manager.start_migration("v1", "v2")

        active_versions = await version_manager.list_versions(status="active")
        draining_versions = await version_manager.list_versions(status="draining")

        assert len(active_versions) == 1
        assert active_versions[0].version_id == "v2"
        assert len(draining_versions) == 1
        assert draining_versions[0].version_id == "v1"


class TestMigration:
    """Tests for migration functionality."""

    @pytest.mark.asyncio
    async def test_start_migration(self, version_manager: VersionManager) -> None:
        """Test starting a migration."""
        await version_manager.deploy_version("v1", "hash1", {})
        await version_manager.deploy_version("v2", "hash2", {})

        remaining = await version_manager.start_migration("v1", "v2")

        # No running processes, so 0 remaining
        assert remaining == 0

        # v1 should be draining
        v1 = await version_manager.get_version("v1")
        assert v1 is not None
        assert v1.status == "draining"

    @pytest.mark.asyncio
    async def test_get_active_migrations(self, version_manager: VersionManager) -> None:
        """Test getting active migrations."""
        await version_manager.deploy_version("v1", "hash1", {})

        await version_manager.start_migration("v1", "v2")

        migrations = await version_manager.get_active_migrations()

        assert len(migrations) == 1
        assert migrations[0].from_version == "v1"
        assert migrations[0].to_version == "v2"
        assert migrations[0].status == "in_progress"

    @pytest.mark.asyncio
    async def test_check_migration_status(self, version_manager: VersionManager) -> None:
        """Test checking migration status."""
        await version_manager.deploy_version("v1", "hash1", {})
        await version_manager.start_migration("v1", "v2")

        migrations = await version_manager.get_active_migrations()
        migration_id = migrations[0].id

        status = await version_manager.check_migration_status(migration_id)

        assert status.status == "in_progress"
        assert status.from_version == "v1"
        assert status.to_version == "v2"
        assert status.runs_remaining == 0

    @pytest.mark.asyncio
    async def test_check_nonexistent_migration(self, version_manager: VersionManager) -> None:
        """Test checking nonexistent migration."""
        status = await version_manager.check_migration_status(999)
        assert status.status == "not_found"

    @pytest.mark.asyncio
    async def test_complete_migration(self, version_manager: VersionManager) -> None:
        """Test completing a migration."""
        await version_manager.deploy_version("v1", "hash1", {})
        await version_manager.deploy_version("v2", "hash2", {})
        await version_manager.start_migration("v1", "v2")

        migrations = await version_manager.get_active_migrations()
        migration_id = migrations[0].id

        await version_manager.complete_migration(migration_id)

        # v1 should be archived
        v1 = await version_manager.get_version("v1")
        assert v1 is not None
        assert v1.status == "archived"

        # Migration should be completed
        status = await version_manager.check_migration_status(migration_id)
        assert status.status == "completed"
        assert status.completed_at is not None

    @pytest.mark.asyncio
    async def test_rollback_migration(self, version_manager: VersionManager) -> None:
        """Test rolling back a migration."""
        await version_manager.deploy_version("v1", "hash1", {})
        await version_manager.deploy_version("v2", "hash2", {})
        await version_manager.start_migration("v1", "v2")

        migrations = await version_manager.get_active_migrations()
        migration_id = migrations[0].id

        await version_manager.rollback_migration(migration_id)

        # v1 should be active again
        v1 = await version_manager.get_version("v1")
        assert v1 is not None
        assert v1.status == "active"

        # v2 should be archived
        v2 = await version_manager.get_version("v2")
        assert v2 is not None
        assert v2.status == "archived"

        # Current version should be v1
        current = await version_manager.get_current_version()
        assert current == "v1"


class TestDrainWatcher:
    """Tests for DrainWatcher class."""

    @pytest.mark.asyncio
    async def test_drain_watcher_starts_and_stops(self, version_manager: VersionManager) -> None:
        """Test DrainWatcher lifecycle."""
        watcher = DrainWatcher(
            version_manager,
            config=DrainWatcherConfig(check_interval_seconds=0.1),
        )

        assert not watcher.is_running

        await watcher.start()
        assert watcher.is_running

        # Let it run briefly
        await asyncio.sleep(0.2)

        await watcher.stop()
        assert not watcher.is_running

    @pytest.mark.asyncio
    async def test_drain_watcher_auto_completes_migration(
        self, version_manager: VersionManager
    ) -> None:
        """Test DrainWatcher auto-completes migrations with no remaining runs."""
        await version_manager.deploy_version("v1", "hash1", {})
        await version_manager.deploy_version("v2", "hash2", {})
        await version_manager.start_migration("v1", "v2")

        watcher = DrainWatcher(
            version_manager,
            config=DrainWatcherConfig(
                check_interval_seconds=0.1,
                auto_complete=True,
            ),
        )

        await watcher.start()

        # Wait for watcher to process
        await asyncio.sleep(0.3)

        await watcher.stop()

        # Migration should be auto-completed
        migrations = await version_manager.get_active_migrations()
        assert len(migrations) == 0


class TestVersionHash:
    """Tests for version hash computation."""

    def test_compute_version_hash(self, tmp_path: Path) -> None:
        """Test computing version hash from DSL files."""
        # Create test DSL files
        (tmp_path / "app.dsl").write_text("module test\napp test_app")
        (tmp_path / "entities.dsl").write_text("entity User:\n  id: uuid pk")

        dsl_files = list(tmp_path.glob("*.dsl"))
        hash1 = VersionManager.compute_version_hash(dsl_files)

        assert len(hash1) == 16  # 16-char hex hash
        assert hash1.isalnum()

    def test_hash_is_deterministic(self, tmp_path: Path) -> None:
        """Test that hash is deterministic for same content."""
        (tmp_path / "app.dsl").write_text("module test")

        dsl_files = list(tmp_path.glob("*.dsl"))
        hash1 = VersionManager.compute_version_hash(dsl_files)
        hash2 = VersionManager.compute_version_hash(dsl_files)

        assert hash1 == hash2

    def test_hash_changes_with_content(self, tmp_path: Path) -> None:
        """Test that hash changes when content changes."""
        dsl_file = tmp_path / "app.dsl"
        dsl_file.write_text("module test")

        hash1 = VersionManager.compute_version_hash([dsl_file])

        dsl_file.write_text("module test_updated")
        hash2 = VersionManager.compute_version_hash([dsl_file])

        assert hash1 != hash2


class TestGenerateVersionId:
    """Tests for version ID generation."""

    def test_generate_version_id_format(self) -> None:
        """Test version ID format."""
        version_id = generate_version_id("abc123def456")

        # Format: vYYYYMMDD_HHMMSS_hash[:8]
        assert version_id.startswith("v")
        parts = version_id[1:].split("_")
        assert len(parts) == 3  # date, time, hash

        # Date part
        assert len(parts[0]) == 8  # YYYYMMDD
        assert parts[0].isdigit()

        # Time part
        assert len(parts[1]) == 6  # HHMMSS
        assert parts[1].isdigit()

        # Hash part (8 chars)
        assert parts[2] == "abc123de"

    def test_generate_version_id_custom_prefix(self) -> None:
        """Test version ID with custom prefix."""
        version_id = generate_version_id("abc123", prefix="release-")
        assert version_id.startswith("release-")
