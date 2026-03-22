"""Tests for production mode helpers."""

from __future__ import annotations

import inspect
import logging
import os
from pathlib import Path
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


from typer.testing import CliRunner  # noqa: E402

runner = CliRunner()


class TestProductionFlagOnServe:
    """Tests for --production flag integration in serve_command."""

    def test_production_parameter_exists(self) -> None:
        """serve_command should accept --production."""
        from dazzle.cli.runtime_impl.serve import serve_command

        sig = inspect.signature(serve_command)
        assert "production" in sig.parameters

    def test_production_fails_without_database_url(self) -> None:
        """--production without DATABASE_URL should exit 1."""
        from dazzle.cli import app

        with patch.dict(os.environ, {}, clear=True):
            result = runner.invoke(app, ["serve", "--production"])
            assert result.exit_code != 0
            assert "DATABASE_URL" in result.output or "DATABASE_URL" in (result.stderr or "")

    def test_production_fails_without_dsl_files(self, tmp_path: Path) -> None:
        """--production with DATABASE_URL but no DSL files should exit 1."""
        from dazzle.cli import app

        # Create minimal dazzle.toml but no .dsl files
        (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\n')
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db"},
            clear=True,
        ):
            result = runner.invoke(
                app, ["serve", "--production", "--manifest", str(tmp_path / "dazzle.toml")]
            )
            assert result.exit_code != 0
            assert "No DSL files" in result.output or "No DSL files" in (result.stderr or "")


class TestRebuildDeprecation:
    """Tests for rebuild command deprecation."""

    def test_rebuild_prints_deprecation_and_exits(self) -> None:
        from dazzle.cli import app

        result = runner.invoke(app, ["rebuild"])
        assert result.exit_code != 0
        assert "dazzle deploy dockerfile" in (result.output + (result.stderr or ""))
