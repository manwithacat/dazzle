"""Tests for dazzle.qa.server — process lifecycle management."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dazzle.qa.server import AppConnection, connect_app


class TestAppConnection:
    def test_from_url_is_external(self) -> None:
        conn = AppConnection(site_url="http://localhost:3000", api_url="http://localhost:8000")
        assert conn.is_external is True

    def test_with_process_is_not_external(self) -> None:
        mock_proc: subprocess.Popen[bytes] = MagicMock(spec=subprocess.Popen)
        conn = AppConnection(
            site_url="http://localhost:3000",
            api_url="http://localhost:8000",
            process=mock_proc,
        )
        assert conn.is_external is False

    def test_stop_does_nothing_for_external(self) -> None:
        conn = AppConnection(site_url="http://localhost:3000", api_url="http://localhost:8000")
        # Should not raise — external connections are not owned
        conn.stop()

    def test_stop_terminates_owned_process(self) -> None:
        mock_proc: subprocess.Popen[bytes] = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None  # process still running
        mock_proc.wait.return_value = 0
        conn = AppConnection(
            site_url="http://localhost:3000",
            api_url="http://localhost:8000",
            process=mock_proc,
        )
        conn.stop()
        mock_proc.terminate.assert_called_once()


class TestConnectApp:
    def test_connect_with_url_returns_external_connection(self) -> None:
        conn = connect_app(url="http://localhost:3000")
        assert conn.is_external is True
        assert conn.site_url == "http://localhost:3000"

    def test_connect_with_url_infers_api_url(self) -> None:
        conn = connect_app(url="http://localhost:3000")
        assert conn.api_url == "http://localhost:8000"

    def test_connect_with_explicit_api_url_uses_it(self) -> None:
        conn = connect_app(url="http://localhost:3000", api_url="http://localhost:9000")
        assert conn.api_url == "http://localhost:9000"

    def test_connect_with_no_args_raises(self) -> None:
        with pytest.raises(ValueError, match="url.*project_dir"):
            connect_app()

    def test_connect_with_project_dir_starts_subprocess(self, tmp_path: Path) -> None:
        import sys
        from unittest.mock import patch

        mock_proc: subprocess.Popen[bytes] = MagicMock(spec=subprocess.Popen)
        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            conn = connect_app(project_dir=tmp_path)
        assert conn.is_external is False
        assert conn.process is mock_proc
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        assert sys.executable in cmd
        assert "dazzle" in cmd or "serve" in cmd
