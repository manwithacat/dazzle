"""Combined static file serving from multiple directories.

Serves static files from project and framework directories, with project
files taking priority (first match wins). This enables project-level images
(e.g. hero-office.webp) to be served alongside framework assets (dz.js, dz.css).

Adds Cache-Control headers to all static responses:
- Fingerprinted assets (containing hash-like segments): 1 year, immutable
- Other assets: 1 hour, public
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from starlette.responses import Response
from starlette.staticfiles import StaticFiles

# Extensions unlikely to change between deploys
_IMMUTABLE_EXTENSIONS = frozenset({".woff2", ".woff", ".ttf", ".eot"})

# Default cache duration for non-fingerprinted assets (1 hour)
_DEFAULT_MAX_AGE = 3600

# Cache duration for fingerprinted/immutable assets (1 year)
_IMMUTABLE_MAX_AGE = 31536000


class CombinedStaticFiles(StaticFiles):
    """Serve static files from multiple directories (first match wins).

    Directories are checked in order. The last directory in the list is used
    as the primary (fallback) directory passed to the parent StaticFiles class.
    Earlier directories are checked first, allowing project files to shadow
    framework files.
    """

    def __init__(self, directories: list[Path], **kwargs: Any) -> None:
        self._extra_dirs = [d for d in directories[:-1] if d.is_dir()]
        primary = directories[-1] if directories else Path(".")
        super().__init__(directory=str(primary), **kwargs)

    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        """Check extra directories first, then fall back to the primary."""
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
        """Add Cache-Control headers to static file responses."""
        response = super().file_response(full_path, stat_result, scope, status_code)
        if "cache-control" not in response.headers:
            ext = os.path.splitext(str(full_path))[1].lower()
            if ext in _IMMUTABLE_EXTENSIONS:
                response.headers["Cache-Control"] = (
                    f"public, max-age={_IMMUTABLE_MAX_AGE}, immutable"
                )
            else:
                response.headers["Cache-Control"] = f"public, max-age={_DEFAULT_MAX_AGE}"
        return response
