"""
DAZZLE - Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps.

A DSL-first toolkit for designing and generating applications from
high-level specifications.
"""

__version__ = "0.1.0"

# Re-export commonly used types for convenience
from .core import ir
from .core.errors import DazzleError, ParseError, LinkError, ValidationError, BackendError

__all__ = [
    "__version__",
    "ir",
    "DazzleError",
    "ParseError",
    "LinkError",
    "ValidationError",
    "BackendError",
]
