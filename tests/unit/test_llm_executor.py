"""Unit tests for LLMIntentExecutor."""

from unittest.mock import AsyncMock, MagicMock, patch

import jinja2
import pytest

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec
from dazzle.core.ir.llm import (
    LLMConfigSpec,
    LLMIntentSpec,
    LLMModelSpec,
    LLMProvider,
    RetryBackoff,
    RetryPolicySpec,
)
from dazzle_back.runtime.llm_executor import LLMIntentExecutor


def _make_model(
    name: str = "test_model",
    provider: LLMProvider = LLMProvider.ANTHROPIC,
    model_id: str = "claude-3-haiku-20240307",
) -> LLMModelSpec:
    return LLMModelSpec(name=name, provider=provider, model_id=model_id)


def _make_intent(
    name: str = "summarize",
    model_ref: str | None = "test_model",
    prompt_template: str = "Summarise: {{ input.text }}",
    timeout_seconds: int = 30,
    retry: RetryPolicySpec | None = None,
) -> LLMIntentSpec:
    return LLMIntentSpec(
        name=name,
        model_ref=model_ref,
        prompt_template=prompt_template,
        timeout_seconds=timeout_seconds,
        retry=retry,
        description="Test intent",
    )


def _make_appspec(
    models: list[LLMModelSpec] | None = None,
    intents: list[LLMIntentSpec] | None = None,
    config: LLMConfigSpec | None = None,
) -> AppSpec:
    return AppSpec(
        module_name="test",
        name="test",
        domain=DomainSpec(),
        llm_models=models or [_make_model()],
        llm_intents=intents or [_make_intent()],
        llm_config=config or LLMConfigSpec(default_model="test_model"),
    )


# ── Prompt rendering ──────────────────────────────────────────────────


class TestPromptRendering:
    def test_renders_valid_template(self) -> None:
        result = LLMIntentExecutor._render_prompt("Hello {{ input.name }}", {"name": "World"})
        assert result == "Hello World"

    def test_missing_var_raises(self) -> None:
        with pytest.raises(jinja2.UndefinedError):
            LLMIntentExecutor._render_prompt("{{ input.missing }}", {})

    def test_complex_template(self) -> None:
        tpl = "{% for item in input.tags %}{{ item }},{% endfor %}"
        result = LLMIntentExecutor._render_prompt(tpl, {"tags": ["a", "b"]})
        assert result == "a,b,"


# ── Model resolution ─────────────────────────────────────────────────


class TestModelResolution:
    def test_resolves_explicit_ref(self) -> None:
        executor = LLMIntentExecutor(_make_appspec())
        intent = _make_intent(model_ref="test_model")
        model = executor._resolve_model(intent)
        assert model.name == "test_model"

    def test_resolves_default_model(self) -> None:
        executor = LLMIntentExecutor(
            _make_appspec(
                intents=[_make_intent(model_ref=None)],
                config=LLMConfigSpec(default_model="test_model"),
            )
        )
        intent = _make_intent(model_ref=None)
        model = executor._resolve_model(intent)
        assert model.name == "test_model"

    def test_unknown_ref_raises(self) -> None:
        executor = LLMIntentExecutor(_make_appspec())
        intent = _make_intent(model_ref="nonexistent")
        with pytest.raises(ValueError, match="unknown model"):
            executor._resolve_model(intent)

    def test_no_ref_and_no_default_raises(self) -> None:
        executor = LLMIntentExecutor(
            _make_appspec(
                intents=[_make_intent(model_ref=None)],
                config=LLMConfigSpec(),
            )
        )
        intent = _make_intent(model_ref=None)
        with pytest.raises(ValueError, match="no model_ref"):
            executor._resolve_model(intent)


# ── Execute ───────────────────────────────────────────────────────────


