"""Tests for ``dazzle.cli.dotenv.load_project_dotenv`` (#814)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dazzle.cli.dotenv import load_project_dotenv


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scrub test-affecting env vars so assertions are deterministic."""
    for key in ("DATABASE_URL", "REDIS_URL", "TEST_KEY_814"):
        monkeypatch.delenv(key, raising=False)


class TestLoadProjectDotenv:
    def test_missing_env_file_returns_empty(self, tmp_path: Path, clean_env: None) -> None:
        assert load_project_dotenv(tmp_path) == []

    def test_loads_simple_assignments(self, tmp_path: Path, clean_env: None) -> None:
        (tmp_path / ".env").write_text("DATABASE_URL=postgresql://localhost:5432/test\n")
        loaded = load_project_dotenv(tmp_path)
        assert "DATABASE_URL" in loaded
        assert os.environ["DATABASE_URL"] == "postgresql://localhost:5432/test"

    def test_shell_export_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None
    ) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql://shell-wins")
        (tmp_path / ".env").write_text("DATABASE_URL=postgresql://from-file\n")
        loaded = load_project_dotenv(tmp_path)
        assert "DATABASE_URL" not in loaded
        assert os.environ["DATABASE_URL"] == "postgresql://shell-wins"

    def test_strips_quotes_and_export_prefix(self, tmp_path: Path, clean_env: None) -> None:
        (tmp_path / ".env").write_text(
            "export TEST_KEY_814=\"value with spaces\"\nREDIS_URL='redis://host:6379'\n"
        )
        load_project_dotenv(tmp_path)
        assert os.environ["TEST_KEY_814"] == "value with spaces"
        assert os.environ["REDIS_URL"] == "redis://host:6379"

    def test_skips_comments_and_blank_lines(self, tmp_path: Path, clean_env: None) -> None:
        (tmp_path / ".env").write_text("# leading comment\n\nTEST_KEY_814=ok\n# trailing comment\n")
        loaded = load_project_dotenv(tmp_path)
        assert loaded == ["TEST_KEY_814"]

    def test_skips_malformed_lines(self, tmp_path: Path, clean_env: None) -> None:
        (tmp_path / ".env").write_text("NOT_A_KVP\nTEST_KEY_814=ok\n=only_value\n")
        loaded = load_project_dotenv(tmp_path)
        assert loaded == ["TEST_KEY_814"]
