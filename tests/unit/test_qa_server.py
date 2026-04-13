"""Unit tests for dazzle.qa.server.AppConnection."""

import json
from pathlib import Path

import pytest

from dazzle.qa.server import AppConnection


class TestAppConnection:
    def test_external_connection_has_no_process(self) -> None:
        conn = AppConnection(
            site_url="http://localhost:8981",
            api_url="http://localhost:8969",
            process=None,
        )
        assert conn.is_external is True
        assert conn.process is None

    def test_stop_is_noop_when_external(self) -> None:
        conn = AppConnection(
            site_url="http://localhost:8981",
            api_url="http://localhost:8969",
            process=None,
        )
        conn.stop()  # Should not raise


class TestAppConnectionFromRuntimeFile:
    def test_reads_ui_and_api_urls(self, tmp_path: Path) -> None:
        project_root = tmp_path / "example"
        (project_root / ".dazzle").mkdir(parents=True)
        (project_root / ".dazzle" / "runtime.json").write_text(
            json.dumps(
                {
                    "project_name": "example",
                    "ui_port": 8981,
                    "api_port": 8969,
                    "ui_url": "http://localhost:8981",
                    "api_url": "http://localhost:8969",
                }
            )
        )

        conn = AppConnection.from_runtime_file(project_root)
        assert conn.site_url == "http://localhost:8981"
        assert conn.api_url == "http://localhost:8969"
        assert conn.process is None
        assert conn.is_external is True

    def test_raises_when_runtime_file_missing(self, tmp_path: Path) -> None:
        project_root = tmp_path / "example"
        project_root.mkdir()
        (project_root / ".dazzle").mkdir()

        with pytest.raises(FileNotFoundError, match="runtime.json"):
            AppConnection.from_runtime_file(project_root)
