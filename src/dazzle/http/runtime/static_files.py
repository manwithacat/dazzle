"""Combined static file serving from multiple directories.

Serves static files from project and framework directories, with project
files taking priority (first match wins). This enables project-level images
(e.g. hero-office.webp) to be served alongside framework assets (dz.js, dz.css).

Adds Cache-Control headers to all static responses:
- Fingerprinted assets (content-hash filenames): 1 year, immutable
- Font assets: 1 year, immutable
- Other assets: 1 hour, public

Fingerprinted paths (e.g. ``dazzle-bundle.a1b2c3d4.css``) are resolved
back to the original filename before serving. No files are renamed on
disk — the hash is a virtual path segment.

With a fingerprinter wired (#1793), a stylesheet carrying absolute
``/static/...`` ``@import``s is served with those imports rewritten to their
hashed URLs, so every imported sheet is cached ``immutable`` under its own
content hash.
"""

import os
from pathlib import Path
from typing import Any

from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from dazzle.page.runtime.asset_fingerprint import (
    FINGERPRINT_RE,
    StaticFingerprinter,
    strip_fingerprint,
)

# Extensions unlikely to change between deploys
_IMMUTABLE_EXTENSIONS = frozenset({".woff2", ".woff", ".ttf", ".eot"})

# Default cache duration for non-fingerprinted assets (1 hour)
_DEFAULT_MAX_AGE = 3600

# Cache duration for fingerprinted/immutable assets (1 year)
_IMMUTABLE_MAX_AGE = 31536000


def static_cache_control(
    request_path: str,
    served_ext: str,
    *,
    active_development: bool = False,
    default_max_age: int | None = None,
) -> str:
    """Cache-Control for a static file, decided by the *requested* path.

    Un-hashed requests are never ``immutable`` (fonts aside) — only a URL
    carrying the content hash may be cached forever.
    """
    if active_development:
        # #1468: a site under active development serves everything
        # no-cache so each rebuild is picked up on the next load. The
        # content hash (when present) still guarantees byte-correctness;
        # no-cache just forces ETag revalidation → 304 when unchanged.
        # Checked first so even a stale fingerprinted URL from a prior
        # deploy revalidates instead of staying immutable.
        return "no-cache"
    is_fingerprinted = bool(FINGERPRINT_RE.search(os.path.basename(request_path)))
    if is_fingerprinted or served_ext.lower() in _IMMUTABLE_EXTENSIONS:
        return f"public, max-age={_IMMUTABLE_MAX_AGE}, immutable"
    if "/dist/" in request_path:
        # #1468 safety net: the framework runtime bundle requested at its
        # plain (non-fingerprinted) URL — i.e. from an HTML emission site
        # that hardcodes `/static/dist/...` instead of reading the
        # fingerprinted app-chrome URLs — must revalidate every load so a
        # deploy's JS/CSS fix is never served stale for hours.
        return "no-cache"
    max_age = _DEFAULT_MAX_AGE if default_max_age is None else default_max_age
    return f"public, max-age={max_age}"


class CombinedStaticFiles(StaticFiles):
    """Serve static files from multiple directories (first match wins).

    Directories are checked in order. The last directory in the list is used
    as the primary (fallback) directory passed to the parent StaticFiles class.
    Earlier directories are checked first, allowing project files to shadow
    framework files.

    Fingerprinted paths (``name.HASH.ext``) are transparently resolved to
    the original file and served with ``Cache-Control: immutable``.
    """

    def __init__(
        self,
        directories: list[Path],
        *,
        default_max_age: int | None = None,
        active_development: bool = False,
        fingerprinter: StaticFingerprinter | None = None,
        **kwargs: Any,
    ) -> None:
        self._extra_dirs = [d for d in directories[:-1] if d.is_dir()]
        # #1468: cache policy for NON-fingerprinted assets. Fingerprinted
        # (content-hashed) assets are always immutable regardless of these.
        self._default_max_age = _DEFAULT_MAX_AGE if default_max_age is None else default_max_age
        self._active_development = active_development
        # #1793: rewrites a served stylesheet's `/static/` @imports to hashed URLs.
        self._fingerprinter = fingerprinter
        primary = directories[-1] if directories else Path(".")
        super().__init__(directory=str(primary), **kwargs)

    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        """Check extra directories first, then fall back to the primary.

        If the path contains a content-hash fingerprint, try the original
        (unhashed) filename as a fallback.
        """
        # Try the path as-is first
        result = self._lookup_in_dirs(path)
        if result[1] is not None:
            return result

        # Try stripping the fingerprint: name.HASH.ext → name.ext
        original = strip_fingerprint(path.lstrip("/"))
        if original:
            result = self._lookup_in_dirs(original)
            if result[1] is not None:
                return result

        return super().lookup_path(path)

    def _lookup_in_dirs(self, path: str) -> tuple[str, os.stat_result | None]:
        """Look up a path in extra directories."""
        for d in self._extra_dirs:
            full = d / path.lstrip("/")
            try:
                stat = full.stat()
                return str(full), stat
            except (FileNotFoundError, PermissionError):
                continue
        return super().lookup_path(path)

    def file_response(
        self,
        full_path: Any,
        stat_result: os.stat_result,
        scope: Any,
        status_code: int = 200,
    ) -> Response:
        """Add Cache-Control headers; rewrite a stylesheet's ``/static/``
        ``@import``s to their hashed URLs when fingerprinting is on (#1793)."""
        response = super().file_response(full_path, stat_result, scope, status_code)
        if "cache-control" not in response.headers:
            response.headers["Cache-Control"] = static_cache_control(
                scope.get("path", "") if scope else "",
                os.path.splitext(str(full_path))[1],
                active_development=self._active_development,
                default_max_age=self._default_max_age,
            )
        fp = self._fingerprinter
        if fp is None or not fp.enabled or response.status_code != 200:
            return response
        path = Path(full_path)
        if path.suffix != ".css":
            return response
        text = path.read_text(encoding="utf-8", errors="replace")
        if "@import" not in text:
            return response
        return Response(
            fp.rewrite_css_imports(text),
            status_code=status_code,
            media_type="text/css; charset=utf-8",
            headers={
                "Cache-Control": response.headers["cache-control"],
                "ETag": f'"{fp.digest(path)}"',
            },
        )
