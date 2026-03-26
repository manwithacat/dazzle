"""Tests for dazzle.db.connection — database URL resolution and connection factory."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from dazzle.db.connection import resolve_db_url


class TestResolveDbUrl:
    def test_explicit_url_wins(self) -> None:
        url = resolve_db_url(explicit_url="postgresql://localhost/mydb")
        assert url == "postgresql://localhost/mydb"

    @patch.dict("os.environ", {"DATABASE_URL": "postgresql://env/db"}, clear=False)
    def test_env_var_fallback(self) -> None:
        url = resolve_db_url()
        assert url == "postgresql://env/db"

    @patch("dazzle.db.connection.load_manifest")
    @patch("dazzle.db.connection.Path.exists", return_value=True)
    def test_manifest_fallback(self, mock_exists: MagicMock, mock_load: MagicMock) -> None:
        import os

        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        with patch.dict("os.environ", env, clear=True):
            manifest = MagicMock()
            manifest.database.url = "postgresql://manifest/db"
            mock_load.return_value = manifest
            url = resolve_db_url(project_root=Path("/fake/project"))
            assert url == "postgresql://manifest/db"

    def test_default_when_nothing_set(self) -> None:
        import os

        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        with patch.dict("os.environ", env, clear=True):
            url = resolve_db_url()
            assert "postgresql://" in url
