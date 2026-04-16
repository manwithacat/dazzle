"""Tests for test-harness persona auth wiring (#790).

Covers:
  - write_runtime_file embeds test_secret when provided
  - read_runtime_test_secret round-trips the value
  - SessionManager._resolve_test_secret env-first, runtime.json fallback
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dazzle.cli.runtime_impl.ports import (
    PortAllocation,
    read_runtime_test_secret,
    write_runtime_file,
)


@pytest.fixture
def allocation() -> PortAllocation:
    return PortAllocation(ui_port=3000, api_port=8000, project_name="demo")


class TestWriteRuntimeFile:
    def test_no_secret_by_default(self, tmp_path: Path, allocation: PortAllocation) -> None:
        write_runtime_file(tmp_path, allocation)
        data = json.loads((tmp_path / ".dazzle" / "runtime.json").read_text())
        assert "test_secret" not in data

    def test_secret_embedded_when_provided(
        self, tmp_path: Path, allocation: PortAllocation
    ) -> None:
        write_runtime_file(tmp_path, allocation, test_secret="s3cr3t")
        data = json.loads((tmp_path / ".dazzle" / "runtime.json").read_text())
        assert data["test_secret"] == "s3cr3t"

    def test_empty_secret_omitted(self, tmp_path: Path, allocation: PortAllocation) -> None:
        write_runtime_file(tmp_path, allocation, test_secret="")
        data = json.loads((tmp_path / ".dazzle" / "runtime.json").read_text())
        assert "test_secret" not in data


class TestReadRuntimeTestSecret:
    def test_missing_runtime_returns_none(self, tmp_path: Path) -> None:
        assert read_runtime_test_secret(tmp_path) is None

    def test_round_trips_value(self, tmp_path: Path, allocation: PortAllocation) -> None:
        write_runtime_file(tmp_path, allocation, test_secret="abc123")
        assert read_runtime_test_secret(tmp_path) == "abc123"

    def test_absent_field_returns_none(self, tmp_path: Path, allocation: PortAllocation) -> None:
        write_runtime_file(tmp_path, allocation)
        assert read_runtime_test_secret(tmp_path) is None

    def test_malformed_json_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / ".dazzle").mkdir()
        (tmp_path / ".dazzle" / "runtime.json").write_text("{not json")
        assert read_runtime_test_secret(tmp_path) is None

    def test_non_string_secret_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / ".dazzle").mkdir()
        (tmp_path / ".dazzle" / "runtime.json").write_text(json.dumps({"test_secret": 42}))
        assert read_runtime_test_secret(tmp_path) is None


class TestSessionManagerResolveSecret:
    def test_env_takes_precedence(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from dazzle.testing.session_manager import SessionManager

        (tmp_path / ".dazzle").mkdir()
        (tmp_path / ".dazzle" / "runtime.json").write_text(
            json.dumps({"test_secret": "runtime-value"})
        )
        monkeypatch.setenv("DAZZLE_TEST_SECRET", "env-value")
        mgr = SessionManager(tmp_path, base_url="http://localhost:8000")
        assert mgr._resolve_test_secret() == "env-value"

    def test_falls_back_to_runtime(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from dazzle.testing.session_manager import SessionManager

        monkeypatch.delenv("DAZZLE_TEST_SECRET", raising=False)
        (tmp_path / ".dazzle").mkdir()
        (tmp_path / ".dazzle" / "runtime.json").write_text(
            json.dumps({"test_secret": "runtime-value"})
        )
        mgr = SessionManager(tmp_path, base_url="http://localhost:8000")
        assert mgr._resolve_test_secret() == "runtime-value"

    def test_returns_empty_when_neither_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from dazzle.testing.session_manager import SessionManager

        monkeypatch.delenv("DAZZLE_TEST_SECRET", raising=False)
        mgr = SessionManager(tmp_path, base_url="http://localhost:8000")
        assert mgr._resolve_test_secret() == ""


class TestE2EAdapterResolvesSecret:
    """The anonymous SimpleAdapter inside E2ERunner.run_tests uses the same fallback."""

    def test_runtime_fallback_reachable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DAZZLE_TEST_SECRET", raising=False)
        (tmp_path / ".dazzle").mkdir()
        (tmp_path / ".dazzle" / "runtime.json").write_text(
            json.dumps({"test_secret": "runtime-adapter"})
        )
        # Resolve the secret through the canonical helper — this is what
        # the adapter closure uses internally.
        assert read_runtime_test_secret(tmp_path) == "runtime-adapter"
