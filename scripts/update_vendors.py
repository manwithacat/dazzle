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
VENDOR_DIR = REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "vendor"

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


def _gh_request(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_gh_headers())
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def _latest_release(owner: str, repo: str) -> dict:
    url = GITHUB_API.format(owner=owner, repo=repo)
    return json.loads(_gh_request(url))


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_gh_headers())
    with urllib.request.urlopen(req) as resp:
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
    """Update htmx core and extensions."""
    release = _latest_release("bigskysoftware", "htmx")
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
    """Update idiomorph extension."""
    release = _latest_release("bigskysoftware", "idiomorph")
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
    """Update lucide icons."""
    release = _latest_release("lucide-icons", "lucide")
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
