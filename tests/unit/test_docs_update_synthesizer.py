"""Tests for dazzle.docs_update.synthesizer — mocked LLM calls."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from dazzle.docs_update.models import ClosedIssue, IssueCategory
from dazzle.docs_update.synthesizer import classify_issues, generate_patches

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(number: int, title: str, labels: list[str] | None = None) -> ClosedIssue:
    return ClosedIssue(
        number=number,
        title=title,
        body=f"Body for {title}",
        labels=labels or [],
        closed_at="2026-02-10T00:00:00Z",
        url=f"https://github.com/owner/repo/issues/{number}",
    )


# ---------------------------------------------------------------------------
# classify_issues
# ---------------------------------------------------------------------------


class TestClassifyIssues:
    def test_classifies_from_llm_response(self) -> None:
        issues = [_make_issue(1, "Add new widget"), _make_issue(2, "Fix crash on login")]

        llm_response = json.dumps(
            [
                {
                    "number": 1,
                    "category": "feature",
                    "summary": "Add widget component",
                    "affected_docs": ["changelog", "readme"],
                },
                {
                    "number": 2,
                    "category": "bug_fix",
                    "summary": "Fix login crash",
                    "affected_docs": ["changelog"],
                },
            ]
        )

        mock_llm = MagicMock(return_value=llm_response)
        result = classify_issues(issues, mock_llm)

        assert result[0].category == IssueCategory.FEATURE
        assert result[0].summary == "Add widget component"
        assert "readme" in result[0].affected_docs

        assert result[1].category == IssueCategory.BUG_FIX
        assert result[1].summary == "Fix login crash"

    def test_handles_markdown_fenced_json(self) -> None:
        issues = [_make_issue(1, "Something")]
        fenced = '```json\n[{"number": 1, "category": "enhancement", "summary": "Improved something", "affected_docs": ["changelog"]}]\n```'

        mock_llm = MagicMock(return_value=fenced)
        result = classify_issues(issues, mock_llm)
        assert result[0].category == IssueCategory.ENHANCEMENT

    def test_handles_invalid_json(self) -> None:
        issues = [_make_issue(1, "Something")]
        mock_llm = MagicMock(return_value="This is not JSON at all")
        result = classify_issues(issues, mock_llm)
        # Should return issues unchanged (no classification)
        assert result[0].category is None

    def test_handles_unknown_category(self) -> None:
        issues = [_make_issue(1, "Something")]
        llm_response = json.dumps(
            [{"number": 1, "category": "unknown_cat", "summary": "X", "affected_docs": []}]
        )
        mock_llm = MagicMock(return_value=llm_response)
        result = classify_issues(issues, mock_llm)
        assert result[0].category == IssueCategory.INTERNAL  # fallback

    def test_empty_issues(self) -> None:
        mock_llm = MagicMock()
        result = classify_issues([], mock_llm)
        assert result == []
        mock_llm.assert_not_called()

    def test_missing_issue_number_in_response(self) -> None:
        issues = [_make_issue(1, "Something")]
        llm_response = json.dumps(
            [{"number": 999, "category": "feature", "summary": "X", "affected_docs": []}]
        )
        mock_llm = MagicMock(return_value=llm_response)
        result = classify_issues(issues, mock_llm)
        # Issue 1 not matched — category stays None
        assert result[0].category is None


# ---------------------------------------------------------------------------
# generate_patches — changelog
# ---------------------------------------------------------------------------


class TestGeneratePatches:
    def test_changelog_patch(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n---\n\n## [0.16.0] - 2025-12-16\n\n### Added\n- Old stuff\n"
        )

        issues = [_make_issue(1, "Add feature X")]
        issues[0].category = IssueCategory.FEATURE
        issues[0].summary = "Add feature X"
        issues[0].affected_docs = ["changelog"]

        mock_llm = MagicMock(
            return_value="### Added\n- Add feature X ([#1](https://github.com/owner/repo/issues/1))"
        )

        patches = generate_patches(issues, ["changelog"], tmp_path, mock_llm)
        assert len(patches) == 1
        assert patches[0].target == "changelog"
        assert "## [Unreleased]" in patches[0].proposed
        assert "Add feature X" in patches[0].proposed

    def test_skips_internal_issues(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [0.16.0]\n\n### Added\n- Old\n")

        issues = [_make_issue(1, "CI fix")]
        issues[0].category = IssueCategory.INTERNAL

        mock_llm = MagicMock()
        patches = generate_patches(issues, ["changelog"], tmp_path, mock_llm)
        assert patches == []

    def test_no_changelog_file(self, tmp_path: Path) -> None:
        issues = [_make_issue(1, "Feature")]
        issues[0].category = IssueCategory.FEATURE
        issues[0].summary = "Feature"

        mock_llm = MagicMock()
        patches = generate_patches(issues, ["changelog"], tmp_path, mock_llm)
        assert patches == []

    def test_readme_patch(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text(
            "# App\n\n## Features\n\nOld features list.\n\n## Install\n\npip install app\n"
        )

        issues = [_make_issue(1, "Add widget")]
        issues[0].category = IssueCategory.FEATURE
        issues[0].summary = "Add widget"
        issues[0].affected_docs = ["readme"]

        llm_response = json.dumps(
            [{"section": "Features", "updated_body": "New features list with widget."}]
        )
        mock_llm = MagicMock(return_value=llm_response)

        patches = generate_patches(issues, ["readme"], tmp_path, mock_llm)
        assert len(patches) == 1
        assert patches[0].target == "readme"
        assert "New features list with widget." in patches[0].proposed

    def test_mkdocs_patch(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        page = docs / "index.md"
        page.write_text("# Welcome\n\nOld intro.\n")

        issues = [_make_issue(1, "Add new CLI command")]
        issues[0].category = IssueCategory.FEATURE
        issues[0].summary = "Add docs command"
        issues[0].affected_docs = ["mkdocs"]

        # First LLM call: identify pages
        # Second LLM call: update page content
        call_count = 0

        def mock_complete(system: str, user: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps([{"page": "index.md", "summary": "Add docs command section"}])
            return "# Welcome\n\nUpdated intro with docs command.\n"

        patches = generate_patches(issues, ["mkdocs"], tmp_path, mock_complete)
        assert len(patches) == 1
        assert patches[0].target == "mkdocs"
        assert "Updated intro" in patches[0].proposed

    def test_changelog_llm_failure_uses_deterministic(self, tmp_path: Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n---\n\n## [0.16.0] - 2025-12-16\n\n### Added\n- Old\n")

        issues = [_make_issue(1, "Add feature Y")]
        issues[0].category = IssueCategory.FEATURE
        issues[0].summary = "Add feature Y"
        issues[0].affected_docs = ["changelog"]

        def mock_fail(system: str, user: str) -> str:
            raise RuntimeError("LLM down")

        patches = generate_patches(issues, ["changelog"], tmp_path, mock_fail)
        assert len(patches) == 1
        # Should still have the deterministic entries
        assert "Add feature Y" in patches[0].proposed
