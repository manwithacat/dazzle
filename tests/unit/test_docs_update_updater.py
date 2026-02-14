"""Tests for dazzle.docs_update.updater — pure markdown operations."""

from __future__ import annotations

from dazzle.docs_update.updater import (
    build_changelog_entries,
    ensure_unreleased_section,
    find_section,
    generate_diff,
    insert_after_header,
    parse_sections,
    replace_section,
)

# ---------------------------------------------------------------------------
# parse_sections
# ---------------------------------------------------------------------------

SAMPLE_MD = """\
# Title

Intro paragraph.

## Section One

Content of section one.

### Subsection

Sub content.

## Section Two

Content of section two.
"""


class TestParseSections:
    def test_finds_all_sections(self) -> None:
        sections = parse_sections(SAMPLE_MD)
        headers = [s.header for s in sections]
        assert headers == ["Title", "Section One", "Subsection", "Section Two"]

    def test_section_levels(self) -> None:
        sections = parse_sections(SAMPLE_MD)
        levels = [s.level for s in sections]
        assert levels == [1, 2, 3, 2]

    def test_section_content(self) -> None:
        sections = parse_sections(SAMPLE_MD)
        # Section One should have content including the blank line
        sec_one = sections[1]
        assert "Content of section one." in sec_one.content

    def test_empty_content(self) -> None:
        sections = parse_sections("")
        assert sections == []

    def test_no_headers(self) -> None:
        sections = parse_sections("Just some text\nNo headers here.")
        assert sections == []


# ---------------------------------------------------------------------------
# find_section
# ---------------------------------------------------------------------------


class TestFindSection:
    def test_finds_by_partial_match(self) -> None:
        sec = find_section(SAMPLE_MD, "Section One")
        assert sec is not None
        assert sec.header == "Section One"

    def test_case_insensitive(self) -> None:
        sec = find_section(SAMPLE_MD, "section two")
        assert sec is not None
        assert sec.header == "Section Two"

    def test_not_found(self) -> None:
        sec = find_section(SAMPLE_MD, "Nonexistent")
        assert sec is None


# ---------------------------------------------------------------------------
# replace_section
# ---------------------------------------------------------------------------


class TestReplaceSection:
    def test_replaces_body(self) -> None:
        result = replace_section(SAMPLE_MD, "Section Two", "New content here.")
        assert "New content here." in result
        assert "Content of section two." not in result

    def test_preserves_header(self) -> None:
        result = replace_section(SAMPLE_MD, "Section Two", "Replaced.")
        assert "## Section Two" in result

    def test_no_match_returns_unchanged(self) -> None:
        result = replace_section(SAMPLE_MD, "Missing", "Replaced.")
        assert result == SAMPLE_MD


# ---------------------------------------------------------------------------
# insert_after_header
# ---------------------------------------------------------------------------


class TestInsertAfterHeader:
    def test_inserts_text(self) -> None:
        result = insert_after_header(SAMPLE_MD, "## Section One", "INSERTED LINE")
        lines = result.split("\n")
        # Find the header line
        idx = next(i for i, ln in enumerate(lines) if "## Section One" in ln)
        assert lines[idx + 1] == "INSERTED LINE"

    def test_no_match_returns_unchanged(self) -> None:
        result = insert_after_header(SAMPLE_MD, "## Missing", "INSERTED")
        assert result == SAMPLE_MD


# ---------------------------------------------------------------------------
# ensure_unreleased_section
# ---------------------------------------------------------------------------

CHANGELOG_WITH_UNRELEASED = """\
# Changelog

## [Unreleased]

## [0.16.0] - 2025-12-16

### Added
- Something
"""

CHANGELOG_WITHOUT_UNRELEASED = """\
# Changelog

---

## [0.16.0] - 2025-12-16

### Added
- Something
"""


class TestEnsureUnreleasedSection:
    def test_already_exists(self) -> None:
        result = ensure_unreleased_section(CHANGELOG_WITH_UNRELEASED)
        assert result == CHANGELOG_WITH_UNRELEASED

    def test_inserts_above_version(self) -> None:
        result = ensure_unreleased_section(CHANGELOG_WITHOUT_UNRELEASED)
        assert "## [Unreleased]" in result
        # Should appear before the version header
        unreleased_pos = result.index("## [Unreleased]")
        version_pos = result.index("## [0.16.0]")
        assert unreleased_pos < version_pos


# ---------------------------------------------------------------------------
# build_changelog_entries
# ---------------------------------------------------------------------------


class TestBuildChangelogEntries:
    def test_groups_by_category(self) -> None:
        issues = [
            {
                "category": "feature",
                "summary": "Add X",
                "number": "1",
                "url": "https://github.com/r/1",
            },
            {
                "category": "bug_fix",
                "summary": "Fix Y",
                "number": "2",
                "url": "https://github.com/r/2",
            },
            {"category": "feature", "summary": "Add Z", "number": "3", "url": ""},
        ]
        result = build_changelog_entries(issues)
        assert "### Added" in result
        assert "### Fixed" in result
        assert "Add X" in result
        assert "Fix Y" in result
        assert "(#3)" in result  # No URL fallback
        assert "[#1]" in result  # With URL

    def test_skips_internal(self) -> None:
        issues = [{"category": "internal", "summary": "CI tweak", "number": "5", "url": ""}]
        result = build_changelog_entries(issues)
        assert result.strip() == ""

    def test_empty_list(self) -> None:
        result = build_changelog_entries([])
        assert result.strip() == ""


# ---------------------------------------------------------------------------
# generate_diff
# ---------------------------------------------------------------------------


class TestGenerateDiff:
    def test_shows_changes(self) -> None:
        diff = generate_diff("line1\nline2\n", "line1\nline3\n", "test.md")
        assert "--- a/test.md" in diff
        assert "+++ b/test.md" in diff
        assert "-line2" in diff
        assert "+line3" in diff

    def test_no_changes(self) -> None:
        diff = generate_diff("same\n", "same\n", "test.md")
        assert diff == ""
