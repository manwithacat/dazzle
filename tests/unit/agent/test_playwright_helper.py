"""Tests for the cycle 198 Playwright helper (src/dazzle/agent/playwright_helper.py).

These tests exercise the argparse surface, the action-dispatch logic, and
the state-directory file semantics with mocked Playwright. They do NOT
launch a real browser — that's what the walk-the-playbook acceptance test
does against contact_manager.

Action coverage:
  - _build_parser emits the expected subcommands
  - _paths builds consistent state/base_url/last_url paths from one dir
  - action_login writes state.json + base_url.txt + last_url.txt on success
  - action_observe returns structured page state from mocked page
  - action_click reports state_changed based on before/after URL diff
  - action_type and action_wait dispatch to the right locator methods
  - action_navigate combines base_url with relative paths correctly
  - Error paths return {"error", "error_type"} dicts without raising
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Playwright is an optional runtime dependency; these tests patch
# ``playwright.async_api.async_playwright`` which requires the import to
# resolve, so skip the whole module when playwright isn't installed
# (e.g. the CI "Python Tests" job that doesn't install the extra).
pytest.importorskip("playwright")

from dazzle.agent import playwright_helper as helper  # noqa: E402


def _mk_page(
    url: str = "http://localhost/", title: str = "test", content: str = "<html></html>"
) -> MagicMock:
    page = MagicMock()
    page.url = url
    page.title = AsyncMock(return_value=title)
    page.content = AsyncMock(return_value=content)
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.evaluate = AsyncMock()
    return page


class _FakePlaywrightBundle:
    """Collect the usual Playwright async_playwright().start() hierarchy as mocks."""

    def __init__(self, page: MagicMock):
        self.page = page
        self.ctx = MagicMock()
        self.ctx.new_page = AsyncMock(return_value=page)
        self.ctx.storage_state = AsyncMock()
        self.ctx.close = AsyncMock()
        self.browser = MagicMock()
        self.browser.new_context = AsyncMock(return_value=self.ctx)
        self.browser.close = AsyncMock()
        self.pw = MagicMock()
        self.pw.chromium = MagicMock()
        self.pw.chromium.launch = AsyncMock(return_value=self.browser)
        self.pw.stop = AsyncMock()

    def patch_async_playwright(self):
        """Return a patcher that yields this bundle's pw object when async_playwright().start() is called."""
        starter = MagicMock()
        starter.start = AsyncMock(return_value=self.pw)

        def _factory():
            return starter

        return patch("playwright.async_api.async_playwright", new=_factory)


class TestParser:
    def test_parser_has_all_actions(self) -> None:
        parser = helper._build_parser()
        # Parse a minimal valid command for each action
        parsed = parser.parse_args(["--state-dir", "/tmp/x", "login", "http://localhost", "user"])
        assert parsed.action == "login"
        assert parsed.api_url == "http://localhost"
        assert parsed.persona_id == "user"

        parsed = parser.parse_args(["--state-dir", "/tmp/x", "observe"])
        assert parsed.action == "observe"

        parsed = parser.parse_args(["--state-dir", "/tmp/x", "navigate", "/path"])
        assert parsed.action == "navigate"
        assert parsed.target == "/path"

        parsed = parser.parse_args(["--state-dir", "/tmp/x", "click", "button.create"])
        assert parsed.action == "click"
        assert parsed.selector == "button.create"

        parsed = parser.parse_args(["--state-dir", "/tmp/x", "type", "#field", "hello"])
        assert parsed.action == "type"
        assert parsed.selector == "#field"
        assert parsed.text == "hello"

        parsed = parser.parse_args(["--state-dir", "/tmp/x", "select", "#priority", "high"])
        assert parsed.action == "select"
        assert parsed.selector == "#priority"
        assert parsed.value == "high"

        parsed = parser.parse_args(["--state-dir", "/tmp/x", "wait", ".loaded"])
        assert parsed.action == "wait"

    def test_timeout_default_and_override(self) -> None:
        parser = helper._build_parser()
        default = parser.parse_args(["--state-dir", "/tmp/x", "observe"])
        assert default.timeout == helper.DEFAULT_TIMEOUT_MS
        custom = parser.parse_args(["--state-dir", "/tmp/x", "--timeout", "12000", "observe"])
        assert custom.timeout == 12000


class TestPaths:
    def test_paths_are_derived_from_state_dir(self, tmp_path: Path) -> None:
        state, base_url, last_url = helper._paths(tmp_path)
        assert state == tmp_path / "state.json"
        assert base_url == tmp_path / "base_url.txt"
        assert last_url == tmp_path / "last_url.txt"


