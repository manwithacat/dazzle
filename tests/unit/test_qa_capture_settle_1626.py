"""#1626 R4 — capture HTMX settle must not drop stills on Playwright timeout.

Playwright's TimeoutError is not a subclass of builtin TimeoutError. The
settle wait is intentionally soft (continue to screenshot); mis-catching it
as a hard failure was the pay_desk / my_invoices / active_alerts hole.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.qa.capture import _SETTLE_TIMEOUT_TYPES, CaptureTarget, _capture_one

pytestmark = pytest.mark.gate


class _PlaywrightTimeoutError(Exception):
    """Mimics playwright.async_api.TimeoutError hierarchy (not builtin TimeoutError)."""


@pytest.mark.asyncio
async def test_capture_one_swallows_playwright_htmx_settle_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dazzle.qa.capture as cap

    prev = cap._SETTLE_TIMEOUT_TYPES
    cap._SETTLE_TIMEOUT_TYPES = (
        _PlaywrightTimeoutError,
        TimeoutError,
        OSError,
        RuntimeError,
    )
    try:
        session = SimpleNamespace(session_token="tok")
        session_manager = MagicMock()
        session_manager.create_session = AsyncMock(return_value=session)

        page = MagicMock()
        page.goto = AsyncMock()
        page.wait_for_load_state = AsyncMock(side_effect=_PlaywrightTimeoutError("networkidle"))
        page.wait_for_function = AsyncMock(side_effect=_PlaywrightTimeoutError("htmx settle"))
        page.wait_for_timeout = AsyncMock()
        page.screenshot = AsyncMock()
        page.close = AsyncMock()

        context = MagicMock()
        context.add_cookies = AsyncMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()

        browser = MagicMock()
        browser.new_context = AsyncMock(return_value=context)

        target = CaptureTarget(
            persona="finance",
            workspace="pay_desk",
            url="/workspaces/pay_desk",
        )
        result = await _capture_one(
            target,
            browser,
            "http://127.0.0.1:18102",
            session_manager,
            tmp_path,
        )
        assert result is not None
        assert result.workspace == "pay_desk"
        assert result.persona == "finance"
        page.screenshot.assert_awaited()
    finally:
        cap._SETTLE_TIMEOUT_TYPES = prev


def test_settle_timeout_types_include_playwright_when_available() -> None:
    """When playwright is installed, settle tuple must catch its TimeoutError."""
    assert TimeoutError in _SETTLE_TIMEOUT_TYPES
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    except ImportError:
        pytest.skip("playwright not installed")
    assert PlaywrightTimeoutError in _SETTLE_TIMEOUT_TYPES
    assert not issubclass(PlaywrightTimeoutError, TimeoutError)
