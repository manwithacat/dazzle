"""Tests for Playwright interaction runner (unit-level, no browser)."""

import pytest

from dazzle.testing.ux.inventory import Interaction, InteractionClass
from dazzle.testing.ux.runner import (
    InteractionRunner,
    _build_page_url,
)


class TestBuildPageUrl:
    def test_list_surface_url(self) -> None:
        url = _build_page_url("task_list", "Task", "list", "http://localhost:3000")
        assert url == "http://localhost:3000/app/task"

    def test_workspace_url(self) -> None:
        url = _build_page_url(
            "", "", "workspace", "http://localhost:3000", workspace="teacher_dashboard"
        )
        assert url == "http://localhost:3000/app/workspaces/teacher_dashboard"


class TestRunnerConfig:
    def test_runner_init(self) -> None:
        runner = InteractionRunner(
            site_url="http://localhost:3000",
            api_url="http://localhost:8000",
        )
        assert runner.site_url == "http://localhost:3000"
        assert runner.api_url == "http://localhost:8000"


# ---------------------------------------------------------------------------
# Console-error gate (complements issue #795)
#
# These tests use a fake Playwright Page to exercise _run_page_load and
# assert that JS console errors fail the interaction.
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status


class _FakeConsoleMessage:
    def __init__(self, text: str, msg_type: str = "error") -> None:
        self.text = text
        self.type = msg_type


class _FakePage:
    """Minimal page stub that drives _run_page_load without a real browser.

    Emits a configurable sequence of console messages between ``goto``
    and the post-navigation check, mimicking errors that fire during
    page load. Registers listeners in the same shape as Playwright's
    real page.on("console", ...).
    """

    def __init__(
        self,
        *,
        response_status: int = 200,
        content: str = (
            "<html><body>" + ("enough content to pass the length check " * 10) + "</body></html>"
        ),
        console_messages: list[_FakeConsoleMessage] | None = None,
    ) -> None:
        self._response_status = response_status
        self._content = content
        self._pending_console = console_messages or []
        self._listeners: dict[str, list] = {}

    def on(self, event: str, listener) -> None:
        self._listeners.setdefault(event, []).append(listener)

    async def goto(self, url: str, wait_until: str = "load") -> _FakeResponse:
        # Emit any pre-queued console messages during navigation.
        for msg in self._pending_console:
            for listener in self._listeners.get("console", []):
                listener(msg)
        return _FakeResponse(status=self._response_status)

    async def content(self) -> str:
        return self._content

    # _capture_screenshot calls page.screenshot — stub it.
    async def screenshot(self, **kwargs) -> bytes:
        return b""


@pytest.mark.asyncio
async def test_page_load_passes_when_no_console_errors() -> None:
    runner = InteractionRunner(
        site_url="http://localhost:3000",
        api_url="http://localhost:8000",
    )
    interaction = Interaction(
        cls=InteractionClass.PAGE_LOAD,
        surface="task_list",
        entity="Task",
        persona="admin",
    )
    page = _FakePage(console_messages=[])
    result = await runner._run_page_load(page, interaction)
    assert result.status == "passed"


@pytest.mark.asyncio
async def test_page_load_fails_on_console_error() -> None:
    runner = InteractionRunner(
        site_url="http://localhost:3000",
        api_url="http://localhost:8000",
    )
    interaction = Interaction(
        cls=InteractionClass.PAGE_LOAD,
        surface="task_list",
        entity="Task",
        persona="admin",
    )
    page = _FakePage(
        console_messages=[
            _FakeConsoleMessage("ReferenceError: Can't find variable: onResizeMove", "error")
        ]
    )
    result = await runner._run_page_load(page, interaction)
    assert result.status == "failed"
    assert result.error is not None
    assert "JS console errors" in result.error
    assert "onResizeMove" in result.error


@pytest.mark.asyncio
async def test_page_load_ignores_console_warning_and_info() -> None:
    runner = InteractionRunner(
        site_url="http://localhost:3000",
        api_url="http://localhost:8000",
    )
    interaction = Interaction(
        cls=InteractionClass.PAGE_LOAD,
        surface="task_list",
        entity="Task",
        persona="admin",
    )
    page = _FakePage(
        console_messages=[
            _FakeConsoleMessage("cookie will expire", "warning"),
            _FakeConsoleMessage("loaded bundle", "info"),
        ]
    )
    result = await runner._run_page_load(page, interaction)
    # Only `error`-level messages fail the gate.
    assert result.status == "passed", result.error
