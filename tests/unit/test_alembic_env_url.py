"""Tests for alembic env.py URL normalization (#727)."""

import os
from unittest.mock import patch

import pytest

from dazzle.core.db_url import add_psycopg_driver, normalise_postgres_scheme


def _call_get_url(*, sqlalchemy_url: str = "", env_url: str = "") -> str:
    """Call _get_url() with mocked config and environment.

    Mirrors the logic of env.py's ``_get_url`` (scheme normalisation +
    psycopg driver) via the shared helpers, without importing env.py
    (which has heavy alembic dependencies).
    """
    # clear=True so a host DATABASE_URL (common in dev) cannot leak into
    # the empty_url case when env_url is intentionally blank.
    env = {"DATABASE_URL": env_url} if env_url else {}
    with patch.dict("os.environ", env, clear=True):
        url = sqlalchemy_url or os.environ.get("DATABASE_URL", "")
        return add_psycopg_driver(normalise_postgres_scheme(url))


class TestGetUrl:
    """Test _get_url() handles postgres://, postgresql://, and env fallback."""

    @pytest.mark.parametrize(
        ("sqlalchemy_url", "env_url", "expected"),
        [
            # postgres:// (Heroku) is normalized to postgresql+psycopg://
            (
                "",
                "postgres://user:pass@host:5432/db",
                "postgresql+psycopg://user:pass@host:5432/db",
            ),
            # postgresql:// gets psycopg driver added
            ("postgresql://user:pass@host/db", "", "postgresql+psycopg://user:pass@host/db"),
            # postgresql+psycopg:// passes through unchanged
            (
                "postgresql+psycopg://user:pass@host/db",
                "",
                "postgresql+psycopg://user:pass@host/db",
            ),
            # Falls back to DATABASE_URL when sqlalchemy.url is empty
            ("", "postgres://user@host/db", "postgresql+psycopg://user@host/db"),
            # Returns empty string when no URL is configured
            ("", "", ""),
        ],
        ids=[
            "heroku_postgres_scheme_normalized",
            "standard_postgresql_scheme_gets_psycopg",
            "already_psycopg_driver_unchanged",
            "env_fallback_when_no_config",
            "empty_url",
        ],
    )
    def test_url_normalization(self, sqlalchemy_url: str, env_url: str, expected: str) -> None:
        assert _call_get_url(sqlalchemy_url=sqlalchemy_url, env_url=env_url) == expected

    def test_sqlalchemy_url_preferred_over_env(self) -> None:
        """sqlalchemy.url from config takes precedence over DATABASE_URL."""
        url = _call_get_url(
            sqlalchemy_url="postgresql://from-config@host/db",
            env_url="postgres://from-env@host/db",
        )
        assert "from-config" in url
        assert "from-env" not in url
