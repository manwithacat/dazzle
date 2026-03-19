"""Parse CHANGELOG.md to extract new capabilities between versions.

The changelog follows Keep a Changelog format:
https://keepachangelog.com/en/1.0.0/
"""

from __future__ import annotations

import re
from pathlib import Path


def _strip_bold(text: str) -> str:
    """Remove markdown bold markers (**...**) from text."""
    return re.sub(r"\*\*([^*]+)\*\*", r"\1", text)


def _clean_item(line: str) -> str:
    """Clean a changelog list item to a one-line description."""
    # Strip leading "- " and any trailing whitespace
    text = re.sub(r"^-\s*", "", line).strip()
    return _strip_bold(text)


def parse_changelog_since(changelog_path: Path, since_version: str) -> list[str]:
    """Extract Added/Changed entries from CHANGELOG.md since a given version.

    Parses all version sections between the current (first) version and
    ``since_version`` (exclusive).  Only ``### Added`` and ``### Changed``
    items are returned; ``### Fixed``, ``### Removed``, ``### Security``
    etc. are skipped.

    Args:
        changelog_path: Path to CHANGELOG.md.
        since_version: Version string to stop at (exclusive).

    Returns:
        List of one-line descriptions with bold markers stripped.
    """
    if not changelog_path.exists():
        return []

    try:
        content = changelog_path.read_text(encoding="utf-8")
    except OSError:
        return []

    items: list[str] = []
    # Track which version section we're in
    in_relevant_section = False
    in_capability_heading = False
    reached_since = False

    # Headings we care about (capabilities, not bug fixes)
    capability_headings = {"added", "changed"}

    for line in content.splitlines():
        # Version heading: ## [0.44.0] - 2026-03-19  or  ## [Unreleased]
        version_match = re.match(r"^##\s+\[([^\]]+)\]", line)
        if version_match:
            version_tag = version_match.group(1)
            # Skip [Unreleased]
            if version_tag.lower() == "unreleased":
                in_relevant_section = False
                in_capability_heading = False
                continue

            # If we've reached the since_version, stop collecting
            if version_tag == since_version:
                reached_since = True
                break

            # We're in a version section newer than since_version
            in_relevant_section = True
            in_capability_heading = False
            continue

        if reached_since or not in_relevant_section:
            continue

        # Sub-heading: ### Added, ### Changed, ### Fixed, etc.
        sub_match = re.match(r"^###\s+(\w+)", line)
        if sub_match:
            heading = sub_match.group(1).lower()
            in_capability_heading = heading in capability_headings
            continue

        # List item under a capability heading
        if in_capability_heading and re.match(r"^-\s+", line):
            cleaned = _clean_item(line)
            if cleaned:
                items.append(cleaned)

    return items


def get_changelog_path() -> Path:
    """Return the path to CHANGELOG.md relative to the package source tree."""
    return Path(__file__).parent.parent.parent.parent / "CHANGELOG.md"
