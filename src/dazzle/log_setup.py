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
import re

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

_REDACTED = "***REDACTED***"

# (pattern, replacement) pairs for credential-shaped substrings. Replacements
# keep the non-secret prefix so the log line stays diagnostic.
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # URL credentials — scheme://user:password@host
    (re.compile(r"(://[^\s:/@]+:)[^\s@/]+(@)"), r"\g<1>" + _REDACTED + r"\g<2>"),
    # Authorization bearer tokens
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"), r"\g<1>" + _REDACTED),
    # key=value / key: value for secret-ish keys
    (
        re.compile(
            r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|"
            r"client[_-]?secret|auth[_-]?token|authorization)"
            r"(['\"]?\s*[=:]\s*['\"]?)[^\s'\"&]+"
        ),
        r"\g<1>\g<2>" + _REDACTED,
    ),
]


def redact_secrets(text: str) -> str:
    """Mask credential-shaped substrings — API keys, bearer tokens, URL
    passwords — in ``text``. Framework-level log defence for #1199."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SecretRedactionFilter(logging.Filter):
    """Logging filter that masks credentials in every record it sees.

    Attached to the framework's log handlers so an API key, bearer token or
    DB-URL password that reaches a log message or traceback is masked before
    the record is emitted (#1199).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError, KeyError):
            # Malformed msg %% args — leave the record untouched for the
            # handler/formatter to surface the formatting error itself.
            return True
        redacted = redact_secrets(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            record.exc_text = redact_secrets(record.exc_text)
        return True


def _apply_secret_redaction() -> None:
    """Attach a :class:`SecretRedactionFilter` to each root/``dazzle`` handler
    that does not already have one. Idempotent."""
    seen: set[int] = set()
    for name in ("", "dazzle"):
        for handler in logging.getLogger(name).handlers:
            if id(handler) in seen:
                continue
            seen.add(id(handler))
            if not any(isinstance(f, SecretRedactionFilter) for f in handler.filters):
                handler.addFilter(SecretRedactionFilter())


def ensure_dazzle_logging_configured(level: str | int | None = None) -> bool:
    """Attach a default StreamHandler to ``dazzle.*`` loggers if none exists.

    Call this once at framework entry-point boot — before any framework
    code path logs. Common entry points:

    - ``dazzle.http.runtime.app_factory.create_app`` (FastAPI runtime)
    - ``dazzle.cli`` command handlers (one-shot CLI runs)
    - ``dazzle.mcp.server`` (MCP server boot)
    - ``dazzle.lsp.server`` (LSP server boot)
    - ``dazzle.http.alembic.env`` (migration env)

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
        _apply_secret_redaction()
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

    _apply_secret_redaction()
    return True


__all__ = [
    "SecretRedactionFilter",
    "ensure_dazzle_logging_configured",
    "redact_secrets",
]
