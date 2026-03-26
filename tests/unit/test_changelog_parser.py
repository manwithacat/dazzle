"""Tests for parse_changelog_guidance()."""

import textwrap

from dazzle.mcp.semantics_kb.changelog import parse_changelog_guidance

SAMPLE_CHANGELOG = textwrap.dedent("""\
    # Changelog

    ## [0.50.0] - 2026-04-01

    ### Added
    - Some new feature

    ### Agent Guidance
    - **New rule**: Do the new thing
    - **Another rule**: Also do this

    ## [0.49.0] - 2026-03-30

    ### Fixed
    - Bug fix

    ## [0.48.12] - 2026-03-26

    ### Added
    - Admin workspace

    ### Agent Guidance
    - **Admin entities**: Filter by domain="platform"
    - **Schema migrations**: Use Alembic for all changes

    ## [0.48.8] - 2026-03-25

    ### Agent Guidance
    - **CSS**: Local-first delivery

    ## [0.48.2] - 2026-03-24

    ### Agent Guidance
    - **PostgreSQL only**: No SQLite

    ## [0.48.0] - 2026-03-24

    ### Agent Guidance
    - **Grant RBAC**: Use has_grant() in guards
    - **Templates**: Use dz:// prefix for extends

    ## [0.47.0] - 2026-03-20

    ### Agent Guidance
    - **Old guidance**: Something from before
""")


class TestParseChangelogGuidance:
    """Tests for the changelog parser."""

    def test_returns_entries_with_guidance(self) -> None:
        """Versions without Agent Guidance sections are excluded."""
        entries = parse_changelog_guidance(changelog_text=SAMPLE_CHANGELOG)
        versions = [e["version"] for e in entries]
        assert "0.49.0" not in versions
        assert "0.50.0" in versions

    def test_default_limit_is_5(self) -> None:
        """Default returns at most 5 entries."""
        entries = parse_changelog_guidance(changelog_text=SAMPLE_CHANGELOG)
        assert len(entries) <= 5

    def test_ordered_newest_first(self) -> None:
        """Entries are ordered newest version first."""
        entries = parse_changelog_guidance(changelog_text=SAMPLE_CHANGELOG, limit=10)
        versions = [e["version"] for e in entries]
        assert versions[0] == "0.50.0"
        assert versions[-1] == "0.47.0"

    def test_extracts_bullet_points(self) -> None:
        """Each entry has a guidance list of bullet point strings."""
        entries = parse_changelog_guidance(changelog_text=SAMPLE_CHANGELOG, limit=10)
        entry_050 = next(e for e in entries if e["version"] == "0.50.0")
        assert len(entry_050["guidance"]) == 2
        assert "New rule" in entry_050["guidance"][0]

    def test_since_filter(self) -> None:
        """since parameter filters to versions >= the given version."""
        entries = parse_changelog_guidance(
            changelog_text=SAMPLE_CHANGELOG, since="0.48.8", limit=10
        )
        versions = [e["version"] for e in entries]
        assert "0.47.0" not in versions
        assert "0.48.2" not in versions
        assert "0.48.8" in versions
        assert "0.50.0" in versions

    def test_since_filter_with_limit(self) -> None:
        """since + limit work together."""
        entries = parse_changelog_guidance(changelog_text=SAMPLE_CHANGELOG, since="0.48.0", limit=2)
        assert len(entries) == 2
        assert entries[0]["version"] == "0.50.0"

    def test_empty_changelog(self) -> None:
        """Empty changelog returns empty list."""
        entries = parse_changelog_guidance(changelog_text="# Changelog\n")
        assert entries == []

    def test_strips_leading_dash_from_bullets(self) -> None:
        """Bullet text has the leading '- ' stripped."""
        entries = parse_changelog_guidance(changelog_text=SAMPLE_CHANGELOG, limit=10)
        entry = next(e for e in entries if e["version"] == "0.48.2")
        assert entry["guidance"] == ["**PostgreSQL only**: No SQLite"]
