"""Tests for FileMetadataStore PostgreSQL hardening."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dazzle_back.runtime.file_storage import FileMetadata, FileMetadataStore


class TestFileMetadataStorePostgresFlag:
    """Test that database_url sets _use_postgres correctly."""

    def test_postgres_url_sets_flag(self) -> None:
        """Verify that providing database_url sets _use_postgres=True."""
        # We can't actually connect, but we can check the flag
        # Use a mock to avoid actual connection
        from unittest.mock import patch

        with patch.object(FileMetadataStore, "_init_db"):
            store = FileMetadataStore(database_url="postgresql://user:pass@localhost/db")
            assert store._use_postgres is True

    def test_no_url_defaults_to_sqlite(self, tmp_path: Path) -> None:
        store = FileMetadataStore(db_path=tmp_path / "test.db")
        assert store._use_postgres is False

    def test_heroku_postgres_url_normalized(self) -> None:
        """Heroku uses postgres:// which should be normalized to postgresql://."""
        from unittest.mock import patch

        with patch.object(FileMetadataStore, "_init_db"):
            store = FileMetadataStore(database_url="postgres://user:pass@localhost/db")
            assert store._use_postgres is True
            assert store._pg_url is not None
            assert store._pg_url.startswith("postgresql://")


class TestFileMetadataStoreSQLiteFunctional:
    """Functional tests using actual SQLite database."""

    def test_save_and_get(self, tmp_path: Path) -> None:
        store = FileMetadataStore(db_path=tmp_path / "test.db")
        file_id = uuid4()
        metadata = FileMetadata(
            id=file_id,
            filename="test.txt",
            content_type="text/plain",
            size=42,
            storage_key="2026/01/01/test.txt",
            storage_backend="local",
            created_at=datetime.now(UTC),
            url="/files/2026/01/01/test.txt",
        )

        store.save(metadata)
        result = store.get(file_id)

        assert result is not None
        assert result.id == file_id
        assert result.filename == "test.txt"
        assert result.content_type == "text/plain"
        assert result.size == 42

    def test_get_nonexistent(self, tmp_path: Path) -> None:
        store = FileMetadataStore(db_path=tmp_path / "test.db")
        result = store.get(uuid4())
        assert result is None

    def test_delete(self, tmp_path: Path) -> None:
        store = FileMetadataStore(db_path=tmp_path / "test.db")
        file_id = uuid4()
        metadata = FileMetadata(
            id=file_id,
            filename="test.txt",
            content_type="text/plain",
            size=42,
            storage_key="key",
            storage_backend="local",
            created_at=datetime.now(UTC),
            url="/files/key",
        )
        store.save(metadata)

        assert store.delete(file_id) is True
        assert store.get(file_id) is None

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        store = FileMetadataStore(db_path=tmp_path / "test.db")
        assert store.delete(uuid4()) is False

    def test_get_by_entity(self, tmp_path: Path) -> None:
        store = FileMetadataStore(db_path=tmp_path / "test.db")
        file_id = uuid4()
        metadata = FileMetadata(
            id=file_id,
            filename="avatar.png",
            content_type="image/png",
            size=1024,
            storage_key="avatars/avatar.png",
            storage_backend="local",
            entity_name="User",
            entity_id="user-1",
            field_name="avatar",
            created_at=datetime.now(UTC),
            url="/files/avatars/avatar.png",
        )
        store.save(metadata)

        results = store.get_by_entity("User", "user-1")
        assert len(results) == 1
        assert results[0].id == file_id

        results_with_field = store.get_by_entity("User", "user-1", field_name="avatar")
        assert len(results_with_field) == 1

        results_empty = store.get_by_entity("User", "user-999")
        assert len(results_empty) == 0

    def test_update_entity_association(self, tmp_path: Path) -> None:
        store = FileMetadataStore(db_path=tmp_path / "test.db")
        file_id = uuid4()
        metadata = FileMetadata(
            id=file_id,
            filename="doc.pdf",
            content_type="application/pdf",
            size=2048,
            storage_key="docs/doc.pdf",
            storage_backend="local",
            created_at=datetime.now(UTC),
            url="/files/docs/doc.pdf",
        )
        store.save(metadata)

        result = store.update_entity_association(file_id, "Invoice", "inv-1", "attachment")
        assert result is True

        updated = store.get(file_id)
        assert updated is not None
        assert updated.entity_name == "Invoice"
        assert updated.entity_id == "inv-1"
        assert updated.field_name == "attachment"
