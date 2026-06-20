#!/usr/bin/env python3
"""Check for and download latest versions of vendored JS dependencies.

Every byte written to ``src/dazzle/page/runtime/static/vendor/`` by this
script also gets hashed and recorded in ``scripts/vendor_hashes.json``
via the helpers in ``vendor_manifest.py``. The companion drift gate in
``tests/unit/test_vendor_hash_drift.py`` then catches any divergence between
on-disk vendored files and the pinned manifest.

This script handles the **auto-update** subset (htmx core + 4 htmx
extensions, idiomorph, lucide). Other vendored files (Alpine, flatpickr,
tom-select, etc.) are vendored manually — use
``scripts/update_vendor_hashes.py`` after replacing them by hand.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

# Make the sibling vendor_manifest module importable when this script
# is invoked directly (`python scripts/update_vendors.py`).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from vendor_manifest import (  # noqa: E402
    VENDOR_DIR,
    hash_bytes,
    load_manifest,
    write_manifest,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

GITHUB_API = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
GITHUB_RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{tag}/{path}"

# In-memory copy of the manifest plus a running log of changes this run
# produced. Mutated by _save_vendor; flushed to disk at end of main().
# Lives at module scope because this is a one-shot CLI — no concurrency,
# no reentrancy, threading state through every update_<vendor> would
# obscure the actual download logic.
_MANIFEST: dict[str, str] | None = None
_CHANGES: list[tuple[str, str | None, str]] = []  # (filename, old, new)


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------


def _gh_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _assert_https(url: str) -> None:
    """Reject anything that isn't an https:// URL.

    All URLs in this script come from GitHub API responses or our own
    hardcoded constants; both should always be https. Defending against
    `file://`, `http://`, or other schemes — which urllib will happily
    open — costs one line and shuts the semgrep warning correctly.
    """
    if not url.startswith("https://"):
        raise ValueError(f"Refusing non-https URL: {url!r}")


def _gh_request(url: str) -> bytes:
    _assert_https(url)  # validates scheme — semgrep can't trace this
    req = urllib.request.Request(url, headers=_gh_headers())
    with urllib.request.urlopen(req) as resp:  # nosem
        return resp.read()


def _save_vendor(filename: str, data: bytes) -> None:
    """Write *data* to VENDOR_DIR/*filename* and update the manifest.

    Every vendored-file write goes through here so the manifest entry
    is updated atomically with the bytes on disk. Records the diff for
    end-of-run reporting (see _print_hash_diff).
    """
    assert _MANIFEST is not None, "_MANIFEST not initialised — call from main()"
    new_hash = hash_bytes(data)
    old_hash = _MANIFEST.get(filename)
    (VENDOR_DIR / filename).write_bytes(data)
    if old_hash != new_hash:
        _MANIFEST[filename] = new_hash
        _CHANGES.append((filename, old_hash, new_hash))


def _latest_stable_release(owner: str, repo: str, tag_prefix: str) -> dict:
    """Return the latest stable release whose tag starts with *tag_prefix*.

    Why this exists (not /releases/latest):
      - GitHub's /releases/latest sometimes returns a pre-release. htmx
        4.0.0-beta3 is currently marked prerelease=false despite the
        -beta3 suffix, which makes the bare prerelease flag unreliable
        on its own.
      - Auto-update PRs across a major version are higher-risk than
        the cron is designed for (assumes patch/minor on a stable
        major). Per-vendor major pin caps the blast radius.

    Filters applied here:
      - prerelease=true / draft=true → skip
      - tag contains '-' (catches -beta / -rc / -alpha) → skip
      - tag does not start with *tag_prefix* → skip

    Releases come back from /releases newest-first, so the first
    surviving entry is the latest stable within the major.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=30"
    releases = json.loads(_gh_request(url))
    for r in releases:
        if r.get("prerelease") or r.get("draft"):
            continue
        tag = r["tag_name"]
        if "-" in tag:  # belt-and-braces against mislabelled prereleases
            continue
        if not tag.startswith(tag_prefix):
            continue
        return r
    raise RuntimeError(
        f"No stable release found in {owner}/{repo} matching prefix {tag_prefix!r}. "
        f"Inspected {len(releases)} recent releases."
    )


def _download(url: str) -> bytes:
    _assert_https(url)  # validates scheme — semgrep can't trace this
    req = urllib.request.Request(url, headers=_gh_headers())
    with urllib.request.urlopen(req) as resp:  # nosem
        return resp.read()


# ---------------------------------------------------------------------------
# Version detection from installed files
# ---------------------------------------------------------------------------


def _read_head(path: Path, lines: int = 5) -> str:
    """Read the first *lines* of a file, or empty string if missing."""
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return "\n".join(text.splitlines()[:lines])


# htmx is manually pinned to a 4.x beta (shipped v0.83.0, #1405). Bump this
# together with the vendored htmx.min.js when moving to GA (#1409).
HTMX_PINNED_VERSION = "4.0.0-beta4"


def _detect_lucide_version() -> str | None:
    head = _read_head(VENDOR_DIR / "lucide.min.js", lines=5)
    m = re.search(r"lucide\s+v?(\d+\.\d+\.\d+)", head)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Dependency definitions
# ---------------------------------------------------------------------------


def _tag_version(tag: str) -> str:
    """Strip leading 'v' from a tag name."""
    return tag.lstrip("v")


def update_htmx(*, check_only: bool) -> None:
    """htmx is PINNED to a manually-vendored 4.x beta — auto-update is a no-op.

    htmx 2.0.9 → 4.0.0-beta4 shipped in v0.83.0 (#1405). The cron must NOT
    touch htmx:

    - ``_latest_stable_release`` deliberately skips pre-releases, so it cannot
      track v4 betas — and pointing it at ``v2.`` (as it used to) would
      *downgrade* the vendored beta back to htmx 2.x on the next run.
    - The beta → GA bump is a deliberate, browser-gated decision tracked in
      #1409, not something the cron should make.
    - All htmx-2 extension files were dropped in the migration (native morph /
      ``hx-status`` / ``hx-sse`` + Dazzle bridges replace them), so there is
      nothing to fetch — fetching the old set would resurrect deleted files
      and trip the vendor-hash drift gate.

    So this reports the pinned version and returns without downloading. When
    bumping to GA (#1409), update both the vendored ``htmx.min.js`` and
    ``HTMX_PINNED_VERSION`` together.
    """
    del check_only  # no-op regardless of dry-run
    print(
        f"htmx: pinned to {HTMX_PINNED_VERSION} (manually vendored; "
        "auto-update skipped, GA bump tracked in #1409)"
    )


# update_idiomorph removed in the htmx 4 migration (#1405): idiomorph-ext.min.js
# was dropped in favour of htmx 4's native innerMorph/outerMorph. The cron used
# to re-vendor it, which would resurrect the deleted file. (GA follow-up: #1409.)


def update_lucide(*, check_only: bool) -> None:
    """Update lucide icons.

    Pin: 0.x (no leading 'v' in lucide's tags). The 0.x → 1.x bump
    in May 2026 wants verification before adopting.
    """
    release = _latest_stable_release("lucide-icons", "lucide", "0.")
    tag = release["tag_name"]
    latest = _tag_version(tag)
    current = _detect_lucide_version()

    label = "lucide"
    if current == latest:
        print(f"{label}: {latest} (up to date)")
    else:
        print(f"{label}: {current or 'unknown'} -> {latest}")

    if check_only:
        return

    # Look for the iife build in release assets
    asset_url = None
    for asset in release.get("assets", []):
        name = asset["name"]
        if "iife" in name and name.endswith(".js") and "min" in name:
            asset_url = asset["browser_download_url"]
            break

    if not asset_url:
        # Fallback: try lucide.iife.min.js directly
        for asset in release.get("assets", []):
            if asset["name"] in ("lucide.iife.min.js", "lucide.iife.js"):
                asset_url = asset["browser_download_url"]
                break

    if asset_url:
        data = _download(asset_url)
        _save_vendor("lucide.min.js", data)
        print("  downloaded lucide.min.js")
    else:
        print("  WARNING: could not find lucide iife asset in release")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _print_hash_diff() -> None:
    """Emit a structured per-file hash diff for capture into the PR body.

    The leading sentinel ``=== VENDOR_HASH_DIFF ===`` lets the workflow
    (or any other consumer) sed the section out without parsing the
    rest of the run's stdout. Format is deliberately Markdown so the
    PR-create step can drop it straight in.
    """
    if not _CHANGES:
        print("\nNo vendored bytes changed; manifest left untouched.")
        return

    print("\n=== VENDOR_HASH_DIFF ===")
    print("## Vendor hash changes\n")
    print(
        "Each entry below is a SHA-256 of the downloaded bytes vs the "
        "previously-pinned hash. Verify each `new` against an independent "
        "source (the upstream release page, a separate download, npm "
        "provenance, etc.) before merging.\n"
    )
    print("| File | old sha256 | new sha256 |")
    print("|------|------------|------------|")
    for filename, old, new in _CHANGES:
        old_short = old.removeprefix("sha256:")[:12] if old else "(new file)"
        new_short = new.removeprefix("sha256:")[:12]
        print(f"| `{filename}` | `{old_short}` | `{new_short}` |")
    print("=== /VENDOR_HASH_DIFF ===")


def main() -> None:
    global _MANIFEST

    check_only = "--check" in sys.argv
    _MANIFEST = load_manifest()

    if check_only:
        print("Checking for updates (dry run)...\n")
    else:
        print("Updating vendored dependencies...\n")

    update_htmx(check_only=check_only)
    update_lucide(check_only=check_only)

    if check_only:
        print("\nRun without --check to download updates.")
        return

    # Atomic commit: vendored bytes are already on disk; persist the
    # manifest changes so the drift gate accepts the new state on the
    # very next test run.
    if _CHANGES:
        write_manifest(_MANIFEST)
    _print_hash_diff()
    print("\nDone.")


if __name__ == "__main__":
    main()
