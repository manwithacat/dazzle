"""Tests for _load_dotenv helper in serve.py (issues #768, #769)."""

import os
from pathlib import Path
from unittest.mock import patch

from dazzle.cli.runtime_impl.serve import _load_dotenv


class TestLoadDotenv:
    def test_no_env_file_returns_empty_list(self, tmp_path: Path) -> None:
        """When .env doesn't exist, returns empty list and doesn't raise."""
        result = _load_dotenv(tmp_path)
        assert result == []

    def test_simple_key_value(self, tmp_path: Path) -> None:
        """Basic KEY=VALUE lines populate os.environ."""
        (tmp_path / ".env").write_text("FOO_TEST_VAR=bar\n")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FOO_TEST_VAR", None)
            result = _load_dotenv(tmp_path)
            assert "FOO_TEST_VAR" in result
            assert os.environ["FOO_TEST_VAR"] == "bar"

    def test_multiple_vars(self, tmp_path: Path) -> None:
        """Multiple variables in one file."""
        (tmp_path / ".env").write_text(
            "DATABASE_URL_TEST=postgresql://localhost/db\nREDIS_URL_TEST=redis://localhost:6379/0\n"
        )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL_TEST", None)
            os.environ.pop("REDIS_URL_TEST", None)
            result = _load_dotenv(tmp_path)
            assert "DATABASE_URL_TEST" in result
            assert "REDIS_URL_TEST" in result
            assert os.environ["DATABASE_URL_TEST"] == "postgresql://localhost/db"
            assert os.environ["REDIS_URL_TEST"] == "redis://localhost:6379/0"

    def test_comments_ignored(self, tmp_path: Path) -> None:
        """Lines starting with # are ignored."""
        (tmp_path / ".env").write_text(
            "# This is a comment\nCOMMENT_TEST_VAR=value\n# Another comment\n"
        )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMMENT_TEST_VAR", None)
            result = _load_dotenv(tmp_path)
            assert result == ["COMMENT_TEST_VAR"]
            assert os.environ["COMMENT_TEST_VAR"] == "value"

    def test_blank_lines_ignored(self, tmp_path: Path) -> None:
        """Blank lines don't cause errors."""
        (tmp_path / ".env").write_text("\n\nBLANK_TEST_VAR=value\n\n")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BLANK_TEST_VAR", None)
            result = _load_dotenv(tmp_path)
            assert result == ["BLANK_TEST_VAR"]

    def test_export_prefix_stripped(self, tmp_path: Path) -> None:
        """'export KEY=VALUE' syntax is supported."""
        (tmp_path / ".env").write_text("export EXPORT_TEST_VAR=value\n")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EXPORT_TEST_VAR", None)
            result = _load_dotenv(tmp_path)
            assert result == ["EXPORT_TEST_VAR"]
            assert os.environ["EXPORT_TEST_VAR"] == "value"

    def test_quoted_values_unquoted(self, tmp_path: Path) -> None:
        """Values wrapped in matching quotes have quotes stripped."""
        (tmp_path / ".env").write_text(
            "QUOTED_DOUBLE_TEST=\"hello world\"\nQUOTED_SINGLE_TEST='single quoted'\n"
        )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QUOTED_DOUBLE_TEST", None)
            os.environ.pop("QUOTED_SINGLE_TEST", None)
            _load_dotenv(tmp_path)
            assert os.environ["QUOTED_DOUBLE_TEST"] == "hello world"
            assert os.environ["QUOTED_SINGLE_TEST"] == "single quoted"

    def test_existing_env_takes_precedence(self, tmp_path: Path) -> None:
        """Existing os.environ values are not overridden by .env."""
        (tmp_path / ".env").write_text("PRECEDENCE_TEST_VAR=from_env_file\n")
        with patch.dict(os.environ, {"PRECEDENCE_TEST_VAR": "from_shell"}, clear=False):
            result = _load_dotenv(tmp_path)
            # Not in the "loaded" list because it was already set
            assert "PRECEDENCE_TEST_VAR" not in result
            assert os.environ["PRECEDENCE_TEST_VAR"] == "from_shell"

    def test_malformed_line_skipped(self, tmp_path: Path) -> None:
        """Lines without = are skipped silently."""
        (tmp_path / ".env").write_text("NOT_KEY_VALUE\nVALID_TEST_VAR=value\n=leading_equals\n")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VALID_TEST_VAR", None)
            result = _load_dotenv(tmp_path)
            assert "VALID_TEST_VAR" in result
            assert "NOT_KEY_VALUE" not in result
