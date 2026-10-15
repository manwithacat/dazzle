"""#1626 R4 — capture HTMX settle must not drop stills on Playwright timeout.

Playwright's TimeoutError is not a subclass of builtin TimeoutError. The
settle wait is intentionally soft (continue to screenshot); mis-catching it
as a hard failure was the pay_desk / my_invoices / active_alerts hole.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.qa.capture import CaptureTarget, _capture_one

pytestmark = pytest.mark.gate


def _playwright_timeout() -> type[BaseException]:
    playwright = pytest.importorskip("playwright.async_api")
    assert not issubclass(playwright.TimeoutError, TimeoutError)
    return playwright.TimeoutError


class _Page:
    """A browser page whose load and HTMX-settle waits both time out."""

    def __init__(self, timeout_error: type[BaseException]) -> None:
        self.timeout_error = timeout_error
        self.screenshots: list[str] = []

    async def goto(self, url: str, **_kw: Any) -> None:
        return None

    async def wait_for_load_state(self, *_a: Any, **_kw: Any) -> None:
        raise self.timeout_error("networkidle")

    async def wait_for_function(self, *_a: Any, **_kw: Any) -> None:
        raise self.timeout_error("htmx settle")

    async def wait_for_timeout(self, _ms: int) -> None:
        return None

    async def screenshot(self, *, path: str, **_kw: Any) -> None:
        self.screenshots.append(path)

    async def close(self) -> None:
        return None


class _Context:
    def __init__(self, page: _Page) -> None:
        self.page = page

    async def add_cookies(self, _cookies: list[dict[str, str]]) -> None:
        return None

    async def new_page(self) -> _Page:
        return self.page

    async def close(self) -> None:
        return None


class _Browser:
    def __init__(self, page: _Page) -> None:
        self.page = page

    async def new_context(self, **_kw: Any) -> _Context:
        return _Context(self.page)


class _Sessions:
    async def create_session(self, _persona: str) -> SimpleNamespace:
        return SimpleNamespace(session_token="tok")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "timeout_error",
    [
        pytest.param(lambda: TimeoutError, id="builtin-timeout"),
        pytest.param(_playwright_timeout, id="playwright-timeout"),
    ],
)
async def test_capture_one_screenshots_through_a_settle_timeout(
    tmp_path: Path, timeout_error: Any
) -> None:
    page = _Page(timeout_error())
    target = CaptureTarget(persona="finance", workspace="pay_desk", url="/workspaces/pay_desk")

    result = await _capture_one(
        target, _Browser(page), "http://127.0.0.1:18102", _Sessions(), tmp_path
    )

    assert result is not None
    assert (result.persona, result.workspace, result.url) == (
        "finance",
        "pay_desk",
        "http://127.0.0.1:18102/workspaces/pay_desk",
    )
    assert page.screenshots == [str(result.screenshot)]