class TestExecute:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        executor = LLMIntentExecutor(_make_appspec())
        with patch.object(LLMIntentExecutor, "_build_client") as mock_build:
            mock_client = MagicMock()
            mock_client.complete.return_value = "Summary result"
            mock_build.return_value = mock_client

            result = await executor.execute("summarize", {"text": "hello"})

        assert result.success is True
        assert result.output == "Summary result"
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_unknown_intent(self) -> None:
        executor = LLMIntentExecutor(_make_appspec())
        result = await executor.execute("nonexistent", {})
        assert result.success is False
        assert "Unknown intent" in (result.error or "")

    @pytest.mark.asyncio
    async def test_bad_template(self) -> None:
        appspec = _make_appspec(intents=[_make_intent(prompt_template="{{ input.missing }}")])
        executor = LLMIntentExecutor(appspec)
        with patch.object(LLMIntentExecutor, "_build_client"):
            result = await executor.execute("summarize", {})
        assert result.success is False
        assert "template" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_client_error(self) -> None:
        executor = LLMIntentExecutor(_make_appspec())
        with patch.object(LLMIntentExecutor, "_build_client", side_effect=ValueError("No API key")):
            result = await executor.execute("summarize", {"text": "x"})
        assert result.success is False
        assert "No API key" in (result.error or "")

    @pytest.mark.asyncio
    async def test_retry_success_on_third_attempt(self) -> None:
        retry = RetryPolicySpec(
            max_attempts=3,
            backoff=RetryBackoff.LINEAR,
            initial_delay_ms=100,
            max_delay_ms=1000,
        )
        appspec = _make_appspec(intents=[_make_intent(retry=retry)])
        executor = LLMIntentExecutor(appspec)

        call_count = 0

        def complete_side_effect(sys_prompt: str, user_prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("temporary failure")
            return "success after retries"

        with patch.object(LLMIntentExecutor, "_build_client") as mock_build:
            mock_client = MagicMock()
            mock_client.complete.side_effect = complete_side_effect
            mock_build.return_value = mock_client

            result = await executor.execute("summarize", {"text": "x"})

        assert result.success is True
        assert result.output == "success after retries"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        appspec = _make_appspec(intents=[_make_intent(timeout_seconds=1)])
        executor = LLMIntentExecutor(appspec)

        def slow_complete(sys_prompt: str, user_prompt: str) -> str:
            import time

            time.sleep(5)
            return "should not reach"

        with patch.object(LLMIntentExecutor, "_build_client") as mock_build:
            mock_client = MagicMock()
            mock_client.complete.side_effect = slow_complete
            mock_build.return_value = mock_client

            result = await executor.execute("summarize", {"text": "x"})

        assert result.success is False
        assert "Timeout" in (result.error or "")

    @pytest.mark.asyncio
    async def test_ai_job_recorded(self) -> None:
        mock_service = AsyncMock()
        mock_service.execute.return_value = {"id": "job-123"}

        executor = LLMIntentExecutor(_make_appspec(), ai_job_service=mock_service)

        with patch.object(LLMIntentExecutor, "_build_client") as mock_build:
            mock_client = MagicMock()
            mock_client.complete.return_value = "result"
            mock_build.return_value = mock_client

            result = await executor.execute("summarize", {"text": "x"}, user_id="user-1")

        assert result.job_id == "job-123"
        mock_service.execute.assert_called_once()
        call_kwargs = mock_service.execute.call_args
        assert call_kwargs[1]["data"]["intent"] == "summarize"
        assert call_kwargs[1]["data"]["user_id"] == "user-1"


# ── List helpers ──────────────────────────────────────────────────────


class TestListHelpers:
    def test_list_intents(self) -> None:
        executor = LLMIntentExecutor(_make_appspec())
        intents = executor.list_intents()
        assert len(intents) == 1
        assert intents[0]["name"] == "summarize"

    def test_list_models(self) -> None:
        executor = LLMIntentExecutor(_make_appspec())
        models = executor.list_models()
        assert len(models) == 1
        assert models[0]["name"] == "test_model"
        assert models[0]["provider"] == "anthropic"
