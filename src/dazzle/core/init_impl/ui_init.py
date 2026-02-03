"""
UI generation from DSL (stub).

The Vite/DNR-UI generation pipeline has been removed. Dazzle now uses
Jinja2/HTMX server-rendered templates exclusively. This module is kept
as a no-op for backward compatibility with callers that invoke generate_ui().
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def generate_ui(
    project_dir: Path,
    log: Callable[[str], None] | None = None,
) -> bool:
    """
    Generate UI artifacts from the project's DSL.

    This is a no-op — the Vite/DNR-UI pipeline has been removed.
    Dazzle now uses Jinja2/HTMX server-rendered templates via
    ``dazzle serve``.

    Args:
        project_dir: Project directory containing dazzle.toml and dsl/
        log: Optional logging callback

    Returns:
        False (no generation performed)
    """
    if log is None:
        log = lambda msg: None  # noqa: E731

    log("  Skipping dnr-ui generation (removed — use dazzle serve)")
    return False
