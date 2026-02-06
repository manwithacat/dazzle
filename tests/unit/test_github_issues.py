"""Tests for GitHub issue creation helper and its integration points."""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

# Pre-mock the mcp SDK package so dazzle.mcp.server can be imported
# without the mcp package being installed.
for _mod in ("mcp", "mcp.server", "mcp.server.fastmcp", "mcp.server.stdio", "mcp.types"):
    sys.modules.setdefault(_mod, MagicMock(pytest_plugins=[]))

from dazzle.mcp.server.github_issues import (  # noqa: E402
    _fallback,
    _gh_available,
    create_github_issue,
)

# ---------------------------------------------------------------------------
# create_github_issue
# ---------------------------------------------------------------------------


class TestCreateGithubIssue:
    def test_success_returns_url(self) -> None:
        with (
            patch("dazzle.mcp.server.github_issues._gh_available", return_value=True),
            patch("dazzle.mcp.server.github_issues.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="https://github.com/manwithacat/dazzle/issues/42\n",
            )
            result = create_github_issue("title", "body", ["bug"])
            assert result == {"url": "https://github.com/manwithacat/dazzle/issues/42"}

    def test_gh_not_available_returns_fallback(self) -> None:
        with patch("dazzle.mcp.server.github_issues._gh_available", return_value=False):
            result = create_github_issue("title", "body", ["bug"])
            assert result["fallback"] is True
            assert "manual_url" in result

    def test_gh_run_fails_returns_fallback(self) -> None:
        with (
            patch("dazzle.mcp.server.github_issues._gh_available", return_value=True),
            patch("dazzle.mcp.server.github_issues.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stderr="auth error")
            result = create_github_issue("title", "body", ["bug"])
            assert result["fallback"] is True

    def test_gh_file_not_found_returns_fallback(self) -> None:
        with (
            patch("dazzle.mcp.server.github_issues._gh_available", return_value=True),
            patch(
                "dazzle.mcp.server.github_issues.subprocess.run",
                side_effect=FileNotFoundError,
            ),
        ):
            result = create_github_issue("title", "body", ["bug"])
            assert result["fallback"] is True

    def test_labels_passed_to_command(self) -> None:
        with (
            patch("dazzle.mcp.server.github_issues._gh_available", return_value=True),
            patch("dazzle.mcp.server.github_issues.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0, stdout="https://github.com/x/y/issues/1\n"
            )
            create_github_issue("t", "b", ["feedback", "high"])
            cmd = mock_run.call_args[0][0]
            assert "--label" in cmd
            label_indices = [i for i, v in enumerate(cmd) if v == "--label"]
            labels = [cmd[i + 1] for i in label_indices]
            assert labels == ["feedback", "high"]


# ---------------------------------------------------------------------------
# _gh_available
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _fallback
# ---------------------------------------------------------------------------


class TestFallback:
    def test_contains_manual_url(self) -> None:
        result = _fallback("t", "b", "owner/repo")
        assert result["manual_url"] == "https://github.com/owner/repo/issues/new"
        assert result["fallback"] is True
        assert result["title"] == "t"
        assert result["body"] == "b"


# ---------------------------------------------------------------------------
# Integration: handle_add_feedback
# ---------------------------------------------------------------------------


class TestHandleAddFeedbackIntegration:
    def test_includes_github_issue(self) -> None:
        with patch("dazzle.mcp.server.github_issues._gh_available", return_value=False):
            from dazzle.mcp.event_first_tools import handle_add_feedback

            result = json.loads(
                handle_add_feedback(
                    {
                        "pain_point": "Something is wrong",
                        "expected": "Should work",
                        "observed": "Does not work",
                        "severity": "high",
                        "scope": "entity",
                    },
                    project_path=MagicMock(),
                )
            )
            assert "github_issue" in result
            assert result["github_issue"]["fallback"] is True


# ---------------------------------------------------------------------------
# Integration: create_handler
# ---------------------------------------------------------------------------


class TestCreateHandlerIntegration:
    def test_includes_github_issue(self) -> None:
        with patch("dazzle.mcp.server.github_issues._gh_available", return_value=False):
            from dazzle.mcp.server.handlers.contribution import create_handler

            result = json.loads(
                create_handler(
                    {
                        "type": "feature_request",
                        "title": "Test Feature",
                        "description": "A test",
                        "content": {
                            "motivation": "Testing",
                            "proposed_solution": "Do the thing",
                        },
                    }
                )
            )
            assert "github_issue" in result
            assert result["github_issue"]["fallback"] is True
