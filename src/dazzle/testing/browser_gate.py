"""Bounded browser factory for Playwright.

Limits concurrent Chromium instances to prevent memory exhaustion
when LLM agents run multiple operations in parallel (discovery runs,
composition capture, viewport tests, agent E2E tests).

Usage::

    from dazzle.testing.browser_gate import get_browser_gate

    # Async consumers
    async with get_browser_gate().async_browser() as browser:
        page = await browser.new_page()
        ...

    # Sync consumers
    with get_browser_gate().sync_browser() as browser:
        page = browser.new_page()
        ...

Configuration via environment variables:

- ``DAZZLE_MAX_BROWSERS`` — max concurrent Chromium instances (default: 2)
- ``DAZZLE_BROWSER_HEADLESS`` — ``1``/``true`` or ``0``/``false`` (default: ``1``)
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

logger = logging.getLogger("dazzle.testing.browser_gate")

DEFAULT_MAX_BROWSERS = 2
DEFAULT_HEADLESS = True


class BrowserGate:
    """Semaphore-gated Playwright browser factory.

    Each call to :meth:`async_browser` or :meth:`sync_browser` acquires a
    slot before launching Chromium and releases it when the context manager
    exits (after closing the browser).  Callers beyond the limit block until
    a slot becomes available.
    """

    def __init__(
        self,
        max_concurrent: int | None = None,
        headless: bool | None = None,
    ) -> None:
        raw = (
            max_concurrent
            if max_concurrent is not None
            else int(os.environ.get("DAZZLE_MAX_BROWSERS", str(DEFAULT_MAX_BROWSERS)))
        )
        self._max: int = max(1, raw)
        self._headless: bool = (
            headless
            if headless is not None
            else os.environ.get("DAZZLE_BROWSER_HEADLESS", "1") not in ("0", "false")
        )
        self._async_semaphore: asyncio.Semaphore | None = None
        self._sync_semaphore = threading.Semaphore(self._max)
        self._active_count: int = 0
        self._lock = threading.Lock()

    @property
    def max_concurrent(self) -> int:
        """Maximum number of concurrent browsers allowed."""
        return self._max

    @property
    def active_count(self) -> int:
        """Number of browsers currently running."""
        return self._active_count

    @property
    def headless(self) -> bool:
        """Default headless mode for launched browsers."""
        return self._headless

    def _get_async_semaphore(self) -> asyncio.Semaphore:
        """Lazily create the async semaphore (must be on an event loop)."""
        if self._async_semaphore is None:
            self._async_semaphore = asyncio.Semaphore(self._max)
        return self._async_semaphore

    def _inc(self) -> None:
        with self._lock:
            self._active_count += 1
        logger.debug("Browser slot acquired (%d/%d active)", self._active_count, self._max)

    def _dec(self) -> None:
        with self._lock:
            self._active_count -= 1
        logger.debug("Browser slot released (%d/%d active)", self._active_count, self._max)

    @asynccontextmanager
    async def async_browser(self, **launch_kwargs: Any) -> AsyncIterator[Any]:
        """Async context manager: acquire slot, launch browser, yield, close, release.

        Keyword arguments are forwarded to ``chromium.launch()``.
        The ``headless`` kwarg defaults to the gate's configured value.
        """
        sem = self._get_async_semaphore()
        await sem.acquire()
        self._inc()
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                headless = launch_kwargs.pop("headless", self._headless)
                browser = await p.chromium.launch(headless=headless, **launch_kwargs)
                try:
                    yield browser
                finally:
                    await browser.close()
        finally:
            self._dec()
            sem.release()

    @contextmanager
    def sync_browser(self, **launch_kwargs: Any) -> Iterator[Any]:
        """Sync context manager: acquire slot, launch browser, yield, close, release.

        Keyword arguments are forwarded to ``chromium.launch()``.
        The ``headless`` kwarg defaults to the gate's configured value.
        """
        self._sync_semaphore.acquire()
        self._inc()
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                headless = launch_kwargs.pop("headless", self._headless)
                browser = p.chromium.launch(headless=headless, **launch_kwargs)
                try:
                    yield browser
                finally:
                    browser.close()
        finally:
            self._dec()
            self._sync_semaphore.release()


# ── Module-level singleton ──────────────────────────────────────────

_gate: BrowserGate | None = None
_gate_lock = threading.Lock()


def get_browser_gate() -> BrowserGate:
    """Get or create the global BrowserGate singleton."""
    global _gate
    if _gate is None:
        with _gate_lock:
            if _gate is None:
                _gate = BrowserGate()
    return _gate


def configure_browser_gate(
    max_concurrent: int | None = None,
    headless: bool | None = None,
) -> BrowserGate:
    """Reconfigure the global gate.  Returns the new instance."""
    global _gate
    with _gate_lock:
        _gate = BrowserGate(max_concurrent=max_concurrent, headless=headless)
    return _gate
