"""Default logging configuration for Dazzle entry points (#1122).

Background: when an app is booted via bare ``uvicorn app:app`` or any
ASGI server that doesn't call ``logging.basicConfig`` itself, the
framework's INFO-level diagnostic tags (e.g.
``onboarding.inject:<reason>`` from #1118, ``onboarding.startup:
repo-wired``, the agent-actionable error messages from #1117) emit
into a void — there's no handler attached to the ``dazzle.*`` logger
chain or the root logger, so the records silently drop.

This was load-bearing for CyFuture's #1118 root-cause investigation —
they had to add ``logging.basicConfig(level='INFO')`` to their app
factory before any of the new tags reached Heroku logs. Without that,
the production-debug story doesn't work and the framework's
observability features are inert in deployment.

The fix is small and conservative: at entry-point boot, check whether
ANY handler is configured (root or ``dazzle.*``) and attach a single
StreamHandler to ``logging.getLogger('dazzle')`` if not. Projects that
DO configure logging keep their config untouched — the check is
conservative and only attaches the default when nothing else is in
place.

Designed to be safe to call multiple times (idempotent — the
handlers-present check short-circuits the second call).
"""

from __future__ import annotations

import logging
import os

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def ensure_dazzle_logging_configured(level: str | int | None = None) -> bool:
    """Attach a default StreamHandler to ``dazzle.*`` loggers if none exists.

    Call this once at framework entry-point boot — before any framework
    code path logs. Common entry points:

    - ``dazzle.back.runtime.app_factory.create_app`` (FastAPI runtime)
    - ``dazzle.cli`` command handlers (one-shot CLI runs)
    - ``dazzle.mcp.server`` (MCP server boot)
    - ``dazzle.lsp.server`` (LSP server boot)
    - ``dazzle.back.alembic.env`` (migration env)

    Args:
        level: Log level to set on the ``dazzle`` logger. If ``None``,
            reads ``DAZZLE_LOG_LEVEL`` env var, falling back to ``INFO``.
            Accepts the standard logging level names (``"DEBUG"``,
            ``"INFO"``, ``"WARNING"``, ``"ERROR"``) or integer levels.

    Returns:
        ``True`` if a handler was attached, ``False`` if logging was
        already configured (handler exists on root or ``dazzle``
        logger) and no change was made.

    The check is conservative: any handler on the root logger or on
    the ``dazzle`` logger itself counts as "already configured" — we
    don't touch the project's logging in that case.
    """
    root = logging.getLogger()
    dazzle_log = logging.getLogger("dazzle")
    if root.handlers or dazzle_log.handlers:
        return False

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    dazzle_log.addHandler(handler)

    # Resolve the level: explicit arg → env var → INFO default.
    resolved_level: str | int
    if level is None:
        resolved_level = os.environ.get("DAZZLE_LOG_LEVEL", "INFO").upper()
    else:
        resolved_level = level
    # logging.getLogger().setLevel accepts both names and ints.
    try:
        dazzle_log.setLevel(resolved_level)
    except (ValueError, TypeError):
        dazzle_log.setLevel(logging.INFO)

    # Don't propagate to the root logger — we'd just double-emit if the
    # project later adds a root handler. The dazzle logger has its own
    # handler; that's enough.
    dazzle_log.propagate = False

    return True


__all__ = ["ensure_dazzle_logging_configured"]
