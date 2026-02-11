"""Tests for dazzle.testing.browser_gate — bounded Playwright browser factory."""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.testing.browser_gate import BrowserGate, configure_browser_gate, get_browser_gate

# ── Helpers ──────────────────────────────────────────────────────────


def _make_mock_sync_playwright():
    """Build a mock sync_playwright context manager."""
    browser = MagicMock()
    browser.close = MagicMock()

    chromium = MagicMock()
    chromium.launch = MagicMock(return_value=browser)

    pw = MagicMock()
    pw.chromium = chromium
    pw.__enter__ = MagicMock(return_value=pw)
    pw.__exit__ = MagicMock(return_value=False)

    factory = MagicMock(return_value=pw)
    return factory, browser


def _make_mock_async_playwright():
    """Build a mock async_playwright context manager."""
    browser = AsyncMock()
    browser.close = AsyncMock()

    chromium = AsyncMock()
    chromium.launch = AsyncMock(return_value=browser)

    pw = AsyncMock()
    pw.chromium = chromium
    pw.__aenter__ = AsyncMock(return_value=pw)
    pw.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=pw)
    return factory, browser


# ── Construction / Configuration ─────────────────────────────────────


class TestBrowserGateConfig:
    def test_defaults(self):
        gate = BrowserGate()
        assert gate.max_concurrent == 2
        assert gate.headless is True
        assert gate.active_count == 0

    def test_explicit_max(self):
        gate = BrowserGate(max_concurrent=5)
        assert gate.max_concurrent == 5

    def test_explicit_headless_false(self):
        gate = BrowserGate(headless=False)
        assert gate.headless is False

    def test_min_clamp(self):
        gate = BrowserGate(max_concurrent=0)
        assert gate.max_concurrent == 1

    def test_env_var_max_browsers(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DAZZLE_MAX_BROWSERS", "4")
        gate = BrowserGate()
        assert gate.max_concurrent == 4

    def test_env_var_headless_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DAZZLE_BROWSER_HEADLESS", "0")
        gate = BrowserGate()
        assert gate.headless is False

    def test_env_var_headless_false_word(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DAZZLE_BROWSER_HEADLESS", "false")
        gate = BrowserGate()
        assert gate.headless is False

    def test_explicit_overrides_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DAZZLE_MAX_BROWSERS", "8")
        gate = BrowserGate(max_concurrent=3)
        assert gate.max_concurrent == 3


# ── Singleton ────────────────────────────────────────────────────────


class TestSingleton:
    def setup_method(self):
        # Reset global singleton between tests
        import dazzle.testing.browser_gate as mod

        mod._gate = None

    def test_get_returns_same_instance(self):
        a = get_browser_gate()
        b = get_browser_gate()
        assert a is b

    def test_configure_replaces_instance(self):
        a = get_browser_gate()
        b = configure_browser_gate(max_concurrent=7)
        assert b is not a
        assert b.max_concurrent == 7
        assert get_browser_gate() is b

    def teardown_method(self):
        import dazzle.testing.browser_gate as mod

        mod._gate = None


# ── Sync Context Manager ────────────────────────────────────────────


class TestSyncBrowser:
    @patch("dazzle.testing.browser_gate.sync_playwright", create=True)
    def test_yields_browser_and_closes(self, _mock_sp):
        factory, mock_browser = _make_mock_sync_playwright()

        gate = BrowserGate(max_concurrent=2)

        with patch(
            "dazzle.testing.browser_gate.sync_playwright",
            factory,
            create=True,
        ):
            # Patch at the point of import inside the method
            # We need to mock the lazy import inside sync_browser
            with patch.dict(
                "sys.modules",
                {"playwright": MagicMock(), "playwright.sync_api": MagicMock()},
            ):
                pw_mod = MagicMock()
                pw_mod.sync_playwright = factory
                with patch.dict("sys.modules", {"playwright.sync_api": pw_mod}):
                    with gate.sync_browser() as browser:
                        assert browser is mock_browser
                        assert gate.active_count == 1

        assert gate.active_count == 0
        mock_browser.close.assert_called_once()

    def test_cleanup_on_exception(self):
        factory, mock_browser = _make_mock_sync_playwright()

        gate = BrowserGate(max_concurrent=2)

        pw_mod = MagicMock()
        pw_mod.sync_playwright = factory

        with patch.dict(
            "sys.modules",
            {
                "playwright": MagicMock(),
                "playwright.sync_api": pw_mod,
            },
        ):
            with pytest.raises(RuntimeError, match="boom"):
                with gate.sync_browser() as _browser:
                    assert gate.active_count == 1
                    raise RuntimeError("boom")

        assert gate.active_count == 0
        mock_browser.close.assert_called_once()


# ── Async Context Manager ───────────────────────────────────────────


class TestAsyncBrowser:
    @pytest.mark.asyncio
    async def test_yields_browser_and_closes(self):
        factory, mock_browser = _make_mock_async_playwright()

        gate = BrowserGate(max_concurrent=2)

        pw_mod = MagicMock()
        pw_mod.async_playwright = factory

        with patch.dict(
            "sys.modules",
            {
                "playwright": MagicMock(),
                "playwright.async_api": pw_mod,
            },
        ):
            async with gate.async_browser() as browser:
                assert browser is mock_browser
                assert gate.active_count == 1

        assert gate.active_count == 0
        mock_browser.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_on_exception(self):
        factory, mock_browser = _make_mock_async_playwright()

        gate = BrowserGate(max_concurrent=2)

        pw_mod = MagicMock()
        pw_mod.async_playwright = factory

        with patch.dict(
            "sys.modules",
            {
                "playwright": MagicMock(),
                "playwright.async_api": pw_mod,
            },
        ):
            with pytest.raises(RuntimeError, match="boom"):
                async with gate.async_browser() as _browser:
                    assert gate.active_count == 1
                    raise RuntimeError("boom")

        assert gate.active_count == 0
        mock_browser.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_headless_kwarg_forwarded(self):
        factory, mock_browser = _make_mock_async_playwright()

        gate = BrowserGate(max_concurrent=2, headless=True)

        pw_mod = MagicMock()
        pw_mod.async_playwright = factory

        with patch.dict(
            "sys.modules",
            {
                "playwright": MagicMock(),
                "playwright.async_api": pw_mod,
            },
        ):
            async with gate.async_browser(headless=False) as _browser:
                pass

        # Verify headless=False was passed through
        pw_instance = factory.return_value
        pw_instance.__aenter__.return_value.chromium.launch.assert_awaited_once()
        call_kwargs = pw_instance.__aenter__.return_value.chromium.launch.call_args
        assert call_kwargs[1].get("headless") is False or call_kwargs[0][0] is False


# ── Concurrency Bound ───────────────────────────────────────────────


class TestConcurrencyBound:
    @pytest.mark.asyncio
    async def test_async_semaphore_limits_concurrency(self):
        """Verify only N browsers run at a time when N+1 tasks are queued."""
        gate = BrowserGate(max_concurrent=2)
        peak_active = 0
        lock = asyncio.Lock()

        factory, mock_browser = _make_mock_async_playwright()

        pw_mod = MagicMock()
        pw_mod.async_playwright = factory

        async def use_browser(delay: float) -> None:
            nonlocal peak_active
            async with gate.async_browser() as _browser:
                async with lock:
                    if gate.active_count > peak_active:
                        peak_active = gate.active_count
                await asyncio.sleep(delay)

        # Patch sys.modules at the outer level so all tasks share
        # the same stable mock — avoids races from per-task patching.
        with patch.dict(
            "sys.modules",
            {
                "playwright": MagicMock(),
                "playwright.async_api": pw_mod,
            },
        ):
            # Launch 3 tasks with max_concurrent=2
            tasks = [
                asyncio.create_task(use_browser(0.1)),
                asyncio.create_task(use_browser(0.1)),
                asyncio.create_task(use_browser(0.1)),
            ]
            await asyncio.gather(*tasks)

        assert peak_active <= 2
        assert gate.active_count == 0

    def test_sync_semaphore_limits_concurrency(self):
        """Verify only N sync browsers run at a time."""
        gate = BrowserGate(max_concurrent=1)
        peak_active = 0
        results: list[float] = []  # timestamps of browser acquisition
        lock = threading.Lock()

        factory, mock_browser = _make_mock_sync_playwright()

        pw_mod = MagicMock()
        pw_mod.sync_playwright = factory

        def use_browser() -> None:
            nonlocal peak_active
            with gate.sync_browser() as _browser:
                with lock:
                    if gate.active_count > peak_active:
                        peak_active = gate.active_count
                    results.append(time.monotonic())
                time.sleep(0.05)

        # Patch sys.modules at the outer level so all threads share
        # the same stable mock — avoids races from per-thread patching.
        with patch.dict(
            "sys.modules",
            {
                "playwright": MagicMock(),
                "playwright.sync_api": pw_mod,
            },
        ):
            threads = [threading.Thread(target=use_browser) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # With max_concurrent=1, peak should never exceed 1
        assert peak_active <= 1
        assert gate.active_count == 0


# ── MCP State Integration ───────────────────────────────────────────


class TestMCPStateIntegration:
    def setup_method(self):
        import dazzle.testing.browser_gate as mod

        mod._gate = None

    def test_init_browser_gate(self):
        from dazzle.mcp.server.state import init_browser_gate

        init_browser_gate(max_concurrent=5)

        gate = get_browser_gate()
        assert gate.max_concurrent == 5

    def teardown_method(self):
        import dazzle.testing.browser_gate as mod

        mod._gate = None
