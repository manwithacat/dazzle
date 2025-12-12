"""
DAZZLE - Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps.

A DSL-first toolkit for designing and generating applications from
high-level specifications.
"""

from __future__ import annotations

import re
from importlib.metadata import version as _metadata_version
from pathlib import Path as _Path

# Re-export commonly used types for convenience
from .core import ir
from .core.errors import BackendError, DazzleError, LinkError, ParseError, ValidationError


def _get_version() -> str:
    """Get version from pyproject.toml (editable) or importlib.metadata (installed)."""
    # In editable mode, read directly from pyproject.toml for live updates
    pyproject = _Path(__file__).parent.parent.parent / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        if match := re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE):
            return match.group(1)

    # Fall back to installed metadata
    try:
        return _metadata_version("dazzle")
    except Exception:
        return "0.0.0"


__version__ = _get_version()

__all__ = [
    "__version__",
    "ir",
    "DazzleError",
    "ParseError",
    "LinkError",
    "ValidationError",
    "BackendError",
]
