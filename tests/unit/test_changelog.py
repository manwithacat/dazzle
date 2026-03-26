"""Tests for changelog parsing utility."""

from pathlib import Path

import pytest

from dazzle.core.changelog import parse_changelog_since

SAMPLE_CHANGELOG = """\
# Changelog

All notable changes to DAZZLE will be documented in this file.

## [Unreleased]

## [0.44.0] - 2026-03-19

### Added
- **Schema-per-tenant isolation** — TenantMiddleware with resolvers (#531)
- **DSL anti-pattern guidance** — 5 modeling anti-patterns surfaced via lint

### Fixed
- Scope rules using current_user.school resolve to null

### Changed
- **server.py subsystem migration** — reduced from 2,214 to 936 lines (#535)
- 8 `Any` annotations replaced with concrete types

## [0.43.0] - 2026-03-18

### Added
- **RBAC Verification Framework** — three-layer access control
- `dazzle rbac matrix` CLI command

### Fixed
- Critical: LIST gate silently disabled for role-based access rules

### Changed
- 14 code smells fixed from systematic analysis

## [0.42.0] - 2026-03-14

### Added
- **Surface field visibility by role** — visible: condition on sections
- **Grant schema infrastructure** — grant_schema DSL construct

### Fixed
- Pulse compliance scoring now reads DSL classify directives
"""


@pytest.fixture
def changelog_file(tmp_path: Path) -> Path:
    """Write the sample changelog to a temp file."""
    p = tmp_path / "CHANGELOG.md"
    p.write_text(SAMPLE_CHANGELOG)
    return p


class TestParseChangelogSince:
    """Tests for parse_changelog_since."""

    def test_since_previous_version(self, changelog_file: Path) -> None:
        """Items from 0.44.0 only when since=0.43.0."""
        items = parse_changelog_since(changelog_file, "0.43.0")
        assert len(items) == 4
        # Should include Added and Changed, not Fixed
        assert any("Schema-per-tenant" in i for i in items)
        assert any("anti-pattern" in i for i in items)
        assert any("subsystem migration" in i for i in items)
        assert any("annotations" in i for i in items)
        # Fixed items should not appear
        assert not any("current_user.school" in i for i in items)

    def test_since_older_version(self, changelog_file: Path) -> None:
        """Items from both 0.44.0 and 0.43.0 when since=0.42.0."""
        items = parse_changelog_since(changelog_file, "0.42.0")
        # 0.44.0: 2 Added + 2 Changed = 4
        # 0.43.0: 2 Added + 1 Changed = 3
        assert len(items) == 7
        assert any("RBAC" in i for i in items)
        assert any("Schema-per-tenant" in i for i in items)

    def test_since_empty_string_gets_all(self, changelog_file: Path) -> None:
        """Empty since_version returns items from every version."""
        items = parse_changelog_since(changelog_file, "")
        # All versions: 0.44.0 (4) + 0.43.0 (3) + 0.42.0 (2 Added) = 9
        assert len(items) == 9

    def test_same_version_returns_empty(self, changelog_file: Path) -> None:
        """No items when since_version matches the first version."""
        items = parse_changelog_since(changelog_file, "0.44.0")
        assert items == []

    def test_bold_markers_stripped(self, changelog_file: Path) -> None:
        """Bold **...** markers are removed from item text."""
        items = parse_changelog_since(changelog_file, "0.43.0")
        for item in items:
            assert "**" not in item

    def test_missing_file(self, tmp_path: Path) -> None:
        """Returns empty list when file does not exist."""
        items = parse_changelog_since(tmp_path / "nope.md", "0.43.0")
        assert items == []

    def test_malformed_changelog(self, tmp_path: Path) -> None:
        """Returns empty list for file with no version headings."""
        p = tmp_path / "CHANGELOG.md"
        p.write_text("Just some random text\nNo headings here\n")
        items = parse_changelog_since(p, "0.43.0")
        assert items == []

    def test_unreleased_section_skipped(self, changelog_file: Path) -> None:
        """Items under [Unreleased] are not included."""
        # Add an item under Unreleased
        content = changelog_file.read_text()
        content = content.replace(
            "## [Unreleased]\n",
            "## [Unreleased]\n\n### Added\n- Unreleased feature\n\n",
        )
        changelog_file.write_text(content)
        items = parse_changelog_since(changelog_file, "0.43.0")
        assert not any("Unreleased feature" in i for i in items)

    def test_fixed_items_excluded(self, changelog_file: Path) -> None:
        """### Fixed items are never included."""
        items = parse_changelog_since(changelog_file, "")
        for item in items:
            assert "LIST gate" not in item
            assert "Pulse compliance" not in item
            assert "current_user.school" not in item
