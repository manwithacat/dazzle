"""Tests for FileMetadataStore PostgreSQL hardening."""

from __future__ import annotations

from unittest.mock import patch

from dazzle_back.runtime.file_storage import FileMetadataStore


class TestFileMetadataStorePostgresFlag:
    """Test that database_url is required and accepted."""

    def test_postgres_url_accepted(self) -> None:
        """Verify that providing database_url works."""
        with patch.object(FileMetadataStore, "_init_db"):
            store = FileMetadataStore(database_url="postgresql://user:pass@localhost/db")
            assert store._pg_url == "postgresql://user:pass@localhost/db"

    def test_heroku_postgres_url_normalized(self) -> None:
        """Heroku uses postgres:// which should be normalized to postgresql://."""
        with patch.object(FileMetadataStore, "_init_db"):
            store = FileMetadataStore(database_url="postgres://user:pass@localhost/db")
            assert store._pg_url is not None
            assert store._pg_url.startswith("postgresql://")

    def test_no_url_raises_error(self) -> None:
        """Verify that omitting database_url raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="database_url is required"):
            FileMetadataStore()
