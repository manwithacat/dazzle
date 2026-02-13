"""Tests for DazzleAgent core — LLM backend selection and MCP sampling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.agent.core import DazzleAgent, Mission
from dazzle.agent.models import PageState

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
