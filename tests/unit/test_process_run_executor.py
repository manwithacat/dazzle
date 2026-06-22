"""TDD tests for ProcessRun row creation + process-step AI subject (#1454).

Task 4: ProcessExecutor.execute() creates a ProcessRun row (status running→completed/failed),
stores run_id on ProcessContext, and _execute_llm_step passes subject_type="ProcessRun",
subject_id=context.run_id to the LLM executor.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.core.ir.process import ProcessSpec, ProcessStepSpec, StepKind
from dazzle.http.runtime.process_executor import (
    ProcessExecutor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_appspec(processes=None):
    appspec = MagicMock()
    appspec.processes = processes or []
    return appspec


def _make_step(name, kind=StepKind.SERVICE, **kwargs):
    return ProcessStepSpec(name=name, kind=kind, **kwargs)


def _make_process(name, steps):
    return ProcessSpec(name=name, steps=steps)


class FakeProcessRunService:
    """Minimal fake that records create/update calls, mimicking the action= convention."""

    def __init__(self, created_id: str = "run-uuid-1234"):
        self._created_id = created_id
        self.create_calls: list[dict] = []
        self.update_calls: list[dict] = []

    async def execute(
        self, *, action: str, data: dict | None = None, record_id: str | None = None, **kw: Any
    ) -> dict:
        if action == "create":
            self.create_calls.append(dict(data or {}))
            return {"id": self._created_id}
        elif action == "update":
            self.update_calls.append({"record_id": record_id, "data": dict(data or {})})
            return {"id": record_id}
        return {}


def _mock_llm_executor(output='{"category": "billing"}', success=True, error=None):
    executor = MagicMock()
    captured_calls: list[dict] = []

    async def mock_execute(intent_name, input_data, *, subject_type, subject_id, **kwargs):
        captured_calls.append(
            {
                "intent_name": intent_name,
                "input_data": input_data,
                "subject_type": subject_type,
                "subject_id": subject_id,
            }
        )
        result = MagicMock()
        result.success = success
        result.output = output
        result.error = error
        return result

    executor.execute = mock_execute
    executor._captured_calls = captured_calls
    return executor


# ---------------------------------------------------------------------------
# ProcessRun row creation tests
# ---------------------------------------------------------------------------


class TestProcessRunRowCreation:
    @pytest.mark.asyncio
    async def test_creates_process_run_row_on_execute(self):
        """A ProcessRun row is created at the start of execute() with status=running."""
        step = _make_step("svc", kind=StepKind.SERVICE, service="DummyService.execute")
        process = _make_process("my_flow", [step])

        svc = MagicMock()
        svc.execute = AsyncMock(return_value={"ok": True})

        pr_service = FakeProcessRunService(created_id="run-abc-123")
        executor = ProcessExecutor(
            _make_appspec([process]),
            services={"DummyService": svc},
            process_run_service=pr_service,
        )

        await executor.execute("my_flow", user_id="user-42")

        assert len(pr_service.create_calls) == 1, "Expected one ProcessRun create call"
        payload = pr_service.create_calls[0]
        assert payload["process_name"] == "my_flow"
        assert payload["started_by"] == "user-42"
        assert payload["status"] == "running"

    @pytest.mark.asyncio
    async def test_run_id_stored_on_context_via_run_result(self):
        """The run_id captured from the create response is stored on the context."""
        step = _make_step("svc", kind=StepKind.SERVICE, service="DummyService.run")
        process = _make_process("flow", [step])

        svc = MagicMock()
        svc.run = AsyncMock(return_value="done")

        pr_service = FakeProcessRunService(created_id="run-xyz-456")
        executor = ProcessExecutor(
            _make_appspec([process]),
            services={"DummyService": svc},
            process_run_service=pr_service,
        )

        result = await executor.execute("flow", user_id="user-1")
        assert result.success
        # run_id is stored on the ProcessResult for observability
        assert result.run_id == "run-xyz-456"

    @pytest.mark.asyncio
    async def test_process_run_status_completed_on_success(self):
        """ProcessRun status is updated to completed when the process succeeds."""
        step = _make_step("svc", kind=StepKind.CONDITION, condition="trigger.x == y")
        process = _make_process("flow", [step])

        pr_service = FakeProcessRunService(created_id="run-1")
        executor = ProcessExecutor(
            _make_appspec([process]),
            process_run_service=pr_service,
        )

        result = await executor.execute(
            "flow",
            trigger_data={"x": "y"},
            user_id="u1",
        )
        assert result.success

        assert len(pr_service.update_calls) >= 1
        final_update = pr_service.update_calls[-1]
        assert final_update["record_id"] == "run-1"
        assert final_update["data"]["status"] == "completed"
        assert "finished_at" in final_update["data"]

    @pytest.mark.asyncio
    async def test_process_run_status_failed_on_step_failure(self):
        """ProcessRun status is updated to failed when a step fails."""
        step = _make_step(
            "classify",
            kind=StepKind.LLM_INTENT,
            llm_intent="classify_ticket",
        )
        process = _make_process("flow", [step])
        llm_exec = _mock_llm_executor(success=False, error="API error")

        pr_service = FakeProcessRunService(created_id="run-2")
        executor = ProcessExecutor(
            _make_appspec([process]),
            llm_executor=llm_exec,
            process_run_service=pr_service,
        )

        result = await executor.execute("flow", user_id="u2")
        assert not result.success

        assert len(pr_service.update_calls) >= 1
        final_update = pr_service.update_calls[-1]
        assert final_update["record_id"] == "run-2"
        assert final_update["data"]["status"] == "failed"
        assert "error_message" in final_update["data"]
        assert "finished_at" in final_update["data"]

    @pytest.mark.asyncio
    async def test_no_process_run_when_service_is_none(self):
        """If no process_run_service is injected, execute runs without creating a row."""
        step = _make_step("check", kind=StepKind.CONDITION, condition="trigger.a == b")
        process = _make_process("flow", [step])

        executor = ProcessExecutor(_make_appspec([process]))

        result = await executor.execute(
            "flow",
            trigger_data={"a": "b"},
            user_id="u3",
        )
        assert result.success  # still works without a service


# ---------------------------------------------------------------------------
# LLM step subject tests
# ---------------------------------------------------------------------------


class TestLLMStepSubjectPassthrough:
    @pytest.mark.asyncio
    async def test_llm_step_called_with_process_run_subject(self):
        """_execute_llm_step must pass subject_type='ProcessRun' and subject_id=run_id."""
        step = _make_step(
            "classify",
            kind=StepKind.LLM_INTENT,
            llm_intent="classify_ticket",
            llm_input_map={"title": "trigger.entity.title"},
        )
        process = _make_process("classify_flow", [step])
        llm_exec = _mock_llm_executor(output='{"category": "billing"}')

        pr_service = FakeProcessRunService(created_id="run-proc-99")
        executor = ProcessExecutor(
            _make_appspec([process]),
            llm_executor=llm_exec,
            process_run_service=pr_service,
        )

        result = await executor.execute(
            "classify_flow",
            trigger_data={"entity": {"title": "Billing issue"}},
            user_id="user-5",
        )

        assert result.success
        calls = llm_exec._captured_calls
        assert len(calls) == 1, "Expected exactly one LLM execute call"
        call = calls[0]
        assert call["subject_type"] == "ProcessRun", (
            f"Expected subject_type='ProcessRun', got {call['subject_type']!r}"
        )
        assert call["subject_id"] == "run-proc-99", (
            f"Expected subject_id='run-proc-99', got {call['subject_id']!r}"
        )

    @pytest.mark.asyncio
    async def test_llm_step_without_process_run_service_raises(self):
        """If no process_run_service is available and an llm step is reached, it should fail.

        This is a wiring bug — there is no run_id to pass as subject, so we fail-loud.
        """
        step = _make_step(
            "classify",
            kind=StepKind.LLM_INTENT,
            llm_intent="classify_ticket",
        )
        process = _make_process("flow", [step])
        llm_exec = _mock_llm_executor()

        executor = ProcessExecutor(
            _make_appspec([process]),
            llm_executor=llm_exec,
        )

        result = await executor.execute("flow", user_id="u-nomatch")
        # Should fail loudly — no run_id = wiring bug
        assert not result.success
        assert "run_id" in result.error.lower() or "ProcessRun" in (result.error or ""), (
            f"Expected fail-loud error about run_id/ProcessRun, got: {result.error!r}"
        )
