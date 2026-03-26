"""Content-hash fingerprinting for static assets.

Computes SHA-256 hashes of static files at startup and provides a Jinja2
filter that rewrites paths with the hash embedded in the filename:

    /static/css/dazzle-bundle.css → /static/css/dazzle-bundle.a1b2c3d4.css

The static file server recognises the hashed pattern and strips the hash
before serving, adding ``Cache-Control: immutable`` headers.

No build step required — hashes are computed at runtime on first access.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

# Matches a fingerprinted filename: name.HEXHASH.ext
# The hash is 8 hex chars (truncated SHA-256).
FINGERPRINT_RE = re.compile(r"^(.+)\.([0-9a-f]{8})(\.\w+)$")


def _hash_file(path: Path) -> str:
    """Return truncated SHA-256 hex digest (8 chars) for a file."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:8]


def build_asset_manifest(*static_dirs: Path) -> dict[str, str]:
    """Build a mapping of original paths to fingerprinted paths.

    Scans all CSS, JS, and SVG files in the given directories.
    Returns a dict like::

        {"css/dazzle-bundle.css": "css/dazzle-bundle.a1b2c3d4.css"}

    Args:
        static_dirs: One or more static asset directories to scan.

    Returns:
        Dict mapping relative original paths to fingerprinted paths.
    """
    manifest: dict[str, str] = {}
    extensions = {".css", ".js", ".svg"}

    for static_dir in static_dirs:
        if not static_dir.is_dir():
            continue
        for path in static_dir.rglob("*"):
            if path.suffix not in extensions:
                continue
            if path.is_dir():
                continue
            relative = path.relative_to(static_dir)
            fingerprint = _hash_file(path)
            stem = path.stem
            ext = path.suffix
            fingerprinted = relative.parent / f"{stem}.{fingerprint}{ext}"
            manifest[str(relative)] = str(fingerprinted)

    return manifest


def static_url_filter(path: str, manifest: dict[str, str]) -> str:
    """Jinja2 filter: rewrite a static path with its content hash.

    Usage in templates::

        <link rel="stylesheet" href="{{ 'css/dazzle-bundle.css' | static_url }}">
        <!-- outputs: /static/css/dazzle-bundle.a1b2c3d4.css -->

    Falls back to the original path if the file is not in the manifest.
    """
    # Strip /static/ prefix if present (templates may use full or relative paths)
    relative = path.removeprefix("/static/")
    fingerprinted = manifest.get(relative)
    if fingerprinted:
        return f"/static/{fingerprinted}"
    # Fallback: return original path unchanged
    return path if path.startswith("/") else f"/static/{path}"


def strip_fingerprint(path: str) -> str | None:
    """Strip the content hash from a fingerprinted filename.

    Returns the original filename if the path matches the fingerprint
    pattern, or None if it doesn't match.

    Example::

        strip_fingerprint("css/dazzle-bundle.a1b2c3d4.css")
        # → "css/dazzle-bundle.css"
    """
    match = FINGERPRINT_RE.match(path)
    if match:
        return f"{match.group(1)}{match.group(3)}"
    return None
