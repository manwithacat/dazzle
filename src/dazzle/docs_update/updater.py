"""Markdown section parsing, patching, and diff generation."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass


@dataclass
class MarkdownSection:
    """A section of a markdown file delimited by headers."""

    header: str  # e.g. "## [Unreleased]"
    level: int  # 1 for #, 2 for ##, etc.
    content: str  # everything after the header line until the next same/higher-level header
    start_line: int = 0
    end_line: int = 0


def parse_sections(content: str) -> list[MarkdownSection]:
    """Split markdown content into sections by header boundaries.

    Each section includes the header line and all content up to (but not
    including) the next header of the same or higher level.
    """
    lines = content.split("\n")
    sections: list[MarkdownSection] = []
    header_re = re.compile(r"^(#{1,6})\s+(.+)$")

    current: MarkdownSection | None = None
    body_lines: list[str] = []

    for i, line in enumerate(lines):
        m = header_re.match(line)
        if m:
            # Close previous section
            if current is not None:
                current.content = "\n".join(body_lines)
                current.end_line = i - 1
                sections.append(current)
            level = len(m.group(1))
            header_text = m.group(2).strip()
            current = MarkdownSection(
                header=header_text,
                level=level,
                content="",
                start_line=i,
            )
            body_lines = []
        elif current is not None:
            body_lines.append(line)
        # Lines before the first header are ignored (preamble)

    # Close last section
    if current is not None:
        current.content = "\n".join(body_lines)
        current.end_line = len(lines) - 1
        sections.append(current)

    return sections


def find_section(content: str, title: str) -> MarkdownSection | None:
    """Find a section whose header contains *title* (case-insensitive)."""
    title_lower = title.lower()
    for section in parse_sections(content):
        if title_lower in section.header.lower():
            return section
    return None


def replace_section(content: str, section_header: str, new_body: str) -> str:
    """Replace the body of a section while preserving the header line.

    Returns the full document with the section body swapped out.
    """
    lines = content.split("\n")
    sections = parse_sections(content)

    target = None
    for s in sections:
        if section_header.lower() in s.header.lower():
            target = s
            break

    if target is None:
        return content  # Section not found — return unchanged

    # The header line is at target.start_line, body starts at start_line + 1
    header_line = lines[target.start_line]
    before = lines[: target.start_line]
    after = lines[target.end_line + 1 :]

    new_lines = [*before, header_line, new_body.rstrip("\n"), *after]
    return "\n".join(new_lines)


def insert_after_header(content: str, header: str, new_lines_text: str) -> str:
    """Insert text immediately after a matching header line.

    Useful for adding entries under an existing CHANGELOG section header.
    """
    lines = content.split("\n")
    header_lower = header.lower()

    for i, line in enumerate(lines):
        if header_lower in line.lower():
            before = lines[: i + 1]
            after = lines[i + 1 :]
            return "\n".join([*before, new_lines_text.rstrip("\n"), *after])

    return content  # Header not found


def ensure_unreleased_section(content: str) -> str:
    """Ensure an ``## [Unreleased]`` section exists at the top of the changelog.

    If one already exists, returns content unchanged.
    Otherwise inserts one above the first ``## [`` version header.
    """
    if re.search(r"^## \[Unreleased\]", content, re.MULTILINE):
        return content

    # Find the first version header like ## [0.16.0]
    m = re.search(r"^(## \[)", content, re.MULTILINE)
    if m:
        pos = m.start()
        return content[:pos] + "## [Unreleased]\n\n" + content[pos:]

    # No version headers at all — append after the first ---
    m_sep = re.search(r"^---\s*$", content, re.MULTILINE)
    if m_sep:
        pos = m_sep.end()
        return content[:pos] + "\n\n## [Unreleased]\n" + content[pos:]

    # Fallback: append at end
    return content.rstrip("\n") + "\n\n## [Unreleased]\n"


def build_changelog_entries(
    issues: list[dict[str, str]],
) -> str:
    """Build changelog entry text grouped by Keep-a-Changelog subsections.

    Each item in *issues* should have keys: ``category``, ``summary``, ``number``, ``url``.
    """
    from dazzle.docs_update.models import CATEGORY_SECTIONS, IssueCategory

    groups: dict[str, list[str]] = {}

    for issue in issues:
        cat = issue.get("category", "")
        try:
            category = IssueCategory(cat)
        except ValueError:
            continue  # Skip internal / unknown
        if category == IssueCategory.INTERNAL:
            continue

        section_header = CATEGORY_SECTIONS.get(category, "### Changed")
        summary = issue.get("summary", issue.get("title", ""))
        number = issue.get("number", "")
        url = issue.get("url", "")

        if url:
            entry = f"- {summary} ([#{number}]({url}))"
        else:
            entry = f"- {summary} (#{number})"

        groups.setdefault(section_header, []).append(entry)

    # Build text in Keep-a-Changelog order
    order = ["### Added", "### Changed", "### Deprecated", "### Fixed"]
    parts: list[str] = []
    for header in order:
        if header in groups:
            parts.append(header)
            parts.extend(groups[header])
            parts.append("")

    return "\n".join(parts)


def generate_diff(original: str, proposed: str, filename: str = "file") -> str:
    """Generate a unified diff between original and proposed content."""
    orig_lines = original.splitlines(keepends=True)
    prop_lines = proposed.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines,
        prop_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    )
    return "".join(diff)


def apply_patches(patches: list[dict[str, str]]) -> dict[str, str]:
    """Apply a list of patches, returning {file_path: new_content}.

    Each patch dict must have ``file_path`` and ``proposed`` keys.
    When multiple patches target the same file they are applied sequentially.
    """
    results: dict[str, str] = {}
    for patch in patches:
        path = patch["file_path"]
        results[path] = patch["proposed"]
    return results
