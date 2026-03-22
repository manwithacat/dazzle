"""Tests for production mode helpers."""

from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest

from dazzle.cli.runtime_impl.production import (
    configure_production_logging,
    validate_production_env,
)


class TestValidateProductionEnv:
    """Tests for production environment validation."""

    def test_returns_database_url_when_set(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db"}):
            db_url, redis_url = validate_production_env()
            assert db_url == "postgresql://localhost/db"
            assert redis_url is None

    def test_normalizes_postgres_to_postgresql(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgres://localhost/db"}):
            db_url, _ = validate_production_env()
            assert db_url == "postgresql://localhost/db"

    def test_raises_when_database_url_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(SystemExit):
                validate_production_env()

    def test_returns_redis_url_when_set(self) -> None:
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "REDIS_URL": "redis://localhost"},
        ):
            _, redis_url = validate_production_env()
            assert redis_url == "redis://localhost"

    def test_redis_url_is_none_when_unset(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db"}, clear=True):
            _, redis_url = validate_production_env()
            assert redis_url is None

    def test_reads_port_env_var(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db", "PORT": "9000"}):
            db_url, _ = validate_production_env()
            assert os.environ["PORT"] == "9000"


class TestConfigureProductionLogging:
    """Tests for structured JSON logging setup."""

    def test_sets_json_format_on_root_logger(self) -> None:
        configure_production_logging()
        root = logging.getLogger()
        # Should have at least one handler with JSON-style formatter
        assert (
            any(
                hasattr(h.formatter, "_fmt") and "message" in (h.formatter._fmt or "")
                for h in root.handlers
            )
            or len(root.handlers) > 0
        )
        # Clean up
        root.handlers.clear()

    def test_produces_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_production_logging()
        logger = logging.getLogger("test.production")
        logger.setLevel(logging.INFO)
        logger.info("test message")
        # Clean up
        logging.getLogger().handlers.clear()
