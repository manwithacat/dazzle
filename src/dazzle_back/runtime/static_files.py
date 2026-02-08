"""Combined static file serving from multiple directories.

Serves static files from project and framework directories, with project
files taking priority (first match wins). This enables project-level images
(e.g. hero-office.webp) to be served alongside framework assets (dz.js, dz.css).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from starlette.staticfiles import StaticFiles


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
