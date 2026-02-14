"""MCP progress notification support.

Provides a lightweight context object that handlers can use to send
progress updates back to the client during long-running operations.

Usage in handlers::

    async def my_handler(project_path, args, *, progress=None):
        if progress:
            await progress.log("Starting phase 1...")
            await progress.advance(1, 5, "Phase 1 complete")

If the handler is synchronous, use the sync wrappers::

    def my_sync_handler(project_path, args, *, progress=None):
        if progress:
            progress.log_sync("Starting phase 1...")
            progress.advance_sync(1, 5, "Phase 1 complete")
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .activity_log import ActivityStore

logger = logging.getLogger("dazzle.mcp.progress")


class ProgressContext:
    """Thin wrapper around an MCP session for sending progress notifications.

    Handles both progress tokens (numeric progress bars) and log messages
    (textual status updates). Falls back gracefully if the session or token
    is unavailable.

    When an :class:`ActivityStore` is attached, every ``log()`` and
    ``advance()`` call also appends a structured event to the SQLite
    activity store — the *reliable* channel that survives even when the
    MCP client drops notifications.
    """

    def __init__(
        self,
        session: Any = None,
        progress_token: str | int | None = None,
        *,
        activity_store: ActivityStore | None = None,
        tool_name: str | None = None,
        operation: str | None = None,
    ) -> None:
        self._session = session
        self._progress_token = progress_token
        self._step = 0
        self._activity_store = activity_store
        self._tool_name = tool_name
        self._operation = operation

    @property
    def available(self) -> bool:
        """True if we have a session to send notifications through."""
        return self._session is not None

    # --------------------------------------------------------------------- #
    # Async API (preferred for async handlers)
    # --------------------------------------------------------------------- #

    async def log(self, message: str, *, level: str = "info") -> None:
        """Send a log message notification to the client."""
        # Activity log write — synchronous, <1ms, always succeeds
        self._write_log_entry(message, level=level)

        if not self._session:
            return
        try:
            await self._session.send_log_message(
                level=level,
                data=message,
                logger="dazzle",
            )
        except Exception:
            logger.debug("Failed to send log message: %s", message, exc_info=True)

    async def advance(
        self,
        current: int | float,
        total: int | float,
        message: str | None = None,
    ) -> None:
        """Send a progress notification with numeric progress, plus a log message.

        Sends both a structured progress notification (if token available)
        and a human-readable log message so the client always gets feedback.
        """
        self._step = int(current)

        # Activity log — structured progress entry (always, even without session)
        self._write_progress_entry(int(current), int(total), message)

        if not self._session:
            return

        # Always send a log message — this is the reliable MCP path
        log_msg = (
            f"[{int(current)}/{int(total)}] {message}"
            if message
            else f"[{int(current)}/{int(total)}]"
        )
        try:
            await self._session.send_log_message(
                level="info",
                data=log_msg,
                logger="dazzle",
            )
        except Exception:
            logger.debug("Failed to send log message: %s", log_msg, exc_info=True)

        # Also send structured progress if we have a token
        if self._progress_token is not None:
            try:
                await self._session.send_progress_notification(
                    progress_token=self._progress_token,
                    progress=float(current),
                    total=float(total),
                    message=message,
                )
            except Exception:
                logger.debug("Failed to send progress notification", exc_info=True)

    # --------------------------------------------------------------------- #
    # Sync API (for synchronous handlers that can't await)
    # --------------------------------------------------------------------- #

    def _fire_and_forget(self, coro: Any) -> None:
        """Schedule a coroutine on the running event loop without awaiting.

        Uses create_task so the notification is sent in the background.
        If no loop is running (e.g. unit tests), silently skips.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            pass  # No running event loop — skip silently

    def log_sync(self, message: str, *, level: str = "info") -> None:
        """Synchronous wrapper for log(). Fires and forgets via event loop."""
        # Activity log write is always synchronous — do it directly
        self._write_log_entry(message, level=level)

        if not self._session:
            return
        self._fire_and_forget(self._send_log_message(message, level=level))

    def advance_sync(
        self,
        current: int | float,
        total: int | float,
        message: str | None = None,
    ) -> None:
        """Synchronous wrapper for advance(). Fires and forgets via event loop."""
        self._step = int(current)
        # Activity log — structured progress (always, even without session)
        self._write_progress_entry(int(current), int(total), message)

        if not self._session:
            return
        self._fire_and_forget(self._send_advance(current, total, message))

    # --------------------------------------------------------------------- #
    # Activity log helpers (synchronous, <1ms)
    # --------------------------------------------------------------------- #

    def _write_log_entry(self, message: str, *, level: str = "info") -> None:
        """Append a log entry to the SQLite activity store if attached."""
        if self._activity_store is not None:
            try:
                self._activity_store.log_event(
                    "log",
                    self._tool_name or "",
                    self._operation,
                    message=message,
                    level=level,
                )
            except Exception:
                pass  # Never fail the handler due to activity logging

    def _write_progress_entry(self, current: int, total: int, message: str | None) -> None:
        """Append a progress entry to the SQLite activity store if attached."""
        if self._activity_store is not None:
            try:
                self._activity_store.log_event(
                    "progress",
                    self._tool_name or "",
                    self._operation,
                    progress_current=current,
                    progress_total=total,
                    message=message or "",
                )
            except Exception:
                pass  # Never fail the handler due to activity logging

    # --------------------------------------------------------------------- #
    # Internal async helpers (for sync wrappers to fire-and-forget)
    # --------------------------------------------------------------------- #

    async def _send_log_message(self, message: str, *, level: str = "info") -> None:
        """Send only the MCP log message (no activity log write)."""
        try:
            await self._session.send_log_message(
                level=level,
                data=message,
                logger="dazzle",
            )
        except Exception:
            logger.debug("Failed to send log message: %s", message, exc_info=True)

    async def _send_advance(
        self, current: int | float, total: int | float, message: str | None
    ) -> None:
        """Send only the MCP progress notifications (no activity log write)."""
        log_msg = (
            f"[{int(current)}/{int(total)}] {message}"
            if message
            else f"[{int(current)}/{int(total)}]"
        )
        try:
            await self._session.send_log_message(
                level="info",
                data=log_msg,
                logger="dazzle",
            )
        except Exception:
            logger.debug("Failed to send log message: %s", log_msg, exc_info=True)

        if self._progress_token is not None:
            try:
                await self._session.send_progress_notification(
                    progress_token=self._progress_token,
                    progress=float(current),
                    total=float(total),
                    message=message,
                )
            except Exception:
                logger.debug("Failed to send progress notification", exc_info=True)


# Singleton for "no progress context" — avoids None checks in handlers
_NOOP = ProgressContext(session=None)


def noop() -> ProgressContext:
    """Return a no-op progress context (safe to call methods on, does nothing)."""
    return _NOOP
