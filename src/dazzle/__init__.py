"""
DAZZLE - Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps.

A DSL-first toolkit for designing and generating applications from
high-level specifications.
"""

from __future__ import annotations

from ._version import get_version as _get_version

# Re-export commonly used types for convenience
from .core import ir
from .core.errors import BackendError, DazzleError, LinkError, ParseError, ValidationError

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
