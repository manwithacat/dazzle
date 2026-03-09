"""Tests for linear checkpointed process executor."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.process import ProcessSpec, ProcessStepSpec, StepKind
from dazzle_back.runtime.process_executor import (
    ProcessContext,
    ProcessExecutor,
    StepResult,
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


def _mock_llm_executor(output='{"category": "billing"}', success=True, error=None):
    executor = MagicMock()

    async def mock_execute(intent_name, input_data, **kwargs):
        result = MagicMock()
        result.success = success
        result.output = output
        result.error = error
        return result

    executor.execute = mock_execute
    return executor


# ---------------------------------------------------------------------------
# ProcessContext
# ---------------------------------------------------------------------------


class TestProcessContext:
    def test_checkpoint_and_check(self):
        ctx = ProcessContext()
        assert not ctx.is_checkpointed("step1")
        ctx.checkpoint("step1", StepResult(success=True, output="hello"))
        assert ctx.is_checkpointed("step1")
        assert ctx.step_outputs["step1"] == "hello"

    def test_resolve_trigger_data(self):
        ctx = ProcessContext(trigger_data={"entity": {"title": "Bug", "id": "123"}})
        assert ctx.resolve_value("trigger.entity.title") == "Bug"
        assert ctx.resolve_value("trigger.entity.id") == "123"

    def test_resolve_step_output(self):
        ctx = ProcessContext()
        ctx.step_outputs["classify"] = {"category": "billing"}
        assert ctx.resolve_value("classify.output.category") == "billing"

    def test_resolve_literal(self):
        ctx = ProcessContext()
        assert ctx.resolve_value("some_literal") == "some_literal"

    def test_resolve_missing_trigger_field(self):
        ctx = ProcessContext(trigger_data={"entity": {}})
        assert ctx.resolve_value("trigger.entity.missing") is None


# ---------------------------------------------------------------------------
# Process Execution
# ---------------------------------------------------------------------------


class TestProcessExecution:
    @pytest.mark.asyncio
    async def test_execute_unknown_process(self):
        executor = ProcessExecutor(_make_appspec([]))
        result = await executor.execute("nonexistent")
        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_llm_step(self):
        step = _make_step(
            "classify",
            kind=StepKind.LLM_INTENT,
            llm_intent="classify_ticket",
            llm_input_map={"title": "trigger.entity.title"},
        )
        process = _make_process("classify_flow", [step])
        llm_exec = _mock_llm_executor(output='{"category": "billing"}')

        executor = ProcessExecutor(
            _make_appspec([process]),
            llm_executor=llm_exec,
        )
        result = await executor.execute(
            "classify_flow",
            trigger_data={"entity": {"title": "Billing issue"}},
        )

        assert result.success
        assert result.steps_completed == 1
        assert result.outputs["classify"] == {"category": "billing"}

    @pytest.mark.asyncio
    async def test_llm_step_without_executor(self):
        step = _make_step(
            "classify",
            kind=StepKind.LLM_INTENT,
            llm_intent="classify_ticket",
        )
        process = _make_process("flow", [step])
        executor = ProcessExecutor(_make_appspec([process]))

        result = await executor.execute("flow")
        assert not result.success
        assert "No LLM executor" in result.error

    @pytest.mark.asyncio
    async def test_llm_step_failure_stops_process(self):
        step1 = _make_step(
            "classify",
            kind=StepKind.LLM_INTENT,
            llm_intent="classify_ticket",
        )
        step2 = _make_step(
            "notify",
            kind=StepKind.LLM_INTENT,
            llm_intent="send_notification",
        )
        process = _make_process("flow", [step1, step2])
        llm_exec = _mock_llm_executor(success=False, error="API error")

        executor = ProcessExecutor(
            _make_appspec([process]),
            llm_executor=llm_exec,
        )
        result = await executor.execute("flow")

        assert not result.success
        assert result.steps_completed == 1
        assert result.steps_total == 2

    @pytest.mark.asyncio
    async def test_condition_step(self):
        step = _make_step(
            "check_status",
            kind=StepKind.CONDITION,
            condition="trigger.entity.status == open",
        )
        process = _make_process("flow", [step])
        executor = ProcessExecutor(_make_appspec([process]))

        result = await executor.execute(
            "flow",
            trigger_data={"entity": {"status": "open"}},
        )
        assert result.success
        assert result.outputs["check_status"] is True

    @pytest.mark.asyncio
    async def test_condition_inequality(self):
        step = _make_step(
            "check",
            kind=StepKind.CONDITION,
            condition="trigger.entity.status != closed",
        )
        process = _make_process("flow", [step])
        executor = ProcessExecutor(_make_appspec([process]))

        result = await executor.execute(
            "flow",
            trigger_data={"entity": {"status": "open"}},
        )
        assert result.success
        assert result.outputs["check"] is True


# ---------------------------------------------------------------------------
# Checkpoint Resume
# ---------------------------------------------------------------------------


class TestCheckpointResume:
    @pytest.mark.asyncio
    async def test_skips_checkpointed_steps(self):
        step1 = _make_step(
            "classify",
            kind=StepKind.LLM_INTENT,
            llm_intent="classify_ticket",
        )
        step2 = _make_step(
            "enrich",
            kind=StepKind.LLM_INTENT,
            llm_intent="enrich_ticket",
        )
        process = _make_process("flow", [step1, step2])
        llm_exec = _mock_llm_executor(output='"enriched"')

        executor = ProcessExecutor(
            _make_appspec([process]),
            llm_executor=llm_exec,
        )

        # Resume with step1 already checkpointed
        result = await executor.execute(
            "flow",
            checkpoint_data={
                "checkpoints": ["classify"],
                "step_outputs": {"classify": {"category": "billing"}},
            },
        )

        assert result.success
        assert result.steps_completed == 2
        # step1 output preserved from checkpoint
        assert result.outputs["classify"] == {"category": "billing"}
        # step2 ran and produced output
        assert result.outputs["enrich"] == "enriched"

    @pytest.mark.asyncio
    async def test_get_checkpoint_data(self):
        ctx = ProcessContext()
        ctx.checkpoint("step1", StepResult(success=True, output="out1"))
        ctx.checkpoint("step2", StepResult(success=True, output="out2"))

        executor = ProcessExecutor(_make_appspec([]))
        data = executor.get_checkpoint_data(ctx)

        assert set(data["checkpoints"]) == {"step1", "step2"}
        assert data["step_outputs"]["step1"] == "out1"
        assert data["step_outputs"]["step2"] == "out2"


# ---------------------------------------------------------------------------
# Multi-step Flow
# ---------------------------------------------------------------------------


class TestMultiStepFlow:
    @pytest.mark.asyncio
    async def test_three_step_pipeline(self):
        steps = [
            _make_step(
                "classify",
                kind=StepKind.LLM_INTENT,
                llm_intent="classify",
                llm_input_map={"title": "trigger.entity.title"},
            ),
            _make_step(
                "check",
                kind=StepKind.CONDITION,
                condition="classify.output.category == billing",
            ),
            _make_step(
                "enrich",
                kind=StepKind.LLM_INTENT,
                llm_intent="enrich",
                llm_input_map={"category": "classify.output.category"},
            ),
        ]
        process = _make_process("pipeline", steps)

        call_count = 0

        async def mock_execute(intent_name, input_data, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.success = True
            if intent_name == "classify":
                result.output = '{"category": "billing"}'
            else:
                result.output = '{"enriched": true}'
            result.error = None
            return result

        llm_exec = MagicMock()
        llm_exec.execute = mock_execute

        executor = ProcessExecutor(
            _make_appspec([process]),
            llm_executor=llm_exec,
        )
        result = await executor.execute(
            "pipeline",
            trigger_data={"entity": {"title": "Billing issue"}},
        )

        assert result.success
        assert result.steps_completed == 3
        assert call_count == 2  # classify + enrich, condition doesn't call LLM
        assert result.outputs["classify"] == {"category": "billing"}
        assert result.outputs["check"] is True
        assert result.outputs["enrich"] == {"enriched": True}

    @pytest.mark.asyncio
    async def test_unsupported_step_kind_fails(self):
        step = _make_step("wait_step", kind=StepKind.WAIT)
        process = _make_process("flow", [step])
        executor = ProcessExecutor(_make_appspec([process]))

        result = await executor.execute("flow")
        assert not result.success
        assert "Unsupported step kind" in result.error
