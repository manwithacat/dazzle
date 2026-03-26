"""
Changelog parser — extracts Agent Guidance sections from CHANGELOG.md.

Parses Keep-a-Changelog format, finds ``### Agent Guidance`` subsections,
and returns structured entries with version + bullet points.
"""

import logging
import re
from pathlib import Path
from typing import Any

from packaging.version import Version

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]")
_GUIDANCE_RE = re.compile(r"^### Agent Guidance\s*$")
_SECTION_RE = re.compile(r"^### ")
_BULLET_RE = re.compile(r"^- (.+)$")


def _find_changelog_path() -> Path | None:
    """Walk up from this file to find CHANGELOG.md at the project root."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = current / "CHANGELOG.md"
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def parse_changelog_guidance(
    *,
    since: str | None = None,
    limit: int = 5,
    changelog_text: str | None = None,
) -> list[dict[str, Any]]:
    """
    Parse Agent Guidance sections from CHANGELOG.md.

    Args:
        since: If given, only return entries for versions >= this value.
        limit: Maximum number of entries to return (default 5).
        changelog_text: Raw changelog text. If None, reads from CHANGELOG.md.

    Returns:
        List of ``{"version": "X.Y.Z", "guidance": ["bullet1", ...]}`` dicts,
        ordered newest-first.
    """
    if changelog_text is None:
        path = _find_changelog_path()
        if path is None:
            logger.warning("CHANGELOG.md not found")
            return []
        changelog_text = path.read_text(encoding="utf-8")

    entries: list[dict[str, Any]] = []
    current_version: str | None = None
    in_guidance = False
    bullets: list[str] = []

    for line in changelog_text.splitlines():
        version_match = _VERSION_RE.match(line)
        if version_match:
            if current_version and bullets:
                entries.append({"version": current_version, "guidance": list(bullets)})
            current_version = version_match.group(1)
            in_guidance = False
            bullets = []
            continue

        if _GUIDANCE_RE.match(line):
            in_guidance = True
            continue

        if in_guidance and _SECTION_RE.match(line):
            in_guidance = False
            continue

        if in_guidance:
            bullet_match = _BULLET_RE.match(line)
            if bullet_match:
                bullets.append(bullet_match.group(1))

    if current_version and bullets:
        entries.append({"version": current_version, "guidance": list(bullets)})

    if since:
        since_ver = Version(since)
        entries = [e for e in entries if Version(e["version"]) >= since_ver]

    return entries[:limit]
