"""Tests for dazzle.docs_update.scanner — mocked ``gh`` subprocess."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from dazzle.docs_update.scanner import (
    _clean_body,
    resolve_since,
    scan_closed_issues,
)

# ---------------------------------------------------------------------------
# _clean_body
# ---------------------------------------------------------------------------


class TestCleanBody:
    def test_strips_images(self) -> None:
        body = "Text before ![alt](https://img.png) text after"
        assert "![" not in _clean_body(body)
        assert "text after" in _clean_body(body)

    def test_truncates_long_body(self) -> None:
        body = "x" * 3000
        cleaned = _clean_body(body)
        assert len(cleaned) < 2100
        assert "truncated" in cleaned

    def test_empty_body(self) -> None:
        assert _clean_body("") == ""
        assert _clean_body(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# resolve_since
# ---------------------------------------------------------------------------


class TestResolveSince:
    @patch("dazzle.docs_update.scanner._run_gh")
    def test_none_uses_latest_release(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = json.dumps([{"publishedAt": "2026-02-01T00:00:00Z"}])
        result = resolve_since(None, "owner/repo")
        assert result == "2026-02-01"

    @patch("dazzle.docs_update.scanner._run_gh")
    def test_none_fallback_no_releases(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = "[]"
        result = resolve_since(None, "owner/repo")
        # Should fall back to 30 days ago
        expected = (datetime.now(tz=UTC) - timedelta(days=30)).strftime("%Y-%m-%d")
        assert result == expected

    def test_relative_days(self) -> None:
        result = resolve_since("14 days", "owner/repo")
        expected = (datetime.now(tz=UTC) - timedelta(days=14)).strftime("%Y-%m-%d")
        assert result == expected

    def test_relative_day_singular(self) -> None:
        result = resolve_since("1 day", "owner/repo")
        expected = (datetime.now(tz=UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        assert result == expected

    def test_date_string_passthrough(self) -> None:
        result = resolve_since("2026-01-15", "owner/repo")
        assert result == "2026-01-15"

    @patch("dazzle.docs_update.scanner._run_gh")
    def test_tag_name(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = json.dumps({"publishedAt": "2026-01-20T12:00:00Z"})
        result = resolve_since("v0.25.0", "owner/repo")
        assert result == "2026-01-20"


# ---------------------------------------------------------------------------
# scan_closed_issues
# ---------------------------------------------------------------------------


class TestScanClosedIssues:
    @patch("dazzle.docs_update.scanner._gh_available", return_value=True)
    @patch("dazzle.docs_update.scanner._run_gh")
    def test_returns_issues(self, mock_gh: MagicMock, _avail: MagicMock) -> None:
        mock_gh.return_value = json.dumps(
            [
                {
                    "number": 100,
                    "title": "Add feature X",
                    "body": "Description of feature X",
                    "labels": [{"name": "enhancement"}],
                    "closedAt": "2026-02-10T00:00:00Z",
                    "url": "https://github.com/owner/repo/issues/100",
                },
                {
                    "number": 101,
                    "title": "Won't fix this",
                    "body": "",
                    "labels": [{"name": "wontfix"}],
                    "closedAt": "2026-02-10T00:00:00Z",
                    "url": "https://github.com/owner/repo/issues/101",
                },
            ]
        )
        issues = scan_closed_issues("2026-02-01", "owner/repo")
        # wontfix should be filtered
        assert len(issues) == 1
        assert issues[0].number == 100
        assert issues[0].title == "Add feature X"

    @patch("dazzle.docs_update.scanner._gh_available", return_value=True)
    @patch("dazzle.docs_update.scanner._run_gh")
    def test_handles_string_labels(self, mock_gh: MagicMock, _avail: MagicMock) -> None:
        mock_gh.return_value = json.dumps(
            [
                {
                    "number": 200,
                    "title": "A normal issue",
                    "body": "body",
                    "labels": ["bug"],
                    "closedAt": "2026-02-10T00:00:00Z",
                    "url": "https://github.com/owner/repo/issues/200",
                },
            ]
        )
        issues = scan_closed_issues("2026-02-01", "owner/repo")
        assert len(issues) == 1
        assert issues[0].labels == ["bug"]

    @patch("dazzle.docs_update.scanner._gh_available", return_value=False)
    def test_raises_when_not_authenticated(self, _avail: MagicMock) -> None:
        with pytest.raises(RuntimeError, match="not authenticated"):
            scan_closed_issues("2026-02-01", "owner/repo")

    @patch("dazzle.docs_update.scanner._gh_available", return_value=True)
    @patch("dazzle.docs_update.scanner._run_gh")
    def test_empty_result(self, mock_gh: MagicMock, _avail: MagicMock) -> None:
        mock_gh.return_value = "[]"
        issues = scan_closed_issues("2026-02-01", "owner/repo")
        assert issues == []
