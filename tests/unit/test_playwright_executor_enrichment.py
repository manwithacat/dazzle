"""Tests for PlaywrightExecutor cycle-197 enrichment.

Covers:
- Console listener buffer accumulates errors during executor lifetime
- State capture before/after each action populates from_url/to_url/state_changed
- Per-action-type population (scroll optimistic True, assert optimistic False, tool None)
- Error path preserves new fields
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from dazzle.agent.executor import PlaywrightExecutor


def _make_mock_page(url: str = "http://localhost/", content: str = "<html></html>") -> MagicMock:
    """Build a MagicMock that looks like a Playwright Page."""
    page = MagicMock()
    page.url = url
    # Console listener machinery
    page._listeners: dict[str, list[Any]] = {}  # type: ignore[misc]

    def _on(event: str, handler: Any) -> None:
        page._listeners.setdefault(event, []).append(handler)

    page.on = MagicMock(side_effect=_on)
    # content() is async
    page.content = AsyncMock(return_value=content)
    # wait_for_load_state is async
    page.wait_for_load_state = AsyncMock()
    return page


class TestConsoleListener:
    def test_init_attaches_console_listener(self) -> None:
        page = _make_mock_page()
        executor = PlaywrightExecutor(page=page)
        # Listener should be registered
        page.on.assert_called_once()
        assert page.on.call_args.args[0] == "console"
        # Buffer attribute created at construction time
        assert executor._console_errors_buffer == []

    def test_console_error_messages_accumulate_in_buffer(self) -> None:
        page = _make_mock_page()
        executor = PlaywrightExecutor(page=page)
        # Simulate the listener firing
        error_handler = page._listeners["console"][0]
        msg_error = MagicMock(type="error", text="TypeError: x is undefined")
        msg_log = MagicMock(type="log", text="plain log")
        error_handler(msg_error)
        error_handler(msg_log)
        error_handler(msg_error)
        # Only 'error' level is buffered
        assert executor._console_errors_buffer == [
            "TypeError: x is undefined",
            "TypeError: x is undefined",
        ]
