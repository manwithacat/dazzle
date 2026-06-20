"""CI drift gate for vendored JS/CSS.

For every file under ``src/dazzle/page/runtime/static/vendor/``, recompute
the SHA-256 and assert it matches the value pinned in
``scripts/vendor_hashes.json``.

What this catches:

  - Tampering with vendored files between scheduled auto-update PRs.
    Most vendored files (Alpine.js, flatpickr, tom-select, etc.) are
    not auto-updated — without this gate, a malicious change to them
    would only surface in a code review of a vendor-update PR, and
    only for the few files the auto-updater touches.

  - Auto-update PRs that forgot to refresh the manifest. The script
    rewrites entries atomically, but if someone hand-edits a vendored
    file outside the update flow this gate catches the drift.

Recovering when this fails:

  - **You deliberately updated a vendored file**: run
    ``python scripts/update_vendor_hashes.py``, which rebuilds the
    manifest entries to match disk, then commit both files together.

  - **You didn't expect any change**: someone (or something) altered
    a vendored file. Investigate before regenerating.

Listed in ``.claude/commands/ship.md`` so /ship runs it pre-push.
"""

from __future__ import annotations

import sys
from pathlib import Path

# `scripts/` is not a package and not on pytest's pythonpath (which is
# `["src"]`). Bootstrap it locally so this test can share helpers with
# update_vendors.py + update_vendor_hashes.py — keeps a single source
# of truth for hashing + manifest I/O.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import pytest  # noqa: E402
from vendor_manifest import (  # noqa: E402
    compute_current_hashes,
    discover_vendor_files,
    load_manifest,
)


def test_every_vendor_file_has_manifest_entry() -> None:
    """No file in vendor/ may exist without a pinned hash.

    A new vendored file added to disk without a manifest update is a
    sign of either an in-progress vendor addition (commit the manifest)
    or unintended state (investigate).
    """
    manifest = load_manifest()
    disk_files = {p.name for p in discover_vendor_files()}
    missing = sorted(disk_files - set(manifest))
    assert not missing, (
        f"Vendored files without a pinned hash: {missing}. "
        f"Run `python scripts/update_vendor_hashes.py` to add entries."
    )


def test_no_manifest_entry_without_file() -> None:
    """Conversely: no stale manifest entry pointing at a removed file."""
    manifest = load_manifest()
    disk_files = {p.name for p in discover_vendor_files()}
    stale = sorted(set(manifest) - disk_files)
    assert not stale, (
        f"Manifest entries for files no longer present: {stale}. "
        f"Run `python scripts/update_vendor_hashes.py` to prune."
    )


@pytest.mark.parametrize("filename", sorted(load_manifest()))
def test_vendor_file_matches_pinned_hash(filename: str) -> None:
    """The on-disk hash of every vendored file must match the manifest.

    Parametrised so a failure names the specific file that drifted —
    not a generic dict-equality dump.
    """
    manifest = load_manifest()
    current = compute_current_hashes()
    expected = manifest[filename]
    actual = current[filename]
    assert actual == expected, (
        f"{filename} has drifted from its pinned hash.\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}\n"
        f"  If this change is deliberate, run "
        f"`python scripts/update_vendor_hashes.py` and commit the "
        f"manifest diff alongside the file."
    )
