"""
DAZZLE - Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps.

A DSL-first toolkit for designing and generating applications from
high-level specifications.
"""

from pathlib import Path as _Path


def _get_version() -> str:
    """Get version from pyproject.toml (editable) or importlib.metadata (installed)."""
    # In editable mode, read directly from pyproject.toml for live updates
    pyproject = _Path(__file__).parent.parent.parent / "pyproject.toml"
    if pyproject.exists():
        import re

        content = pyproject.read_text()
        if match := re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE):
            return match.group(1)

    # Fall back to installed metadata
    try:
        from importlib.metadata import version

        return version("dazzle")
    except Exception:
        return "0.0.0"


__version__ = _get_version()

# Re-export commonly used types for convenience
from .core import ir
from .core.errors import BackendError, DazzleError, LinkError, ParseError, ValidationError

__all__ = [
    "__version__",
    "ir",
    "DazzleError",
    "ParseError",
    "LinkError",
    "ValidationError",
    "BackendError",
]
