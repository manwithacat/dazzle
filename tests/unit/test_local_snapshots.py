"""Local snapshot hygiene — no nested .dazzle/spec_snapshots (storage trim)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.local_snapshots import (
    any_nested_snapshots,
    copy_project_material,
    has_nested_spec_snapshots,
    list_snapshot_ids,
    prune_snapshots,
    remove_all_snapshots,
    snapshots_root,
)


def _touch_tree(root: Path, *parts: str) -> Path:
    path = root.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    return path


def test_copy_project_material_excludes_dazzle_and_junk(tmp_path: Path) -> None:
    src = tmp_path / "proj"
    (src / "dsl").mkdir(parents=True)
    (src / "dsl" / "app.dsl").write_text("app Foo:\n", encoding="utf-8")
    (src / "src" / "pkg").mkdir(parents=True)
    (src / "src" / "pkg" / "m.py").write_text("x=1\n", encoding="utf-8")
    # Would recurse if copied:
    nest = src / ".dazzle" / "spec_snapshots" / "old-id"
    nest.mkdir(parents=True)
    (nest / "junk.txt").write_text("boom", encoding="utf-8")
    (src / ".git" / "objects").mkdir(parents=True)
    (src / ".git" / "objects" / "x").write_text("g", encoding="utf-8")
    (src / ".venv" / "lib").mkdir(parents=True)
    (src / "node_modules" / "pkg").mkdir(parents=True)
    (src / "__pycache__").mkdir()
    (src / "tmp" / "scratch").mkdir(parents=True)

    dest = tmp_path / "snap"
    copy_project_material(src, dest)

    assert (dest / "dsl" / "app.dsl").is_file()
    assert (dest / "src" / "pkg" / "m.py").is_file()
    assert not (dest / ".dazzle").exists()
    assert not (dest / ".git").exists()
    assert not (dest / ".venv").exists()
    assert not (dest / "node_modules").exists()
    assert not (dest / "__pycache__").exists()
    assert not (dest / "tmp").exists()
    assert not has_nested_spec_snapshots(dest)


def test_two_copies_never_nest_spec_snapshots(tmp_path: Path) -> None:
    """Regression: creating multiple snapshots must stay flat (no nested path)."""
    src = tmp_path / "proj"
    (src / "dsl").mkdir(parents=True)
    (src / "dsl" / "a.dsl").write_text("app A:\n", encoding="utf-8")
    # Prior local state that must never be mirrored into a new snapshot
    prior = src / ".dazzle" / "spec_snapshots" / "prior"
    prior.mkdir(parents=True)
    (prior / "dsl" / "old.dsl").parent.mkdir(parents=True)
    (prior / "dsl" / "old.dsl").write_text("app Old:\n", encoding="utf-8")

    snap_root = snapshots_root(src)
    for i in range(2):
        dest = snap_root / f"id-{i}"
        # Mimic a correct writer: material goes under the snapshot id, never
        # including .dazzle from src.
        copy_project_material(src, dest)

    # "prior" is leftover local state under src; new snaps are id-0/id-1 only.
    assert set(list_snapshot_ids(src)) >= {"id-0", "id-1"}
    for sid in ("id-0", "id-1"):
        path = snap_root / sid
        assert not has_nested_spec_snapshots(path)
        # No path segment pair …/spec_snapshots/…/spec_snapshots/…
        parts = path.joinpath("dsl", "a.dsl").parts
        assert parts.count("spec_snapshots") == 1
        # Prior mirror was not re-copied into the new snapshot.
        assert not (path / "dsl" / "old.dsl").exists()
    assert "id-0" not in any_nested_snapshots(src)
    assert "id-1" not in any_nested_snapshots(src)


def test_prune_keeps_newest(tmp_path: Path) -> None:
    root = snapshots_root(tmp_path)
    root.mkdir(parents=True)
    for name in ("a", "b", "c"):
        d = root / name
        d.mkdir()
        (d / "f.txt").write_text(name, encoding="utf-8")
    # Bump mtimes so c is newest, then b, then a
    import os
    import time

    now = time.time()
    os.utime(root / "a", (now - 30, now - 30))
    os.utime(root / "b", (now - 20, now - 20))
    os.utime(root / "c", (now - 10, now - 10))

    report = prune_snapshots(tmp_path, keep=2, dry_run=False)
    assert set(report.kept) == {"b", "c"}
    assert report.removed == ["a"]
    assert list_snapshot_ids(tmp_path) == ["b", "c"]


def test_prune_dry_run_does_not_delete(tmp_path: Path) -> None:
    root = snapshots_root(tmp_path)
    (root / "only").mkdir(parents=True)
    report = prune_snapshots(tmp_path, keep=0, dry_run=True)
    assert report.removed == ["only"]
    assert (root / "only").is_dir()


def test_remove_all(tmp_path: Path) -> None:
    root = snapshots_root(tmp_path)
    nested = root / "top" / ".dazzle" / "spec_snapshots" / "inner"
    nested.mkdir(parents=True)
    (nested / "x.txt").write_text("n", encoding="utf-8")
    assert any_nested_snapshots(tmp_path) == ["top"]

    report = remove_all_snapshots(tmp_path, dry_run=False)
    assert "top" in report.removed
    assert not root.exists()


def test_copy_refuses_existing_dest(tmp_path: Path) -> None:
    src = tmp_path / "s"
    dest = tmp_path / "d"
    src.mkdir()
    dest.mkdir()
    with pytest.raises(FileExistsError):
        copy_project_material(src, dest)
