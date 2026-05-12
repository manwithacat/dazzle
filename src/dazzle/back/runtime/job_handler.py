"""Background-job handler resolution (#953 cycle 3).

Turns a `JobSpec.run` declaration into a callable the worker can
invoke. Two forms are supported in cycle 3:

  * Module path with `:` separator —
    ``app.jobs:render_thumbnail`` resolves to
    ``app.jobs.render_thumbnail``.
  * Module path with `.` separator —
    ``app.jobs.render_thumbnail`` resolves the same way, with the
    rightmost dot being the attribute boundary.

File paths (e.g. ``scripts/render_thumbnail.py``) are intentionally
out of scope for cycle 3 — they need a sandboxed subprocess executor
that handles cwd / env / cleanup, which is its own primitive worth
designing separately. The resolver raises ``JobHandlerNotFound``
with a clear message when given a file path so callers can catch
it and surface a useful error.

Security
--------

`JobSpec.run` is sourced from the DSL at AppSpec build time — never
from request input. The resolver further validates the module path
against ``_VALID_MODULE_PATH_RE`` (lowercase identifier characters
+ dots only) before reaching ``importlib.import_module`` so even a
hypothetical untrusted DSL source can't traverse arbitrary import
graphs.
"""

from __future__ import annotations

import importlib
import logging
import re
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Restrict to lowercase identifier chars + dots — matches the
# Python module naming convention without allowing path traversal,
# leading dots, double dots, or arbitrary symbols.
_VALID_MODULE_PATH_RE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*$")


class JobHandlerNotFound(Exception):
    """Raised when `JobSpec.run` can't be resolved to a callable.

    Cycle-4 worker catches this, marks the JobRun as ``failed``
    with the exception message in `error_message`, and logs.
    """


def resolve_handler(run_path: str) -> Callable[..., Any]:
    """Resolve a `JobSpec.run` value to a callable.

    Args:
        run_path: A dotted module path optionally followed by an
            attribute separator (``module:func`` or
            ``module.func``).

    Returns:
        The resolved callable. Cycle-4 worker invokes it with the
        message payload (``handler(**payload)`` or
        ``handler(payload)`` per the cycle-4-decided convention).

    Raises:
        JobHandlerNotFound: If the path is empty, looks like a file
            path, or the module/attribute can't be imported.
    """
    if not run_path:
        raise JobHandlerNotFound("Job handler path is empty")

    if _looks_like_file_path(run_path):
        raise JobHandlerNotFound(
            f"Job handler {run_path!r} looks like a file path. "
            "Cycle 3 supports only dotted module paths "
            "(e.g. `app.jobs:render_thumbnail`); file-path handlers "
            "need a sandboxed subprocess executor (out of scope "
            "for now)."
        )

    module_name, attr_name = _split_module_attr(run_path)

    # Allow-list validation — only lowercase identifier chars + dots
    # reach the import, even though `module_name` is sourced from the
    # DSL at AppSpec build time (never request input). Defends
    # against a future malformed JobSpec.run reaching the importer.
    if not _VALID_MODULE_PATH_RE.match(module_name):
        raise JobHandlerNotFound(
            f"Job handler module {module_name!r} contains invalid characters; "
            "only lowercase identifiers + dots are allowed."
        )

    try:
        module = importlib.import_module(module_name)  # nosemgrep
    except ImportError as exc:
        raise JobHandlerNotFound(
            f"Cannot import job handler module {module_name!r}: {exc}"
        ) from exc

    try:
        handler = getattr(module, attr_name)
    except AttributeError as exc:
        raise JobHandlerNotFound(f"Module {module_name!r} has no attribute {attr_name!r}") from exc

    if not callable(handler):
        raise JobHandlerNotFound(
            f"Job handler {run_path!r} resolved to a non-callable {type(handler).__name__}"
        )

    resolved: Callable[..., Any] = handler
    return resolved


def _looks_like_file_path(run_path: str) -> bool:
    """True if `run_path` looks like a filesystem path rather than a
    dotted module path."""
    if "/" in run_path or "\\" in run_path:
        return True
    if run_path.endswith((".py", ".sh", ".js")):
        return True
    return False


def _split_module_attr(run_path: str) -> tuple[str, str]:
    """Split a `run_path` into ``(module_name, attr_name)``.

    Accepts both ``module:attr`` and ``module.attr`` forms. The
    colon form is preferred (matches Python entry-point convention)
    because it removes ambiguity on namespaced modules like
    ``app.jobs.render_thumbnail`` — without the colon you can't tell
    whether `render_thumbnail` is a sub-module or the callable.
    """
    if ":" in run_path:
        module_name, _, attr_name = run_path.partition(":")
        if not module_name or not attr_name:
            raise JobHandlerNotFound(
                f"Job handler {run_path!r} has empty module or attr around `:`"
            )
        return module_name, attr_name

    if "." not in run_path:
        raise JobHandlerNotFound(
            f"Job handler {run_path!r} must be a dotted path "
            "(e.g. `app.jobs.render_thumbnail` or "
            "`app.jobs:render_thumbnail`)"
        )

    module_name, _, attr_name = run_path.rpartition(".")
    return module_name, attr_name