@pytest.mark.asyncio
class TestActionLogin:
    async def test_successful_login_writes_state_files(self, tmp_path: Path) -> None:
        page = _mk_page(url="http://localhost:3000/")
        page.request = MagicMock()
        # Magic-link POST → 200 with `url` field
        post_resp = MagicMock()
        post_resp.ok = True
        post_resp.status = 200
        post_resp.json = AsyncMock(return_value={"url": "/auth/magic/abc123"})
        page.request.post = AsyncMock(return_value=post_resp)

        bundle = _FakePlaywrightBundle(page)

        with bundle.patch_async_playwright():
            result = await helper.action_login("http://localhost:3000", "user", tmp_path, 5000)

        assert result["status"] == "logged_in"
        assert result["persona"] == "user"
        assert (tmp_path / "base_url.txt").read_text() == "http://localhost:3000"
        assert (tmp_path / "last_url.txt").read_text() == "http://localhost:3000/"
        bundle.ctx.storage_state.assert_awaited_once()

    async def test_magic_link_post_failure_returns_error(self, tmp_path: Path) -> None:
        page = _mk_page()
        page.request = MagicMock()
        post_resp = MagicMock()
        post_resp.ok = False
        post_resp.status = 404
        page.request.post = AsyncMock(return_value=post_resp)

        bundle = _FakePlaywrightBundle(page)
        with bundle.patch_async_playwright():
            result = await helper.action_login("http://localhost:3000", "user", tmp_path, 5000)

        assert "error" in result
        assert "404" in result["error"]

    async def test_login_bounce_to_auth_login_flagged_as_rejection(self, tmp_path: Path) -> None:
        page = _mk_page(url="http://localhost:3000/auth/login")
        page.request = MagicMock()
        post_resp = MagicMock()
        post_resp.ok = True
        post_resp.status = 200
        post_resp.json = AsyncMock(return_value={"url": "/auth/magic/abc"})
        page.request.post = AsyncMock(return_value=post_resp)

        bundle = _FakePlaywrightBundle(page)
        with bundle.patch_async_playwright():
            result = await helper.action_login("http://localhost:3000", "user", tmp_path, 5000)

        assert "error" in result
        assert "login rejected" in result["error"]


@pytest.mark.asyncio
class TestActionObserve:
    async def test_returns_structured_page_state(self, tmp_path: Path) -> None:
        page = _mk_page(url="http://localhost/app", title="Contacts")
        page.evaluate.side_effect = [
            [
                {
                    "tag": "a",
                    "role": None,
                    "text": "Home",
                    "id": None,
                    "className": "nav",
                    "href": "/",
                    "name": None,
                },
            ],
            "Contact Manager Dashboard",
        ]
        bundle = _FakePlaywrightBundle(page)

        with bundle.patch_async_playwright():
            result = await helper.action_observe(tmp_path, 5000)

        assert result["url"] == "http://localhost/app"
        assert result["title"] == "Contacts"
        assert len(result["interactive_elements"]) == 1
        assert result["interactive_elements"][0]["text"] == "Home"
        assert result["visible_text"] == "Contact Manager Dashboard"


@pytest.mark.asyncio
class TestActionClick:
    async def test_click_state_changed_when_url_differs(self, tmp_path: Path) -> None:
        page = _mk_page(url="http://localhost/app")
        locator = MagicMock()

        async def _click(**kw: object) -> None:
            page.url = "http://localhost/app/contacts/1"

        locator.first = MagicMock()
        locator.first.click = AsyncMock(side_effect=_click)
        page.locator = MagicMock(return_value=locator)

        bundle = _FakePlaywrightBundle(page)
        with bundle.patch_async_playwright():
            result = await helper.action_click("a.view", tmp_path, 5000)

        assert result["status"] == "clicked"
        assert result["state_changed"] is True
        assert result["to"] == "http://localhost/app/contacts/1"

    async def test_click_no_state_change_when_url_unchanged(self, tmp_path: Path) -> None:
        page = _mk_page(url="http://localhost/app")
        locator = MagicMock()
        locator.first = MagicMock()
        locator.first.click = AsyncMock()  # no URL change
        page.locator = MagicMock(return_value=locator)

        bundle = _FakePlaywrightBundle(page)
        with bundle.patch_async_playwright():
            result = await helper.action_click("button.inert", tmp_path, 5000)

        assert result["status"] == "clicked"
        assert result["state_changed"] is False

    async def test_click_exception_returns_error(self, tmp_path: Path) -> None:
        page = _mk_page()
        locator = MagicMock()
        locator.first = MagicMock()
        locator.first.click = AsyncMock(side_effect=Exception("locator not found"))
        page.locator = MagicMock(return_value=locator)

        bundle = _FakePlaywrightBundle(page)
        with bundle.patch_async_playwright():
            result = await helper.action_click("a.missing", tmp_path, 5000)

        assert "error" in result
        assert result["selector"] == "a.missing"
        assert result["error_type"] == "Exception"


