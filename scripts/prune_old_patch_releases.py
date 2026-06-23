#!/usr/bin/env python3
"""Prune patch tags + GitHub Releases older than N minor series.

Every push is tagged `vMAJOR.MINOR.PATCH` for deployment traceability, but that
accumulates thousands of patch tags/Releases. This keeps the public record tidy:
the **minor/major anchors** (`vX.Y.0`) are kept forever, and **patch** tags
(`vX.Y.Z`, Z>0) are removed once their minor series falls outside the most recent
``--keep-minors`` series (default 5). The underlying commits stay on ``main``
(never GC'd), so deleting a patch tag loses only the convenience pointer, not
history — and the tag→SHA backup written here makes even that recoverable.

Used two ways:
  * by ``.github/workflows/prune-old-releases.yml`` on each minor release (--execute)
  * once, by hand, for the retroactive cleanup of the existing backlog

Safe by default: prints the plan and writes a backup; pass ``--execute`` to delete.

    python scripts/prune_old_patch_releases.py                 # dry-run
    python scripts/prune_old_patch_releases.py --execute        # delete
    python scripts/prune_old_patch_releases.py --keep-minors 5  # window size
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _run(cmd: list[str], *, check: bool = True) -> str:
    return subprocess.run(cmd, check=check, capture_output=True, text=True).stdout


def _all_semver_tags() -> list[tuple[int, int, int, str]]:
    """Return (major, minor, patch, tag) for every `vX.Y.Z` tag, sorted ascending."""
    out = _run(["git", "tag"])
    parsed: list[tuple[int, int, int, str]] = []
    for tag in out.split():
        m = _TAG_RE.match(tag)
        if m:
            parsed.append((int(m[1]), int(m[2]), int(m[3]), tag))
    return sorted(parsed)


def _protected_minor_series(
    tags: list[tuple[int, int, int, str]], keep: int
) -> set[tuple[int, int]]:
    """The most-recent `keep` (major, minor) series — their patches are retained."""
    series = sorted({(maj, mn) for maj, mn, _, _ in tags}, reverse=True)
    return set(series[:keep])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--keep-minors", type=int, default=5, help="minor series to protect (default 5)"
    )
    ap.add_argument("--execute", action="store_true", help="actually delete (default: dry-run)")
    ap.add_argument(
        "--backup",
        default="prune-backup-tags.txt",
        help="where to write the tag→SHA backup before deleting",
    )
    args = ap.parse_args()

    tags = _all_semver_tags()
    if not tags:
        print("No vX.Y.Z tags found — nothing to do.")
        return 0

    protected = _protected_minor_series(tags, args.keep_minors)
    # Prune: patch tags (Z>0) whose (major, minor) is NOT in the protected window.
    # Minor/major anchors (Z==0) are kept forever.
    prune = [t for (maj, mn, patch, t) in tags if patch > 0 and (maj, mn) not in protected]
    kept_anchors = [t for (_, _, patch, t) in tags if patch == 0]

    print(f"Total semver tags:        {len(tags)}")
    print(f"Protected minor series:   {sorted(protected, reverse=True)}")
    print(f"Minor/major anchors kept: {len(kept_anchors)}")
    print(f"Patch tags to prune:      {len(prune)}")
    if prune:
        print(f"  e.g. {prune[:5]} … {prune[-3:]}")

    if not prune:
        return 0

    if not args.execute:
        print("\n[dry-run] pass --execute to delete the above. No changes made.")
        return 0

    # Backup the full tag→SHA map so any deleted tag can be re-created from its SHA.
    backup = _run(["git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/tags"])
    Path(args.backup).write_text(backup, encoding="utf-8")
    print(f"\nWrote tag→SHA backup to {args.backup} ({len(backup.splitlines())} tags).")

    failures = 0
    for i, tag in enumerate(prune, 1):
        # Delete the GitHub Release (if any) and the remote+local tag together.
        rel = subprocess.run(
            ["gh", "release", "delete", tag, "--yes", "--cleanup-tag"],
            capture_output=True,
            text=True,
        )
        if rel.returncode != 0:
            # No Release for this tag — delete the tag directly.
            d = subprocess.run(
                ["git", "push", "origin", "--delete", tag], capture_output=True, text=True
            )
            if d.returncode != 0:
                failures += 1
                print(f"  ✗ {tag}: {d.stderr.strip() or rel.stderr.strip()}")
                continue
        subprocess.run(["git", "tag", "-d", tag], capture_output=True, text=True)
        if i % 50 == 0:
            print(f"  … {i}/{len(prune)} pruned")

    print(f"\nDone: pruned {len(prune) - failures}/{len(prune)} patch tags ({failures} failures).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
