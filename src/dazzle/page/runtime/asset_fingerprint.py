"""Content-hash fingerprinting for static assets.

Computes SHA-256 hashes of static files and rewrites their URLs with the
hash embedded in the filename:

    /static/dist/dazzle.min.js → /static/dist/dazzle.min.a1b2c3d4.js

The static file server (``CombinedStaticFiles``) recognises the hashed
pattern, strips the hash to find the real file on disk, and serves it with
``Cache-Control: immutable``. A deploy that changes the bundle changes its
hash → a new URL → returning visitors fetch the fix immediately instead of
running the cached old bundle until ``max-age`` expires (#1468; the framework
runtime bundle has the worst propagation of any asset class otherwise).

Gated on environment (``should_fingerprint``): on in production/staging,
off in dev/test (plain URLs, fast iteration) and when a project sets
``[ui] active_development = true`` (a deployed site that wants no-cache
iteration instead of immutable fingerprints).

No build step required — hashes are computed once per process (a deploy is a
new process, so the cache is always fresh for the bytes being served).
"""

import functools
import hashlib
import os
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


# ---------------------------------------------------------------------------
# Framework runtime-bundle fingerprinting (#1468)
# ---------------------------------------------------------------------------


def should_fingerprint(*, active_development: bool = False, env: str | None = None) -> bool:
    """Whether framework asset URLs should carry content-hash fingerprints.

    On in production/staging — returning visitors must receive a JS/CSS fix
    the instant it deploys, not after the bundle's ``max-age`` expires (#1468).
    Off in dev/test (plain ``/static/dist/...`` URLs — fast iteration, stable
    test assertions) and whenever a project opts into ``[ui]
    active_development = true`` (a deployed site that prefers ``no-cache``
    iteration over immutable fingerprints).

    Mirrors :func:`dazzle.page.runtime.asset_bundle.should_bundle_assets`'s
    environment gate so bundling and fingerprinting turn on together.
    """
    if active_development:
        return False
    resolved = env if env is not None else os.environ.get("DAZZLE_ENV", "")
    return resolved in ("production", "staging")


def _framework_static_root() -> Path:
    """The framework's served static dir (``page/runtime/static``)."""
    return Path(__file__).parent / "static"


@functools.cache
def _framework_manifest() -> dict[str, str]:
    """Content-hash manifest for the framework static dir (built once/process).

    A deploy is a new process, so a process-lifetime cache always reflects the
    bytes being served. Cleared in tests via ``_framework_manifest.cache_clear()``.
    """
    return build_asset_manifest(_framework_static_root())


def fingerprint_static_url(url: str, *, active_development: bool = False) -> str:
    """Rewrite a framework ``/static/<rel>`` URL to its content-hashed form.

    ``/static/dist/dazzle.min.js`` → ``/static/dist/dazzle.min.a1b2c3d4.js``.
    Returns the URL unchanged when fingerprinting is off (dev/test/active
    development), when the URL isn't a ``/static/`` framework asset, or when
    the asset isn't in the framework manifest (e.g. project-supplied or theme
    overrides) — the server serves those at the configured ``max-age`` instead.
    """
    if not should_fingerprint(active_development=active_development):
        return url
    if not url.startswith("/static/"):
        return url
    rel = url.removeprefix("/static/")
    fingerprinted = _framework_manifest().get(rel)
    return f"/static/{fingerprinted}" if fingerprinted else url


def fingerprint_urls(urls: tuple[str, ...], *, active_development: bool = False) -> tuple[str, ...]:
    """Fingerprint every framework ``/static/`` URL in a tuple (order-preserving)."""
    return tuple(fingerprint_static_url(u, active_development=active_development) for u in urls)
