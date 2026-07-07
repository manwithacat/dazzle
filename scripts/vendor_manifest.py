"""Shared helpers for the vendored-JS hash manifest.

The manifest at ``scripts/vendor_hashes.json`` pins a SHA-256 of every
file under ``src/dazzle/page/runtime/static/vendor/``. It is consulted by:

  - ``tests/unit/test_vendor_hash_drift.py`` — drift gate; fails CI if any
    on-disk file diverges from the manifest. This is the layer that
    catches tampering with files between scheduled auto-updates.

  - ``scripts/update_vendors.py`` — atomic update path; recomputes the
    hash after downloading each file and rewrites the manifest entry
    in the same commit as the vendored file.

  - ``scripts/update_vendor_hashes.py`` — manual rebuild for files
    outside the auto-update set (Alpine, flatpickr, tom-select, etc.).
    Run after replacing a vendored file by hand.

Design choices:

  - SHA-256 hex digest with an explicit ``sha256:`` prefix in case we
    ever need to rotate algorithms without ambiguity.

  - Manifest is JSON (machine-friendly) and committed to the repo —
    the *expected* hashes are part of the source-controlled trust
    boundary, not a side-channel.

  - Schema-aware: the top-level has ``_schema`` documenting purpose
    and algorithm, and ``files`` with the actual hash entries. Tests
    only read ``files``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Resolves the repo root regardless of where this module is imported from.
REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = REPO_ROOT / "src" / "dazzle" / "page" / "runtime" / "static" / "vendor"
MANIFEST_PATH = REPO_ROOT / "scripts" / "vendor_hashes.json"

HASH_PREFIX = "sha256:"


def hash_bytes(data: bytes) -> str:
    """Return the manifest-format hash for *data*."""
    return HASH_PREFIX + hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    """Return the manifest-format hash for the contents of *path*."""
    return hash_bytes(path.read_bytes())


def load_manifest() -> dict[str, str]:
    """Return the ``files`` map from the manifest (filename -> hash).

    Raises if the manifest is missing or malformed — both are real bugs
    we want to fail loudly on, not silently degrade.
    """
    raw = json.loads(MANIFEST_PATH.read_text())
    files = raw.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"{MANIFEST_PATH} has no 'files' map")
    return files


def write_manifest(files: dict[str, str]) -> None:
    """Rewrite the manifest with *files* as the new entries map.

    Preserves the ``_schema`` block (description + algorithm) and sorts
    entries by filename so diffs stay readable.
    """
    raw = json.loads(MANIFEST_PATH.read_text())
    raw["files"] = dict(sorted(files.items()))
    MANIFEST_PATH.write_text(json.dumps(raw, indent=2) + "\n")


def discover_vendor_files() -> list[Path]:
    """Every .js/.css file currently in the vendor dir, sorted."""
    # rglob: vendored libraries may live in subdirectories (pdfjs/);
    # .mjs joined the set with the PDF.js ES-module build (hx-pdf P3).
    return sorted(
        p for p in VENDOR_DIR.rglob("*") if p.is_file() and p.suffix in (".js", ".css", ".mjs")
    )


def compute_current_hashes() -> dict[str, str]:
    """Hash every file currently under VENDOR_DIR, keyed by filename."""
    return {str(p.relative_to(VENDOR_DIR)): hash_file(p) for p in discover_vendor_files()}
