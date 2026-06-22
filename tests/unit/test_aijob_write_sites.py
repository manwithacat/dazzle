"""Tests for AIJob write sites — subject_type/subject_id required columns.

#1454 closed-system AI cognition: every AIJob must name a subject.
Verifies that:
- _record_job writes subject_type/subject_id (NOT entity_type/entity_id) into the create payload.
- submit (LLMJobQueue) raises ValueError when subject_type or subject_id is missing/empty.
- execute (LLMIntentExecutor) raises ValueError when subject is missing/empty.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec
from dazzle.core.ir.llm import (
    LLMConfigSpec,
    LLMIntentSpec,
    LLMModelSpec,
    LLMProvider,
)
from dazzle.http.runtime.llm_executor import LLMIntentExecutor
from dazzle.http.runtime.llm_queue import LLMJobQueue

# ---------------------------------------------------------------------------
# Helpers (mirror test_llm_executor.py / test_llm_queue.py patterns)
# ---------------------------------------------------------------------------


def _make_model(name: str = "test_model") -> LLMModelSpec:
    return LLMModelSpec(
        name=name, provider=LLMProvider.ANTHROPIC, model_id="claude-3-haiku-20240307"
    )


def _make_intent(name: str = "summarize") -> LLMIntentSpec:
    return LLMIntentSpec(
        name=name,
        model_ref="test_model",
        prompt_template="Summarise: $text",
        timeout_seconds=30,
        description="Test intent",
    )


def _make_appspec() -> AppSpec:
    return AppSpec(
        module_name="test",
        name="test",
        domain=DomainSpec(),
        llm_models=[_make_model()],
        llm_intents=[_make_intent()],
        llm_config=LLMConfigSpec(default_model="test_model"),
    )


def _mock_queue_executor(appspec=None):
    executor = MagicMock()
    executor._appspec = appspec or MagicMock()
    executor._appspec.llm_intents = []
    executor._appspec.llm_config = MagicMock()
    executor._appspec.llm_config.default_model = "claude"

    async def mock_execute(
        intent_name, input_data, user_id=None, subject_type=None, subject_id=None
    ):
        result = MagicMock()
        result.success = True
        result.output = "result"
        result.tokens_in = 0
        result.tokens_out = 0
        result.cost_usd = None
        result.duration_ms = 100
        result.error = None
        result.job_id = None
        return result

    executor.execute = mock_execute
    return executor


# ---------------------------------------------------------------------------
# Test: _record_job writes subject_type / subject_id (NOT entity_type/entity_id)
# ---------------------------------------------------------------------------


class TestRecordJobWritesSubjectColumns:
    @pytest.mark.asyncio
    async def test_record_job_payload_has_subject_keys(self) -> None:
        """_record_job must write subject_type/subject_id into the AIJob create payload."""
        captured: list[dict] = []

        mock_service = AsyncMock()

        async def capture_execute(*, action: str, data: dict | None = None, **kw):
            if data is not None:
                captured.append(dict(data))
            return {"id": "job-abc"}

        mock_service.execute.side_effect = capture_execute

        executor = LLMIntentExecutor(_make_appspec(), ai_job_service=mock_service)

        with patch.object(LLMIntentExecutor, "_build_client") as mock_build:
            mock_client = MagicMock()
            mock_client.complete.return_value = "Summary result"
            mock_build.return_value = mock_client

            result = await executor.execute(
                "summarize",
                {"text": "hello"},
                user_id="user-1",
                subject_type="Doc",
                subject_id="11111111-1111-1111-1111-111111111111",
            )

        assert result.success is True
        assert len(captured) == 1, "Expected exactly one AIJob create call"
        payload = captured[0]

        # Must use the new column names
        assert "subject_type" in payload, "payload missing subject_type"
        assert "subject_id" in payload, "payload missing subject_id"
        assert payload["subject_type"] == "Doc"
        assert payload["subject_id"] == "11111111-1111-1111-1111-111111111111"

        # Must NOT use the old column names
        assert "entity_type" not in payload, "payload still uses entity_type (old name)"
        assert "entity_id" not in payload, "payload still uses entity_id (old name)"

    @pytest.mark.asyncio
    async def test_queue_submit_payload_has_subject_keys(self) -> None:
        """LLMJobQueue.submit must write subject_type/subject_id into the AIJob create payload."""
        captured: list[dict] = []

        class FakeService:
            def execute(self, *, action: str, data: dict | None = None, **kw):
                if data is not None:
                    captured.append(dict(data))
                return {"id": "job-xyz"}

        queue = LLMJobQueue(executor=_mock_queue_executor(), ai_job_service=FakeService())

        job_id = await queue.submit(
            "classify",
            {"title": "test"},
            subject_type="Task",
            subject_id="22222222-2222-2222-2222-222222222222",
            user_id="user-2",
        )

        assert isinstance(job_id, str) and len(job_id) > 0
        assert len(captured) == 1, "Expected exactly one AIJob create call"
        payload = captured[0]

        assert "subject_type" in payload, "payload missing subject_type"
        assert "subject_id" in payload, "payload missing subject_id"
        assert payload["subject_type"] == "Task"
        assert payload["subject_id"] == "22222222-2222-2222-2222-222222222222"

        assert "entity_type" not in payload, "payload still uses entity_type (old name)"
        assert "entity_id" not in payload, "payload still uses entity_id (old name)"


# ---------------------------------------------------------------------------
# Test: subject required — raise ValueError if missing/empty
# ---------------------------------------------------------------------------


class TestSubjectRequired:
    @pytest.mark.asyncio
    async def test_submit_raises_without_subject_type(self) -> None:
        """LLMJobQueue.submit must raise ValueError when subject_type is absent."""
        queue = LLMJobQueue(executor=_mock_queue_executor())
        with pytest.raises(ValueError, match="#1454"):
            await queue.submit(
                "classify",
                {"title": "test"},
                subject_type="",
                subject_id="22222222-2222-2222-2222-222222222222",
            )

    @pytest.mark.asyncio
    async def test_submit_raises_without_subject_id(self) -> None:
        """LLMJobQueue.submit must raise ValueError when subject_id is absent."""
        queue = LLMJobQueue(executor=_mock_queue_executor())
        with pytest.raises(ValueError, match="#1454"):
            await queue.submit(
                "classify",
                {"title": "test"},
                subject_type="Task",
                subject_id="",
            )

    @pytest.mark.asyncio
    async def test_execute_raises_without_subject(self) -> None:
        """LLMIntentExecutor.execute must raise ValueError when subject is missing."""
        executor = LLMIntentExecutor(_make_appspec())
        with pytest.raises(ValueError, match="#1454"):
            await executor.execute(
                "summarize",
                {"text": "hello"},
                subject_type="",
                subject_id="",
            )

    @pytest.mark.asyncio
    async def test_execute_raises_with_missing_subject_type(self) -> None:
        """LLMIntentExecutor.execute must raise ValueError when subject_type is empty."""
        executor = LLMIntentExecutor(_make_appspec())
        with pytest.raises(ValueError, match="#1454"):
            await executor.execute(
                "summarize",
                {"text": "hello"},
                subject_type="",
                subject_id="11111111-1111-1111-1111-111111111111",
            )
