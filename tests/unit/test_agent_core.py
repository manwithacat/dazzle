"""Tests for DazzleAgent core — LLM backend selection, MCP sampling,
observer modes, executor selectors, and viewport runner optimization."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.agent.core import DazzleAgent, Mission
from dazzle.agent.executor import PlaywrightExecutor
from dazzle.agent.models import ActionType, AgentAction, PageState
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


class TestStepBudgetNudge:
    """#818: when the step budget is nearly exhausted, `_build_messages`
    injects a hard reminder pointing at the mission's terminal tool.

    Before this, trial runs ended at ``max_steps`` 100% of the time
    without the agent ever calling ``submit_verdict`` — the synthesis
    fallback had to generate every verdict."""

    def _agent(self) -> DazzleAgent:
        return DazzleAgent(observer=_mock_observer(), executor=_mock_executor())

    def _state(self) -> PageState:
        return PageState(url="u", title="t", visible_text="")

    def _mission_with_terminal(self) -> Mission:
        return Mission(
            name="trial:x",
            system_prompt="p",
            max_steps=30,
            terminal_tools=["submit_verdict"],
        )

    def _history(self, agent: DazzleAgent, n: int) -> None:
        from dazzle.agent.models import ActionType, AgentAction, Step

        agent._history = [
            Step(
                state=self._state(),
                action=AgentAction(type=ActionType.NAVIGATE, target="/"),
                result=MagicMock(state_changed=True),
                step_number=i,
                duration_ms=1.0,
            )
            for i in range(1, n + 1)
        ]

    def test_no_nudge_mid_run(self) -> None:
        """At 20 steps remaining, no wrap-up pressure applied."""
        agent = self._agent()
        self._history(agent, 10)
        msgs = agent._build_messages(
            self._state(), steps_remaining=20, mission=self._mission_with_terminal()
        )
        rendered = str(msgs)
        assert "step(s) left" not in rendered
        assert "submit_verdict" not in rendered

    def test_nudge_at_five_steps_remaining(self) -> None:
        """Near terminal — nudge cites the mission's terminal tool."""
        agent = self._agent()
        self._history(agent, 25)
        msgs = agent._build_messages(
            self._state(), steps_remaining=5, mission=self._mission_with_terminal()
        )
        rendered = str(msgs)
        assert "5 step(s) left" in rendered
        assert "submit_verdict" in rendered

    def test_nudge_uses_done_when_no_terminal_tool(self) -> None:
        """No terminal_tool → nudge says `done` instead."""
        agent = self._agent()
        self._history(agent, 25)
        mission = Mission(name="x", system_prompt="p", max_steps=30)
        msgs = agent._build_messages(self._state(), steps_remaining=3, mission=mission)
        rendered = str(msgs)
        assert "3 step(s) left" in rendered
        assert "`done`" in rendered


# =============================================================================
# Backend selection (continued below)
# =============================================================================


# =============================================================================
# Backend selection
# =============================================================================


class TestBackendSelection:
    def test_mcp_session_routing(self) -> None:
        """With mcp_session set, agent stores it; without, it stays None."""
        session = MagicMock()
        with_session = DazzleAgent(_mock_observer(), _mock_executor(), mcp_session=session)
        assert with_session._mcp_session is session
        without_session = DazzleAgent(_mock_observer(), _mock_executor(), api_key="test-key")
        assert without_session._mcp_session is None


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
# Claude CLI driver path (subscription-billed, text protocol)
# =============================================================================


class TestClaudeCliDriver:
    def test_tool_calls_forced_off_under_cli_driver(self) -> None:
        """claude -p is a text pipe; native tool use must downgrade to
        the text protocol exactly like the MCP sampling path does."""
        agent = DazzleAgent(
            _mock_observer(),
            _mock_executor(),
            use_tool_calls=True,
            llm_driver="claude-cli",
        )
        assert agent._use_tool_calls is False

    def test_default_model_follows_llm_driver(self) -> None:
        """grok-cli must not inherit the Claude judgment pin (unknown model id)."""
        from dazzle.core.model_defaults import (
            DEFAULT_GROK_JUDGMENT_MODEL,
            DEFAULT_JUDGMENT_MODEL,
        )

        claude = DazzleAgent(_mock_observer(), _mock_executor(), llm_driver="claude-cli")
        grok = DazzleAgent(_mock_observer(), _mock_executor(), llm_driver="grok-cli")
        assert claude._model == DEFAULT_JUDGMENT_MODEL
        assert grok._model == DEFAULT_GROK_JUDGMENT_MODEL

    @pytest.mark.asyncio
    async def test_decide_routes_to_claude_cli(self) -> None:
        agent = DazzleAgent(_mock_observer(), _mock_executor(), llm_driver="claude-cli")
        state = PageState(url="u", title="t", visible_text="")
        with patch(
            "dazzle.llm.driver.call_claude_cli",
            return_value=('{"action": "done", "success": true, "reasoning": "r"}', 42),
        ) as mock_cli:
            action, _prompt, _resp, tokens = await agent._decide(_simple_mission(), state, {})
        mock_cli.assert_called_once()
        assert action.type == ActionType.DONE
        assert tokens == 42

    def test_messages_flattened_to_single_prompt(self) -> None:
        """History + state must arrive as one prompt string; image parts
        are skipped (same contract as the MCP sampling path)."""
        agent = DazzleAgent(_mock_observer(), _mock_executor(), llm_driver="claude-cli")
        messages = [
            {"role": "user", "content": "## Previous Actions\nstep one"},
            {"role": "assistant", "content": "I understand. What's the current state?"},
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"data": "..."}},
                    {"type": "text", "text": "current state text"},
                ],
            },
        ]
        with patch("dazzle.llm.driver.call_claude_cli", return_value=("ok", 0)) as mock_cli:
            agent._decide_via_claude_cli("sys", messages)
        prompt = mock_cli.call_args.args[0]
        assert "step one" in prompt
        assert "current state text" in prompt
        assert "image" not in prompt
        assert mock_cli.call_args.kwargs["system_prompt"] == "sys"

    def test_default_driver_unchanged(self) -> None:
        """Default construction keeps the SDK path — existing callers
        see no behavior change."""
        agent = DazzleAgent(_mock_observer(), _mock_executor(), use_tool_calls=True)
        assert agent._llm_driver == "anthropic-api"
        assert agent._use_tool_calls is True


