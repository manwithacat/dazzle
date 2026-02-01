"""Single source of truth for the DAZZLE version."""

import re
from importlib.metadata import version as _metadata_version
from pathlib import Path


def get_version() -> str:
    """Get version from pyproject.toml (editable) or importlib.metadata (installed)."""
    pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        if match := re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE):
            return match.group(1)
    try:
        return _metadata_version("dazzle")
    except Exception:
        return "0.0.0"
