"""Tests for DazzleAgent core — LLM backend selection, MCP sampling,
observer modes, executor selectors, and viewport runner optimization."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.agent.core import DazzleAgent, Mission
from dazzle.agent.executor import PlaywrightExecutor
from dazzle.agent.models import ActionType, AgentAction, ObserverMode, PageState
from dazzle.agent.observer import PlaywrightObserver

# =============================================================================
# Fixtures
# =============================================================================


def _mock_observer() -> MagicMock:
    obs = AsyncMock()
    obs.observe.return_value = PageState(
        url="http://localhost:3000/",
        title="Test Page",
        visible_text="Hello",
    )
    obs.navigate = AsyncMock()
    return obs


def _mock_executor() -> MagicMock:
    return AsyncMock()


def _simple_mission() -> Mission:
    return Mission(
        name="test",
        system_prompt="You are a test agent.",
        max_steps=1,
    )


# =============================================================================
# Backend selection
# =============================================================================


class TestBackendSelection:
    def test_prefers_mcp_session_when_provided(self) -> None:
        """When mcp_session is set, agent should use sampling, not the SDK."""
        session = MagicMock()
        agent = DazzleAgent(_mock_observer(), _mock_executor(), mcp_session=session)
        assert agent._mcp_session is session

    def test_falls_back_to_anthropic_without_session(self) -> None:
        """Without mcp_session, agent should use the Anthropic SDK."""
        agent = DazzleAgent(_mock_observer(), _mock_executor(), api_key="test-key")
        assert agent._mcp_session is None


# =============================================================================
# MCP sampling path
# =============================================================================


class TestMcpSampling:
    @pytest.mark.asyncio
    async def test_decide_via_sampling_calls_create_message(self) -> None:
        """_decide_via_sampling should call session.create_message with correct args."""
        session = AsyncMock()
        session.create_message.return_value = MagicMock(
            content=MagicMock(text='{"action": "done", "success": true, "reasoning": "test"}'),
            model="claude-sonnet-4-20250514",
        )

        agent = DazzleAgent(_mock_observer(), _mock_executor(), mcp_session=session)

        messages = [{"role": "user", "content": "What do you see?"}]
        text, tokens = await agent._decide_via_sampling("system prompt", messages)

        session.create_message.assert_awaited_once()
        call_kwargs = session.create_message.call_args
        assert call_kwargs.kwargs["max_tokens"] == 800
        assert call_kwargs.kwargs["system_prompt"] == "system prompt"
        assert len(call_kwargs.kwargs["messages"]) == 1
        assert tokens == 0  # MCP sampling doesn't report token usage

    @pytest.mark.asyncio
    async def test_decide_via_sampling_handles_multipart_content(self) -> None:
        """Multipart messages (text + image) should extract only text parts."""
        session = AsyncMock()
        session.create_message.return_value = MagicMock(
            content=MagicMock(text='{"action": "done", "success": true, "reasoning": "ok"}'),
        )

        agent = DazzleAgent(_mock_observer(), _mock_executor(), mcp_session=session)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "data": "..."}},
                    {"type": "text", "text": "What do you see?"},
                ],
            }
        ]
        text, _ = await agent._decide_via_sampling("system", messages)

        # Should have extracted only the text part
        call_kwargs = session.create_message.call_args
        sampling_msg = call_kwargs.kwargs["messages"][0]
        assert "What do you see?" in sampling_msg.content.text

    @pytest.mark.asyncio
    async def test_agent_run_uses_sampling_when_session_set(self) -> None:
        """Full agent.run() should use MCP sampling when session is provided."""
        done_response = '{"action": "done", "success": true, "reasoning": "complete"}'
        session = AsyncMock()
        session.create_message.return_value = MagicMock(
            content=MagicMock(text=done_response),
        )

        observer = _mock_observer()
        executor = _mock_executor()
        agent = DazzleAgent(observer, executor, mcp_session=session)

        transcript = await agent.run(_simple_mission())

        assert transcript.outcome == "completed"
        session.create_message.assert_awaited_once()


# =============================================================================
# Anthropic SDK path
# =============================================================================


class TestAnthropicSdk:
    def test_decide_via_anthropic_calls_messages_create(self) -> None:
        """_decide_via_anthropic should call client.messages.create."""
        agent = DazzleAgent(_mock_observer(), _mock_executor(), api_key="test-key")

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.content = [
            MagicMock(text='{"action": "done", "success": true, "reasoning": "test"}')
        ]

        with patch.object(agent, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get.return_value = mock_client

            text, tokens = agent._decide_via_anthropic("system", [])

            mock_client.messages.create.assert_called_once()
            assert tokens == 150
            assert '"action": "done"' in text


# =============================================================================
# Accessibility observer
# =============================================================================


class TestAccessibilityObserver:
    def test_dom_mode_default(self) -> None:
        """Default PlaywrightObserver uses DOM mode."""
        page = MagicMock()
        obs = PlaywrightObserver(page)
        assert obs._mode == ObserverMode.DOM

    @pytest.mark.asyncio
    async def test_accessibility_snapshot(self) -> None:
        """Accessibility mode produces role-based selectors in PageState."""
        page = AsyncMock()
        page.url = "http://localhost:3000/"
        page.title = AsyncMock(return_value="Test")
        page.accessibility.snapshot = AsyncMock(
            return_value={
                "role": "WebArea",
                "name": "",
                "children": [
                    {"role": "button", "name": "Submit"},
                    {"role": "textbox", "name": "Username"},
                    {"role": "link", "name": "Home"},
                ],
            }
        )
        page.evaluate = AsyncMock(return_value="visible text")
        page.screenshot = AsyncMock(return_value=b"png")

        obs = PlaywrightObserver(page, mode="accessibility", include_screenshots=False)
        state = await obs.observe()

        assert len(state.clickables) == 2  # button + link
        assert len(state.inputs) == 1  # textbox
        assert state.clickables[0].selector == 'role=button[name="Submit"]'
        assert state.inputs[0].selector == 'role=textbox[name="Username"]'
        assert len(state.accessibility_tree) == 3

    @pytest.mark.asyncio
    async def test_accessibility_empty_snapshot(self) -> None:
        """None snapshot produces empty clickables/inputs."""
        page = AsyncMock()
        page.url = "http://localhost:3000/"
        page.title = AsyncMock(return_value="Empty")
        page.accessibility.snapshot = AsyncMock(return_value=None)
        page.evaluate = AsyncMock(return_value="")

        obs = PlaywrightObserver(page, mode="accessibility", include_screenshots=False)
        state = await obs.observe()

        assert state.clickables == []
        assert state.inputs == []
        assert state.accessibility_tree == []

    def test_flatten_tree_depth_cap(self) -> None:
        """Nodes deeper than 10 levels are ignored."""
        page = MagicMock()
        obs = PlaywrightObserver(page, include_screenshots=False)

        # Build a tree 12 levels deep with a button at the bottom
        node: dict = {"role": "button", "name": "Deep"}
        for _ in range(12):
            node = {"role": "generic", "name": "", "children": [node]}

        clickables: list = []
        inputs: list = []
        tree: list = []
        obs._flatten_a11y_tree(node, clickables, inputs, tree, depth=0)

        # The button at depth 12 should not be captured
        assert len(clickables) == 0

    def test_build_a11y_selector(self) -> None:
        """Various role/name combos produce correct selectors."""
        assert PlaywrightObserver._build_a11y_selector("button", "OK") == 'role=button[name="OK"]'
        assert PlaywrightObserver._build_a11y_selector("heading", "") == "role=heading"
        assert (
            PlaywrightObserver._build_a11y_selector("link", "Go Home")
            == 'role=link[name="Go Home"]'
        )

    def test_build_a11y_selector_quote_escaping(self) -> None:
        """Names containing quotes are escaped."""
        sel = PlaywrightObserver._build_a11y_selector("button", 'Say "hello"')
        assert sel == 'role=button[name="Say \\"hello\\""]'


# =============================================================================
# Console / network capture
# =============================================================================


class TestConsoleNetworkCapture:
    @pytest.mark.asyncio
    async def test_console_capture_errors(self) -> None:
        """Console errors and warnings are captured in PageState."""
        page = AsyncMock()
        page.url = "http://localhost:3000/"
        page.title = AsyncMock(return_value="Test")
        page.evaluate = AsyncMock(side_effect=["visible text", {}, {}])
        page.screenshot = AsyncMock(return_value=b"png")

        # Capture the handler registered via page.on("console", ...)
        console_handler = None

        def on_side_effect(event: str, handler: object) -> None:
            nonlocal console_handler
            if event == "console":
                console_handler = handler

        page.on = MagicMock(side_effect=on_side_effect)

        obs = PlaywrightObserver(page, mode="dom", capture_console=True, include_screenshots=False)

        # Simulate console messages
        assert console_handler is not None
        msg = MagicMock()
        msg.type = "error"
        msg.text = "Uncaught TypeError"
        msg.location = {"url": "app.js", "lineNumber": 42}
        console_handler(msg)

        # Re-mock evaluate for the three calls in _observe_dom
        page.evaluate = AsyncMock(side_effect=[[], [], "text", {}])
        state = await obs.observe()

        assert len(state.console_messages) == 1
        assert state.console_messages[0]["level"] == "error"
        assert state.console_messages[0]["text"] == "Uncaught TypeError"

    def test_console_capture_off_by_default(self) -> None:
        """No console listener when capture_console=False."""
        page = MagicMock()
        PlaywrightObserver(page, capture_console=False, capture_network=False)
        # page.on should not have been called
        page.on.assert_not_called()

    @pytest.mark.asyncio
    async def test_network_capture_errors(self) -> None:
        """4xx/5xx responses are captured in PageState."""
        page = AsyncMock()
        page.url = "http://localhost:3000/"
        page.title = AsyncMock(return_value="Test")

        response_handler = None

        def on_side_effect(event: str, handler: object) -> None:
            nonlocal response_handler
            if event == "response":
                response_handler = handler

        page.on = MagicMock(side_effect=on_side_effect)

        obs = PlaywrightObserver(page, mode="dom", capture_network=True, include_screenshots=False)

        assert response_handler is not None
        resp = MagicMock()
        resp.status = 500
        resp.url = "http://localhost:3000/api/data"
        resp.request.method = "POST"
        response_handler(resp)

        page.evaluate = AsyncMock(side_effect=[[], [], "text", {}])
        state = await obs.observe()

        assert len(state.network_errors) == 1
        assert state.network_errors[0]["status"] == 500
        assert state.network_errors[0]["method"] == "POST"

    def test_capture_truncation(self) -> None:
        """Buffers cap at 50 entries."""
        page = MagicMock()
        obs = PlaywrightObserver(page, capture_console=True, capture_network=True)

        for i in range(60):
            msg = MagicMock()
            msg.type = "error"
            msg.text = f"error {i}"
            msg.location = {}
            obs._on_console(msg)

            resp = MagicMock()
            resp.status = 404
            resp.url = f"http://localhost/{i}"
            resp.request.method = "GET"
            obs._on_response(resp)

        assert len(obs._console_buffer) == 50
        assert len(obs._network_buffer) == 50


# =============================================================================
# Executor role selectors
# =============================================================================


class TestExecutorRoleSelectors:
    def test_resolve_css_passthrough(self) -> None:
        """CSS selectors pass through to page.locator()."""
        page = MagicMock()
        executor = PlaywrightExecutor(page)
        executor._resolve_locator("#my-button")
        page.locator.assert_called_once_with("#my-button")

    def test_resolve_role_with_name(self) -> None:
        """role=button[name="X"] dispatches to get_by_role."""
        page = MagicMock()
        executor = PlaywrightExecutor(page)
        executor._resolve_locator('role=button[name="Submit"]')
        page.get_by_role.assert_called_once_with("button", name="Submit")

    def test_resolve_role_without_name(self) -> None:
        """role=heading dispatches to get_by_role without name."""
        page = MagicMock()
        executor = PlaywrightExecutor(page)
        executor._resolve_locator("role=heading")
        page.get_by_role.assert_called_once_with("heading")

    @pytest.mark.asyncio
    async def test_click_with_role_selector(self) -> None:
        """Full execute path with a role selector."""
        page = AsyncMock()
        page.get_by_role = MagicMock()
        locator = AsyncMock()
        page.get_by_role.return_value = locator

        executor = PlaywrightExecutor(page)
        action = AgentAction(type=ActionType.CLICK, target='role=button[name="Save"]')
        result = await executor.execute(action)

        page.get_by_role.assert_called_once_with("button", name="Save")
        locator.click.assert_awaited_once()
        assert result.error is None


# =============================================================================
# Viewport runner single-context optimization
# =============================================================================


class TestViewportRunnerResize:
    def test_single_context_created(self) -> None:
        """browser.new_context() is called exactly once."""
        from pathlib import Path

        from dazzle.testing.viewport import ComponentPattern, ViewportAssertion
        from dazzle.testing.viewport_runner import ViewportRunner, ViewportRunOptions

        runner = ViewportRunner(Path("/fake"))

        browser = MagicMock()
        context = MagicMock()
        browser.new_context.return_value = context
        page = MagicMock()
        context.new_page.return_value = page
        page.evaluate.return_value = [{"selector": ".x", "property": "display", "actual": "block"}]

        patterns = {
            "/": [
                ComponentPattern(
                    name="test",
                    assertions=[
                        ViewportAssertion(
                            selector=".x",
                            property="display",
                            expected="block",
                            viewport="mobile",
                            description="test",
                        ),
                        ViewportAssertion(
                            selector=".x",
                            property="display",
                            expected="block",
                            viewport="desktop",
                            description="test",
                        ),
                    ],
                )
            ]
        }

        from dazzle.testing.viewport_runner import ViewportRunResult

        result = ViewportRunResult(project_name="test")
        opts = ViewportRunOptions(include_suggestions=False)
        runner._run_matrix(browser, patterns, ["mobile", "desktop"], opts, result)

        browser.new_context.assert_called_once()
        assert page.set_viewport_size.call_count == 2

    def test_viewport_resize_per_viewport(self) -> None:
        """page.set_viewport_size() is called for each viewport."""
        from pathlib import Path

        from dazzle.testing.viewport import VIEWPORT_MATRIX, ComponentPattern, ViewportAssertion
        from dazzle.testing.viewport_runner import (
            ViewportRunner,
            ViewportRunOptions,
            ViewportRunResult,
        )

        runner = ViewportRunner(Path("/fake"))
        browser = MagicMock()
        context = MagicMock()
        browser.new_context.return_value = context
        page = MagicMock()
        context.new_page.return_value = page
        page.evaluate.return_value = [{"selector": ".x", "property": "display", "actual": "flex"}]

        patterns = {
            "/": [
                ComponentPattern(
                    name="t",
                    assertions=[
                        ViewportAssertion(
                            selector=".x",
                            property="display",
                            expected="flex",
                            viewport=vp,
                            description="t",
                        )
                        for vp in ["mobile", "tablet", "desktop"]
                    ],
                )
            ]
        }
        result = ViewportRunResult(project_name="test")
        opts = ViewportRunOptions(include_suggestions=False)
        runner._run_matrix(browser, patterns, ["mobile", "tablet", "desktop"], opts, result)

        sizes = [c.args[0] for c in page.set_viewport_size.call_args_list]
        assert sizes == [
            {
                "width": VIEWPORT_MATRIX["mobile"]["width"],
                "height": VIEWPORT_MATRIX["mobile"]["height"],
            },
            {
                "width": VIEWPORT_MATRIX["tablet"]["width"],
                "height": VIEWPORT_MATRIX["tablet"]["height"],
            },
            {
                "width": VIEWPORT_MATRIX["desktop"]["width"],
                "height": VIEWPORT_MATRIX["desktop"]["height"],
            },
        ]

    def test_cookies_injected_once(self) -> None:
        """context.add_cookies() is called once even with multiple viewports."""
        from pathlib import Path

        from dazzle.testing.viewport import ComponentPattern, ViewportAssertion
        from dazzle.testing.viewport_runner import (
            ViewportRunner,
            ViewportRunOptions,
            ViewportRunResult,
        )

        runner = ViewportRunner(Path("/fake"))
        browser = MagicMock()
        context = MagicMock()
        browser.new_context.return_value = context
        page = MagicMock()
        context.new_page.return_value = page
        page.evaluate.return_value = [{"selector": ".x", "property": "display", "actual": "block"}]

        patterns = {
            "/": [
                ComponentPattern(
                    name="t",
                    assertions=[
                        ViewportAssertion(
                            selector=".x",
                            property="display",
                            expected="block",
                            viewport="mobile",
                            description="t",
                        )
                    ],
                )
            ]
        }
        result = ViewportRunResult(project_name="test")
        opts = ViewportRunOptions(persona_id="admin", include_suggestions=False)

        with patch(
            "dazzle.testing.viewport_auth.load_persona_cookies",
            return_value=[{"name": "session", "value": "abc", "url": "http://localhost:3000"}],
        ):
            runner._run_matrix(browser, patterns, ["mobile", "desktop"], opts, result)

        context.add_cookies.assert_called_once()


# =============================================================================
# PageState prompt rendering
# =============================================================================


class TestPageStatePrompt:
    def test_to_prompt_accessibility_mode(self) -> None:
        """Accessibility tree renders unified Interactive Elements section."""
        state = PageState(
            url="http://localhost:3000/",
            title="Test",
            accessibility_tree=[
                {"role": "button", "name": "Save", "selector": 'role=button[name="Save"]'},
                {"role": "textbox", "name": "Email", "selector": 'role=textbox[name="Email"]'},
            ],
        )
        prompt = state.to_prompt()
        assert "### Interactive Elements" in prompt
        assert "### Clickable Elements" not in prompt
        assert 'button: "Save"' in prompt
        assert 'textbox: "Email"' in prompt

    def test_to_prompt_console_messages(self) -> None:
        """Console messages section appears when present."""
        state = PageState(
            url="http://localhost:3000/",
            title="Test",
            console_messages=[
                {"level": "error", "text": "Uncaught TypeError", "url": "app.js", "line_number": 1}
            ],
        )
        prompt = state.to_prompt()
        assert "### Console Messages" in prompt
        assert "[error] Uncaught TypeError" in prompt

    def test_to_prompt_network_errors(self) -> None:
        """Network errors section appears when present."""
        state = PageState(
            url="http://localhost:3000/",
            title="Test",
            network_errors=[
                {"method": "POST", "url": "http://localhost:3000/api/data", "status": 500}
            ],
        )
        prompt = state.to_prompt()
        assert "### Network Errors" in prompt
        assert "POST http://localhost:3000/api/data -> 500" in prompt

    def test_to_prompt_includes_clickable_attrs(self) -> None:
        """Clickable elements include href/hx-get/hx-post in prompt."""
        from dazzle.agent.models import Element

        state = PageState(
            url="http://localhost:3000/",
            title="Test",
            clickables=[
                Element(
                    tag="a",
                    text="Login",
                    selector='a[href="/login"]',
                    attributes={"href": "/login"},
                ),
                Element(
                    tag="button",
                    text="Save",
                    selector="button",
                    attributes={"hx-post": "/api/save"},
                ),
            ],
        )
        prompt = state.to_prompt()
        assert "href=/login" in prompt
        assert "hx-post=/api/save" in prompt


# =============================================================================
# HttpExecutor — href extraction from CSS selectors
# =============================================================================


class TestHttpExecutorClick:
    """Test that _click extracts href from selectors instead of no-oping."""

    @pytest.mark.asyncio
    async def test_click_extracts_href_from_selector(self) -> None:
        from dazzle.agent.executor import HttpExecutor

        client = AsyncMock()
        response = MagicMock()
        response.url = "http://localhost:3000/login"
        response.text = "<html></html>"
        response.status_code = 200
        client.get = AsyncMock(return_value=response)

        executor = HttpExecutor(client, "http://localhost:3000")
        action = AgentAction(type=ActionType.CLICK, target='a[href="/login"]')
        result = await executor.execute(action)

        client.get.assert_called_once_with("http://localhost:3000/login", follow_redirects=True)
        assert "Navigated" in result.message

    @pytest.mark.asyncio
    async def test_click_extracts_hx_get_from_selector(self) -> None:
        from dazzle.agent.executor import HttpExecutor

        client = AsyncMock()
        response = MagicMock()
        response.url = "http://localhost:3000/api/data"
        response.text = "<html></html>"
        response.status_code = 200
        client.get = AsyncMock(return_value=response)

        executor = HttpExecutor(client, "http://localhost:3000")
        action = AgentAction(type=ActionType.CLICK, target='div[hx-get="/api/data"]')
        result = await executor.execute(action)

        client.get.assert_called_once()
        assert "Navigated" in result.message

    @pytest.mark.asyncio
    async def test_click_falls_back_gracefully(self) -> None:
        from dazzle.agent.executor import HttpExecutor

        client = AsyncMock()
        executor = HttpExecutor(client, "http://localhost:3000")
        action = AgentAction(type=ActionType.CLICK, target="button.submit")
        result = await executor.execute(action)

        assert "Click on button.submit" in result.message
        client.get.assert_not_called()
