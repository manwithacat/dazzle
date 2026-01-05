"""
Flexible specification loader for DAZZLE.

Supports loading product specifications from:
- spec/ directory (multiple markdown files)
- SPEC.md (single file, backward compatible)

Files in spec/ are loaded recursively, sorted alphabetically,
and concatenated with source markers for LLM context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SpecContent:
    """Loaded specification content."""

    content: str
    """Combined specification content."""

    source_files: list[Path]
    """List of source files that were loaded."""

    source_type: str
    """How the spec was loaded: 'directory', 'single_file', or 'none'."""

    @property
    def is_empty(self) -> bool:
        """Check if any spec content was found."""
        return not self.content.strip()

    @property
    def file_count(self) -> int:
        """Number of source files."""
        return len(self.source_files)


def load_spec(
    project_root: Path,
    include_sources: bool = True,
) -> SpecContent:
    """
    Load product specification from project.

    Loading priority:
    1. spec/ directory - load all *.md files recursively
    2. SPEC.md - single file (backward compatible)
    3. Returns empty content if neither exists

    Args:
        project_root: Project root directory
        include_sources: Include source file markers in output

    Returns:
        SpecContent with combined content and metadata
    """
    spec_dir = project_root / "spec"
    spec_file = project_root / "SPEC.md"

    # Priority 1: spec/ directory
    if spec_dir.is_dir():
        return _load_from_directory(spec_dir, project_root, include_sources)

    # Priority 2: SPEC.md file
    if spec_file.is_file():
        return _load_from_file(spec_file, project_root, include_sources)

    # No spec found
    logger.debug(f"No specification found in {project_root}")
    return SpecContent(content="", source_files=[], source_type="none")


def _load_from_directory(
    spec_dir: Path,
    project_root: Path,
    include_sources: bool,
) -> SpecContent:
    """Load and concatenate all markdown files from spec directory."""
    # Find all markdown files recursively
    md_files = sorted(spec_dir.rglob("*.md"))

    if not md_files:
        logger.warning(f"spec/ directory exists but contains no .md files: {spec_dir}")
        return SpecContent(content="", source_files=[], source_type="directory")

    logger.info(f"Loading {len(md_files)} spec files from {spec_dir}")

    parts: list[str] = []
    for md_file in md_files:
        relative_path = md_file.relative_to(project_root)
        content = md_file.read_text().strip()

        if include_sources:
            parts.append(f"<!-- Source: {relative_path} -->")
            parts.append(content)
            parts.append("")  # Blank line between files
        else:
            parts.append(content)
            parts.append("")

    combined = "\n".join(parts).strip()

    return SpecContent(
        content=combined,
        source_files=md_files,
        source_type="directory",
    )


def _load_from_file(
    spec_file: Path,
    project_root: Path,
    include_sources: bool,
) -> SpecContent:
    """Load single SPEC.md file."""
    logger.info(f"Loading spec from {spec_file}")

    content = spec_file.read_text().strip()

    if include_sources:
        relative_path = spec_file.relative_to(project_root)
        content = f"<!-- Source: {relative_path} -->\n{content}"

    return SpecContent(
        content=content,
        source_files=[spec_file],
        source_type="single_file",
    )


def get_spec_summary(project_root: Path) -> dict[str, str | int | list[str]]:
    """
    Get a summary of spec files without loading full content.

    Useful for MCP tools that need to report spec status.

    Returns:
        Dict with source_type, file_count, and file_paths
    """
    spec_dir = project_root / "spec"
    spec_file = project_root / "SPEC.md"

    if spec_dir.is_dir():
        md_files = sorted(spec_dir.rglob("*.md"))
        return {
            "source_type": "directory",
            "file_count": len(md_files),
            "file_paths": [str(f.relative_to(project_root)) for f in md_files],
        }

    if spec_file.is_file():
        return {
            "source_type": "single_file",
            "file_count": 1,
            "file_paths": ["SPEC.md"],
        }

    return {
        "source_type": "none",
        "file_count": 0,
        "file_paths": [],
    }
