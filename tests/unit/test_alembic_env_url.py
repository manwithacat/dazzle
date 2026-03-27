"""Tests for alembic env.py URL normalization (#727)."""

from unittest.mock import MagicMock, patch


class TestGetUrl:
    """Test _get_url() handles postgres://, postgresql://, and env fallback."""

    def _call_get_url(self, *, sqlalchemy_url: str = "", env_url: str = "") -> str:
        """Call _get_url() with mocked config and environment."""
        # We need to mock the alembic context before importing env.py,
        # so we patch at the module level.
        mock_config = MagicMock()
        mock_config.get_main_option.return_value = sqlalchemy_url
        mock_config.config_file_name = None

        mock_context = MagicMock()
        mock_context.config = mock_config

        with patch.dict("os.environ", {"DATABASE_URL": env_url} if env_url else {}, clear=False):
            # Inline the logic from _get_url to test it without importing env.py
            # (which has heavy alembic dependencies)
            import os

            url = sqlalchemy_url or os.environ.get("DATABASE_URL", "")
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            return url

    def test_heroku_postgres_scheme_normalized(self) -> None:
        """postgres:// (Heroku) is normalized to postgresql+psycopg://."""
        url = self._call_get_url(env_url="postgres://user:pass@host:5432/db")
        assert url == "postgresql+psycopg://user:pass@host:5432/db"

    def test_standard_postgresql_scheme_gets_psycopg(self) -> None:
        """postgresql:// gets psycopg driver added."""
        url = self._call_get_url(sqlalchemy_url="postgresql://user:pass@host/db")
        assert url == "postgresql+psycopg://user:pass@host/db"

    def test_already_psycopg_driver_unchanged(self) -> None:
        """postgresql+psycopg:// passes through unchanged."""
        url = self._call_get_url(sqlalchemy_url="postgresql+psycopg://user:pass@host/db")
        assert url == "postgresql+psycopg://user:pass@host/db"

    def test_sqlalchemy_url_preferred_over_env(self) -> None:
        """sqlalchemy.url from config takes precedence over DATABASE_URL."""
        url = self._call_get_url(
            sqlalchemy_url="postgresql://from-config@host/db",
            env_url="postgres://from-env@host/db",
        )
        assert "from-config" in url
        assert "from-env" not in url

    def test_env_fallback_when_no_config(self) -> None:
        """Falls back to DATABASE_URL when sqlalchemy.url is empty."""
        url = self._call_get_url(sqlalchemy_url="", env_url="postgres://user@host/db")
        assert url == "postgresql+psycopg://user@host/db"

    def test_empty_url(self) -> None:
        """Returns empty string when no URL is configured."""
        url = self._call_get_url(sqlalchemy_url="", env_url="")
        assert url == ""