@pytest.mark.asyncio
class TestActionType:
    async def test_type_fills_locator(self, tmp_path: Path) -> None:
        page = _mk_page()
        locator = MagicMock()
        locator.first = MagicMock()
        locator.first.fill = AsyncMock()
        page.locator = MagicMock(return_value=locator)

        bundle = _FakePlaywrightBundle(page)
        with bundle.patch_async_playwright():
            result = await helper.action_type("#email", "a@b.c", tmp_path, 5000)

        assert result["status"] == "typed"
        assert result["text_length"] == 5
        locator.first.fill.assert_awaited_once_with("a@b.c", timeout=5000)


@pytest.mark.asyncio
class TestActionWait:
    async def test_wait_finds_selector(self, tmp_path: Path) -> None:
        page = _mk_page()
        locator = MagicMock()
        locator.first = MagicMock()
        locator.first.wait_for = AsyncMock()
        page.locator = MagicMock(return_value=locator)

        bundle = _FakePlaywrightBundle(page)
        with bundle.patch_async_playwright():
            result = await helper.action_wait(".loaded", tmp_path, 5000)

        assert result["status"] == "found"
        assert result["selector"] == ".loaded"


@pytest.mark.asyncio
class TestActionSelect:
    async def test_select_matches_by_value_on_first_try(self, tmp_path: Path) -> None:
        page = _mk_page()
        locator = MagicMock()
        locator.first = MagicMock()
        locator.first.select_option = AsyncMock(return_value=["high"])
        page.locator = MagicMock(return_value=locator)

        bundle = _FakePlaywrightBundle(page)
        with bundle.patch_async_playwright():
            result = await helper.action_select("#priority", "high", tmp_path, 5000)

        assert result["status"] == "selected"
        assert result["matched_by"] == "value"
        assert result["chosen_values"] == ["high"]
        locator.first.select_option.assert_awaited_once_with(value="high", timeout=5000)

    async def test_select_falls_back_to_label(self, tmp_path: Path) -> None:
        page = _mk_page()
        locator = MagicMock()
        locator.first = MagicMock()

        # First call (value=...) raises, second call (label=...) succeeds
        locator.first.select_option = AsyncMock(side_effect=[Exception("no value match"), ["low"]])
        page.locator = MagicMock(return_value=locator)

        bundle = _FakePlaywrightBundle(page)
        with bundle.patch_async_playwright():
            result = await helper.action_select("#priority", "Low Priority", tmp_path, 5000)

        assert result["status"] == "selected"
        assert result["matched_by"] == "label"
        assert result["chosen_values"] == ["low"]
        assert locator.first.select_option.await_count == 2

    async def test_select_returns_error_when_both_attempts_fail(self, tmp_path: Path) -> None:
        page = _mk_page()
        locator = MagicMock()
        locator.first = MagicMock()
        locator.first.select_option = AsyncMock(
            side_effect=[Exception("no value"), Exception("no label either")]
        )
        page.locator = MagicMock(return_value=locator)

        bundle = _FakePlaywrightBundle(page)
        with bundle.patch_async_playwright():
            result = await helper.action_select("#priority", "nonexistent", tmp_path, 5000)

        assert "error" in result
        assert result["selector"] == "#priority"
        assert result["value"] == "nonexistent"
        assert result["error_type"] == "Exception"


@pytest.mark.asyncio
class TestActionNavigate:
    async def test_relative_path_combined_with_base_url(self, tmp_path: Path) -> None:
        (tmp_path / "base_url.txt").write_text("http://localhost:3653")
        page = _mk_page(url="http://localhost:3653/")

        async def _goto(url: str) -> None:
            page.url = url

        page.goto = AsyncMock(side_effect=_goto)

        bundle = _FakePlaywrightBundle(page)
        with bundle.patch_async_playwright():
            result = await helper.action_navigate("/app/contacts", tmp_path, 5000)

        assert result["status"] == "navigated"
        assert result["to"] == "http://localhost:3653/app/contacts"

    async def test_absolute_url_used_directly(self, tmp_path: Path) -> None:
        (tmp_path / "base_url.txt").write_text("http://localhost:3653")
        page = _mk_page(url="http://localhost:3653/")

        async def _goto(url: str) -> None:
            page.url = url

        page.goto = AsyncMock(side_effect=_goto)

        bundle = _FakePlaywrightBundle(page)
        with bundle.patch_async_playwright():
            result = await helper.action_navigate("http://other.com/elsewhere", tmp_path, 5000)

        assert result["to"] == "http://other.com/elsewhere"
