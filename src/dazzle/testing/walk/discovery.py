"""Discover scene walk YAML under a project root (#1638)."""

from __future__ import annotations

from pathlib import Path

# Relative to project root (directory containing dazzle.toml).
DEFAULT_WALKS_SUBDIR = Path("fixtures") / "scene_walks"


def default_walks_dir(project_root: Path) -> Path:
    """``{project}/fixtures/scene_walks``."""
    return project_root.resolve() / DEFAULT_WALKS_SUBDIR


def discover_walk_paths(
    project_root: Path,
    *,
    walks_dir: Path | None = None,
) -> list[Path]:
    """Return sorted ``*.yaml`` / ``*.yml`` paths under the walks directory.

    Missing directory → empty list (not an error). Non-directory path → empty.
    """
    root = (walks_dir if walks_dir is not None else default_walks_dir(project_root)).resolve()
    if not root.is_dir():
        return []
    paths = sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml"))
    # de-dupe while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out
