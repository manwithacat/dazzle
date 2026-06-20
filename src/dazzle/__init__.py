"""
DAZZLE - Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps.

A DSL-first toolkit for designing and generating applications from
high-level specifications.
"""

from ._version import get_version as _get_version

# Re-export commonly used types for convenience
from .core import ir
from .core.errors import BackendError, DazzleError, LinkError, ParseError, ValidationError
from .result import Err, Ok, Result, UnwrapError
from .types import NewType

__version__ = _get_version()

__all__ = [
    "__version__",
    "ir",
    "DazzleError",
    "ParseError",
    "LinkError",
    "ValidationError",
    "BackendError",
    "Ok",
    "Err",
    "Result",
    "UnwrapError",
    "NewType",
    "register_lifespan_hook",
]


def __getattr__(name: str) -> object:
    # #1366: the supported host-app startup/shutdown path, surfaced at the top
    # level so downstream code finds it before reaching for the deprecated
    # @app.on_event (which a custom lifespan silently ignores). Lazy because
    # importing back.runtime pulls FastAPI (~350ms) — `import dazzle` and
    # `dazzle --help` must stay light (the v0.80.8 lesson).
    if name == "register_lifespan_hook":
        from .http.runtime.lifespan_hooks import register_lifespan_hook

        return register_lifespan_hook
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
