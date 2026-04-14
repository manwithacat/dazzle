"""Tests for PlaywrightExecutor cycle-197 enrichment.

Covers:
- Console listener buffer accumulates errors during executor lifetime
- State capture before/after each action populates from_url/to_url/state_changed
- Per-action-type population (scroll optimistic True, assert optimistic False, tool None)
- Error path preserves new fields
"""

from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.agent.executor import PlaywrightExecutor
from dazzle.agent.models import ActionType, AgentAction


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


def _dom_hash_of(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]


def _make_clicking_page(
    before_url: str, after_url: str, before_html: str, after_html: str
) -> MagicMock:
    """Page whose url and content() change after the click fires."""
    page = _make_mock_page(url=before_url, content=before_html)
    calls = {"n": 0}

    async def _content_after() -> str:
        calls["n"] += 1
        return after_html if calls["n"] > 1 else before_html

    page.content = AsyncMock(side_effect=_content_after)
    locator = MagicMock()
    locator.click = AsyncMock(side_effect=lambda **kw: setattr(page, "url", after_url))
    page.locator = MagicMock(return_value=locator)
    return page


@pytest.mark.asyncio
class TestStateCapture:
    async def test_click_navigates_populates_from_and_to_url(self) -> None:
        page = _make_clicking_page(
            before_url="http://localhost/app",
            after_url="http://localhost/app/contacts/1",
            before_html="<html>before</html>",
            after_html="<html>after</html>",
        )
        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.CLICK, target="button.x")
        result = await executor.execute(action)

        assert result.error is None
        assert result.from_url == "http://localhost/app"
        assert result.to_url == "http://localhost/app/contacts/1"
        assert result.state_changed is True

    async def test_click_no_op_detected(self) -> None:
        """Click fires but URL and DOM hash are unchanged → state_changed False."""
        page = _make_mock_page(url="http://localhost/app", content="<html>same</html>")
        locator = MagicMock()
        locator.click = AsyncMock()  # Does NOT change page.url
        page.locator = MagicMock(return_value=locator)

        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.CLICK, target="a.broken")
        result = await executor.execute(action)

        assert result.from_url == "http://localhost/app"
        assert result.to_url == "http://localhost/app"
        assert result.state_changed is False

    async def test_scroll_is_optimistic_state_changed_true(self) -> None:
        page = _make_mock_page()
        page.evaluate = AsyncMock()  # scroll uses evaluate()
        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.SCROLL)
        result = await executor.execute(action)
        assert result.state_changed is True  # optimistic

    async def test_assert_is_optimistic_state_changed_false(self) -> None:
        page = _make_mock_page()
        locator = MagicMock()
        locator.wait_for = AsyncMock()
        page.locator = MagicMock(return_value=locator)
        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.ASSERT, target="some condition")
        result = await executor.execute(action)
        assert result.state_changed is False  # optimistic

    async def test_tool_action_has_none_state_fields(self) -> None:
        page = _make_mock_page()
        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.TOOL, target="propose_component")
        result = await executor.execute(action)
        assert result.from_url is None
        assert result.to_url is None
        assert result.state_changed is None

    async def test_done_action_has_none_state_fields(self) -> None:
        page = _make_mock_page()
        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.DONE, success=True)
        result = await executor.execute(action)
        assert result.state_changed is None

    async def test_exception_path_preserves_error_and_leaves_state_fields_safe(self) -> None:
        page = _make_mock_page()
        locator = MagicMock()
        locator.click = AsyncMock(side_effect=RuntimeError("selector not found"))
        page.locator = MagicMock(return_value=locator)
        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.CLICK, target="button.missing")
        result = await executor.execute(action)
        assert result.error == "selector not found"
        assert result.state_changed is None  # undefined on error path

    async def test_console_errors_during_click_captured(self) -> None:
        """Errors emitted between the before-snapshot and after-snapshot are captured."""
        page = _make_mock_page()
        locator = MagicMock()

        async def _click(**kw) -> None:
            # Simulate a console error firing during the click
            handler = page._listeners["console"][0]
            handler(MagicMock(type="error", text="TypeError in handler"))

        locator.click = AsyncMock(side_effect=_click)
        page.locator = MagicMock(return_value=locator)
        executor = PlaywrightExecutor(page=page)

        # Add a pre-existing error that should NOT appear in the action's window
        preexisting_handler = page._listeners["console"][0]
        preexisting_handler(MagicMock(type="error", text="old error from page load"))

        action = AgentAction(type=ActionType.CLICK, target="button.x")
        result = await executor.execute(action)
        assert result.console_errors_during_action == ["TypeError in handler"]
