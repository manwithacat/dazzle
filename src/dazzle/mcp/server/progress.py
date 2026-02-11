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
from typing import Any

logger = logging.getLogger("dazzle.mcp.progress")


class ProgressContext:
    """Thin wrapper around an MCP session for sending progress notifications.

    Handles both progress tokens (numeric progress bars) and log messages
    (textual status updates). Falls back gracefully if the session or token
    is unavailable.
    """

    def __init__(
        self,
        session: Any = None,
        progress_token: str | int | None = None,
    ) -> None:
        self._session = session
        self._progress_token = progress_token
        self._step = 0

    @property
    def available(self) -> bool:
        """True if we have a session to send notifications through."""
        return self._session is not None

    # --------------------------------------------------------------------- #
    # Async API (preferred for async handlers)
    # --------------------------------------------------------------------- #

    async def log(self, message: str, *, level: str = "info") -> None:
        """Send a log message notification to the client."""
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
        if not self._session:
            return
        self._step = int(current)

        # Always send a log message — this is the reliable path
        log_msg = (
            f"[{int(current)}/{int(total)}] {message}"
            if message
            else f"[{int(current)}/{int(total)}]"
        )
        await self.log(log_msg)

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
        if not self._session:
            return
        self._fire_and_forget(self.log(message, level=level))

    def advance_sync(
        self,
        current: int | float,
        total: int | float,
        message: str | None = None,
    ) -> None:
        """Synchronous wrapper for advance(). Fires and forgets via event loop."""
        if not self._session:
            return
        self._fire_and_forget(self.advance(current, total, message))


# Singleton for "no progress context" — avoids None checks in handlers
_NOOP = ProgressContext(session=None)


def noop() -> ProgressContext:
    """Return a no-op progress context (safe to call methods on, does nothing)."""
    return _NOOP
