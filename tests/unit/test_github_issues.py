"""Tests for the gh CLI availability check."""

import sys
from unittest.mock import MagicMock, patch

# Pre-mock the mcp SDK package so dazzle.mcp.server can be imported
# without the mcp package being installed.
for _mod in ("mcp", "mcp.server", "mcp.server.fastmcp", "mcp.server.stdio", "mcp.types"):
    sys.modules.setdefault(_mod, MagicMock(pytest_plugins=[]))

from dazzle.mcp.server.github_issues import _gh_available  # noqa: E402


class TestGhAvailable:
    def test_available(self) -> None:
        with (
            patch("dazzle.mcp.server.github_issues._find_gh", return_value="/usr/bin/gh"),
            patch("dazzle.mcp.server.github_issues.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            assert _gh_available() is True

    def test_not_installed(self) -> None:
        with patch("dazzle.mcp.server.github_issues._find_gh", return_value=None):
            assert _gh_available() is False

    def test_not_authenticated(self) -> None:
        with (
            patch("dazzle.mcp.server.github_issues._find_gh", return_value="/usr/bin/gh"),
            patch("dazzle.mcp.server.github_issues.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stderr="not logged in")
            assert _gh_available() is False