# =============================================================================
# Accessibility observer
# =============================================================================


class TestAccessibilityObserver:
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

    @pytest.mark.parametrize(
        "role,name,expected",
        [
            ("button", "OK", 'role=button[name="OK"]'),
            ("heading", "", "role=heading"),
            ("link", "Go Home", 'role=link[name="Go Home"]'),
            ("button", 'Say "hello"', 'role=button[name="Say \\"hello\\""]'),
        ],
        ids=[
            "test_build_a11y_selector_button",
            "test_build_a11y_selector_no_name",
            "test_build_a11y_selector_link",
            "test_build_a11y_selector_quote_escaping",
        ],
    )
    def test_build_a11y_selector(self, role: str, name: str, expected: str) -> None:
        """Various role/name combos (with quote-escape) produce correct selectors."""
        assert PlaywrightObserver._build_a11y_selector(role, name) == expected


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
    @pytest.mark.parametrize(
        "selector,expected_method,expected_args,expected_kwargs",
        [
            ("#my-button", "locator", ("#my-button",), {}),
            ('role=button[name="Submit"]', "get_by_role", ("button",), {"name": "Submit"}),
            ("role=heading", "get_by_role", ("heading",), {}),
        ],
        ids=[
            "test_resolve_css_passthrough",
            "test_resolve_role_with_name",
            "test_resolve_role_without_name",
        ],
    )
    def test_resolve_locator_dispatch(
        self,
        selector: str,
        expected_method: str,
        expected_args: tuple,
        expected_kwargs: dict,
    ) -> None:
        """_resolve_locator dispatches to the right Playwright API."""
        page = MagicMock()
        executor = PlaywrightExecutor(page)
        executor._resolve_locator(selector)
        getattr(page, expected_method).assert_called_once_with(*expected_args, **expected_kwargs)

    @pytest.mark.asyncio
    async def test_click_with_role_selector(self) -> None:
        """Full execute path with a role selector."""
        page = AsyncMock()
        # PlaywrightExecutor.__init__ calls page.on("console", ...); it must
        # be a plain sync registration, not an awaitable.
        page.on = MagicMock()
        # execute() captures before/after state via page.url (sync attr) and
        # page.content() (async) — feed realistic values so _dom_hash can
        # hash a real string and state diff comparisons work.
        page.url = "http://test/"
        page.content.return_value = "<html></html>"
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

    @pytest.mark.parametrize(
        "target,resolved_url,should_navigate",
        [
            ('a[href="/login"]', "http://localhost:3000/login", True),
            ('div[hx-get="/api/data"]', "http://localhost:3000/api/data", True),
            ("button.submit", None, False),
        ],
        ids=[
            "test_click_extracts_href_from_selector",
            "test_click_extracts_hx_get_from_selector",
            "test_click_falls_back_gracefully",
        ],
    )
    @pytest.mark.asyncio
    async def test_click_dispatch(
        self, target: str, resolved_url: str | None, should_navigate: bool
    ) -> None:
        from dazzle.agent.executor import HttpExecutor

        client = AsyncMock()
        if should_navigate:
            response = MagicMock()
            response.url = resolved_url
            response.text = "<html></html>"
            response.status_code = 200
            client.get = AsyncMock(return_value=response)

        executor = HttpExecutor(client, "http://localhost:3000")
        action = AgentAction(type=ActionType.CLICK, target=target)
        result = await executor.execute(action)

        if should_navigate:
            client.get.assert_called_once()
            assert "Navigated" in result.message
        else:
            client.get.assert_not_called()
            assert f"Click on {target}" in result.message
