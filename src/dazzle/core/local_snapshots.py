"""Local (gitignored) project snapshot hygiene under ``.dazzle/spec_snapshots/``.

Historical context
------------------
Ops ``RollbackManager`` (retired ADR-0051) wrote DSL-only snapshots to
``.dazzle/spec_snapshots/<id>/``. Some environments also accumulated
**full-tree** mirrors that nested prior ``.dazzle/spec_snapshots`` copies
(exponential file counts; unusable for rsync backups).

There is **no active product writer** on mainline after ADR-0051. This
module still provides:

1. A shared **copy ignore** for any future snapshot writer (must exclude
   ``.dazzle/``, ``.git/``, venvs, caches).
2. **List / prune / remove** so operators can reclaim disk without hunting
   paths.
3. Nest detection for doctor / tests.

CLI: ``dazzle clean snapshots`` (see ``dazzle.cli.clean``).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

SPEC_SNAPSHOTS_REL = Path(".dazzle") / "spec_snapshots"
DEFAULT_KEEP = 10

# Directory / file names never copied into a project material snapshot.
# Used by :func:`ignore_for_copytree` and documented for operators.
SNAPSHOT_COPY_EXCLUDE_NAMES: frozenset[str] = frozenset(
    {
        ".dazzle",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".hypothesis",
        ".import_linter_cache",
        "htmlcov",
        "coverage_html",
        ".coverage",
        ".DS_Store",
        "tmp",
        ".tox",
        ".nox",
        "dist",
        "build",
        ".eggs",
        "*.egg-info",
    }
)


def snapshots_root(project_root: Path | None = None) -> Path:
    """Return ``{project}/.dazzle/spec_snapshots``."""
    root = Path(project_root or Path.cwd()).resolve()
    return root / SPEC_SNAPSHOTS_REL


def ignore_for_copytree(
    extra_names: Iterable[str] | None = None,
) -> Callable[[str, list[str]], set[str]]:
    """``shutil.copytree`` ignore callable — never copy local state / junk.

    Always excludes ``.dazzle`` so snapshots cannot nest prior snapshots.
    """
    excluded = set(SNAPSHOT_COPY_EXCLUDE_NAMES)
    if extra_names:
        excluded.update(extra_names)

    def _ignore(directory: str, names: list[str]) -> set[str]:
        skipped: set[str] = set()
        for name in names:
            if name in excluded:
                skipped.add(name)
                continue
            # egg-info style
            if name.endswith(".egg-info"):
                skipped.add(name)
        return skipped

    return _ignore


def copy_project_material(
    src: Path,
    dest: Path,
    *,
    extra_exclude: Iterable[str] | None = None,
) -> None:
    """Copy project material into ``dest`` using the shared exclude set.

    Prefer this over raw ``copytree`` for any new snapshot / mirror writer.
    ``dest`` must not already exist (``copytree`` default).
    """
    src = Path(src).resolve()
    dest = Path(dest)
    if dest.exists():
        raise FileExistsError(f"snapshot destination already exists: {dest}")
    shutil.copytree(src, dest, ignore=ignore_for_copytree(extra_exclude))


def list_snapshot_ids(project_root: Path | None = None) -> list[str]:
    """Top-level snapshot directory names (sorted)."""
    root = snapshots_root(project_root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def has_nested_spec_snapshots(snapshot_dir: Path) -> bool:
    """True if ``snapshot_dir`` contains a nested ``.dazzle/spec_snapshots`` tree."""
    nested = Path(snapshot_dir) / ".dazzle" / "spec_snapshots"
    return nested.is_dir()


def any_nested_snapshots(project_root: Path | None = None) -> list[str]:
    """Ids of top-level snapshots that contain nested ``spec_snapshots`` (shallow)."""
    root = snapshots_root(project_root)
    bad: list[str] = []
    if not root.is_dir():
        return bad
    for child in root.iterdir():
        if child.is_dir() and has_nested_spec_snapshots(child):
            bad.append(child.name)
    return sorted(bad)


@dataclass
class CleanReport:
    """Result of a prune or remove operation."""

    root: Path
    removed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    dry_run: bool = False
    nested_before: list[str] = field(default_factory=list)

    @property
    def removed_count(self) -> int:
        return len(self.removed)


def prune_snapshots(
    project_root: Path | None = None,
    *,
    keep: int = DEFAULT_KEEP,
    dry_run: bool = False,
) -> CleanReport:
    """Keep the newest ``keep`` top-level snapshot dirs; delete the rest.

    Newest is by directory mtime (local filesystem). Nested explosion inside a
    kept snapshot is **not** rewritten — use :func:`remove_all_snapshots` for
    full reclaim after a recursive mess.
    """
    if keep < 0:
        raise ValueError("keep must be >= 0")
    root = snapshots_root(project_root)
    nested = any_nested_snapshots(project_root)
    if not root.is_dir():
        return CleanReport(root=root, dry_run=dry_run, nested_before=nested)

    children = [p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]
    children.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    keep_list = children[:keep] if keep else []
    drop_list = children[keep:] if keep else children

    report = CleanReport(
        root=root,
        kept=[p.name for p in keep_list],
        removed=[p.name for p in drop_list],
        dry_run=dry_run,
        nested_before=nested,
    )
    if not dry_run:
        for path in drop_list:
            shutil.rmtree(path, ignore_errors=False)
    return report


def remove_all_snapshots(
    project_root: Path | None = None,
    *,
    dry_run: bool = False,
) -> CleanReport:
    """Delete the entire ``.dazzle/spec_snapshots`` tree (safe high-ROI reclaim).

    Uses ``rm -rf`` when available — nested explosion can reach millions of
    inodes where ``shutil.rmtree`` is impractically slow.
    """
    import subprocess

    root = snapshots_root(project_root)
    nested = any_nested_snapshots(project_root)
    ids = list_snapshot_ids(project_root)
    report = CleanReport(
        root=root,
        removed=ids if root.is_dir() else [],
        kept=[],
        dry_run=dry_run,
        nested_before=nested,
    )
    if not dry_run and root.exists():
        # Prefer platform rm for deep trees (nested mirrors).
        try:
            subprocess.run(
                ["rm", "-rf", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            shutil.rmtree(root, ignore_errors=False)
    return report


__all__ = [
    "DEFAULT_KEEP",
    "SNAPSHOT_COPY_EXCLUDE_NAMES",
    "SPEC_SNAPSHOTS_REL",
    "CleanReport",
    "any_nested_snapshots",
    "copy_project_material",
    "has_nested_spec_snapshots",
    "ignore_for_copytree",
    "list_snapshot_ids",
    "prune_snapshots",
    "remove_all_snapshots",
    "snapshots_root",
]
