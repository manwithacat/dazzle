#!/usr/bin/env python3
"""Check for and download latest versions of vendored JS dependencies."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = REPO_ROOT / "src" / "dazzle" / "ui" / "runtime" / "static" / "vendor"

GITHUB_API = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
GITHUB_RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{tag}/{path}"


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


def _detect_htmx_version() -> str | None:
    head = _read_head(VENDOR_DIR / "htmx.min.js", lines=3)
    # htmx embeds version as: version:"2.0.8"  or  htmx.org@v2.0.8
    m = re.search(r'version["\s:]+["\']?v?(\d+\.\d+\.\d+)', head)
    if m:
        return m.group(1)
    m = re.search(r"htmx\.org@v?(\d+\.\d+\.\d+)", head)
    if m:
        return m.group(1)
    return None


def _detect_lucide_version() -> str | None:
    head = _read_head(VENDOR_DIR / "lucide.min.js", lines=5)
    m = re.search(r"lucide\s+v?(\d+\.\d+\.\d+)", head)
    if m:
        return m.group(1)
    return None


def _detect_idiomorph_version() -> str | None:
    head = _read_head(VENDOR_DIR / "idiomorph-ext.min.js", lines=5)
    m = re.search(r"[Ii]diomorph\s+v?(\d+\.\d+\.\d+)", head)
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
    """Update htmx core and extensions.

    Pin: htmx v2.x. v4 reorganised dist/ext/ and warrants a deliberate
    migration; the cron isn't the right place for that decision.
    """
    release = _latest_stable_release("bigskysoftware", "htmx", "v2.")
    tag = release["tag_name"]
    latest = _tag_version(tag)
    current = _detect_htmx_version()

    label = "htmx"
    if current == latest:
        print(f"{label}: {latest} (up to date)")
    else:
        print(f"{label}: {current or 'unknown'} -> {latest}")

    if check_only:
        return

    # Download htmx.min.js from release assets
    asset_url = None
    for asset in release.get("assets", []):
        if asset["name"] == "htmx.min.js":
            asset_url = asset["browser_download_url"]
            break

    if asset_url:
        data = _download(asset_url)
        (VENDOR_DIR / "htmx.min.js").write_bytes(data)
    else:
        # Fallback: download from dist/ on the tag
        url = GITHUB_RAW.format(
            owner="bigskysoftware", repo="htmx", tag=tag, path="dist/htmx.min.js"
        )
        data = _download(url)
        (VENDOR_DIR / "htmx.min.js").write_bytes(data)

    # Extensions from dist/ext/ on the release tag
    extensions = {
        "json-enc.js": "htmx-ext-json-enc.js",
        "preload.js": "htmx-ext-preload.js",
        "response-targets.js": "htmx-ext-response-targets.js",
        "loading-states.js": "htmx-ext-loading-states.js",
        "sse.js": "htmx-ext-sse.js",
    }
    for src_name, dest_name in extensions.items():
        url = GITHUB_RAW.format(
            owner="bigskysoftware", repo="htmx", tag=tag, path=f"dist/ext/{src_name}"
        )
        data = _download(url)
        (VENDOR_DIR / dest_name).write_bytes(data)
        print(f"  downloaded {dest_name}")


def update_idiomorph(*, check_only: bool) -> None:
    """Update idiomorph extension.

    Pin: 0.7.x. 0.x semver treats the minor as the breaking-change
    axis, so jumping to 0.8 should also be intentional.
    """
    release = _latest_stable_release("bigskysoftware", "idiomorph", "v0.7.")
    tag = release["tag_name"]
    latest = _tag_version(tag)
    current = _detect_idiomorph_version()

    label = "idiomorph"
    if current == latest:
        print(f"{label}: {latest} (up to date)")
    else:
        print(f"{label}: {current or 'unknown'} -> {latest}")

    if check_only:
        return

    url = GITHUB_RAW.format(
        owner="bigskysoftware",
        repo="idiomorph",
        tag=tag,
        path="dist/idiomorph-ext.min.js",
    )
    data = _download(url)
    (VENDOR_DIR / "idiomorph-ext.min.js").write_bytes(data)
    print("  downloaded idiomorph-ext.min.js")


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
        (VENDOR_DIR / "lucide.min.js").write_bytes(data)
        print("  downloaded lucide.min.js")
    else:
        print("  WARNING: could not find lucide iife asset in release")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    check_only = "--check" in sys.argv

    if check_only:
        print("Checking for updates (dry run)...\n")
    else:
        print("Updating vendored dependencies...\n")

    update_htmx(check_only=check_only)
    update_idiomorph(check_only=check_only)
    update_lucide(check_only=check_only)

    if check_only:
        print("\nRun without --check to download updates.")
    else:
        print("\nDone.")


if __name__ == "__main__":
    main()
