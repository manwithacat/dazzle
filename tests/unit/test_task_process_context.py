"""Tests for process-aware task inbox enrichment.

Covers:
- _build_process_context() building step context from ProcessSpec
- _task_to_summary() and _task_to_detail() passing process_context
- list_tasks and get_task endpoints including process_context in responses
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.core.ir.process import ProcessSpec, ProcessStepSpec, StepKind
from dazzle.core.process.adapter import ProcessTask, TaskStatus
from dazzle_back.runtime.task_routes import (
    ProcessStepContext,
    _build_process_context,
    _task_to_detail,
    _task_to_summary,
)


def _make_process_spec(
    name: str = "order_flow",
    steps: list[tuple[str, str]] | None = None,
    on_success_map: dict[str, str] | None = None,
) -> ProcessSpec:
    """Create a ProcessSpec with named steps.

    steps: list of (name, kind) tuples
    on_success_map: dict of step_name -> on_success step name
    """
    if steps is None:
        steps = [
            ("validate", "service"),
            ("review", "human_task"),
            ("approve", "human_task"),
            ("fulfill", "service"),
        ]
    on_success_map = on_success_map or {}
    step_specs = []
    for step_name, kind in steps:
        step_specs.append(
            ProcessStepSpec(
                name=step_name,
                kind=StepKind(kind),
                on_success=on_success_map.get(step_name),
            )
        )
    return ProcessSpec(name=name, steps=step_specs)


def _make_task(
    task_id: str = "t1",
    run_id: str = "r1",
    step_name: str = "review",
) -> ProcessTask:
    now = datetime.now(UTC)
    return ProcessTask(
        task_id=task_id,
        run_id=run_id,
        step_name=step_name,
        surface_name="order_review",
        entity_name="Order",
        entity_id="e1",
        assignee_id="user1",
        assignee_role="reviewer",
        status=TaskStatus.PENDING,
        due_at=now,
        created_at=now,
    )


# ---------------------------------------------------------------------------
# _build_process_context
# ---------------------------------------------------------------------------


class TestBuildProcessContext:
    """_build_process_context extracts step position from ProcessSpec."""

    def test_middle_step_has_prev_and_next(self) -> None:
        spec = _make_process_spec()
        manager = MagicMock()
        manager.get_process_spec.return_value = spec

        ctx = _build_process_context("order_flow", "review", manager)
        assert ctx is not None
        assert ctx.process_name == "order_flow"
        assert ctx.step_index == 1
        assert ctx.total_steps == 4
        assert ctx.previous_step == "validate"
        assert ctx.next_step == "approve"
        assert ctx.next_step_kind == "human_task"

    def test_first_step_has_no_prev(self) -> None:
        spec = _make_process_spec()
        manager = MagicMock()
        manager.get_process_spec.return_value = spec

        ctx = _build_process_context("order_flow", "validate", manager)
        assert ctx is not None
        assert ctx.step_index == 0
        assert ctx.previous_step is None
        assert ctx.next_step == "review"

    def test_last_step_has_no_next(self) -> None:
        spec = _make_process_spec()
        manager = MagicMock()
        manager.get_process_spec.return_value = spec

        ctx = _build_process_context("order_flow", "fulfill", manager)
        assert ctx is not None
        assert ctx.step_index == 3
        assert ctx.next_step is None
        assert ctx.next_step_kind is None
        assert ctx.previous_step == "approve"

    def test_on_success_overrides_sequential_next(self) -> None:
        spec = _make_process_spec(
            on_success_map={"review": "fulfill"},
        )
        manager = MagicMock()
        manager.get_process_spec.return_value = spec

        ctx = _build_process_context("order_flow", "review", manager)
        assert ctx is not None
        # Should use on_success target, skipping "approve"
        assert ctx.next_step == "fulfill"
        assert ctx.next_step_kind == "service"

    def test_no_process_spec_returns_none(self) -> None:
        manager = MagicMock()
        manager.get_process_spec.return_value = None

        ctx = _build_process_context("missing", "step1", manager)
        assert ctx is None

    def test_empty_steps_returns_none(self) -> None:
        spec = _make_process_spec(steps=[])
        manager = MagicMock()
        manager.get_process_spec.return_value = spec

        ctx = _build_process_context("order_flow", "step1", manager)
        assert ctx is None

    def test_single_step_process(self) -> None:
        spec = _make_process_spec(steps=[("only_step", "human_task")])
        manager = MagicMock()
        manager.get_process_spec.return_value = spec

        ctx = _build_process_context("order_flow", "only_step", manager)
        assert ctx is not None
        assert ctx.step_index == 0
        assert ctx.total_steps == 1
        assert ctx.previous_step is None
        assert ctx.next_step is None


# ---------------------------------------------------------------------------
# Converters pass process_context through
# ---------------------------------------------------------------------------


class TestConverterProcessContext:
    """_task_to_summary and _task_to_detail pass process_context."""

    def test_summary_includes_context(self) -> None:
        task = _make_task()
        ctx = ProcessStepContext(
            process_name="order_flow",
            step_index=1,
            total_steps=3,
            previous_step="validate",
            next_step="fulfill",
            next_step_kind="service",
        )
        summary = _task_to_summary(task, "order_flow", ctx)
        assert summary.process_context is not None
        assert summary.process_context.step_index == 1
        assert summary.process_context.next_step == "fulfill"

    def test_summary_without_context(self) -> None:
        task = _make_task()
        summary = _task_to_summary(task, "order_flow")
        assert summary.process_context is None

    def test_detail_includes_context(self) -> None:
        task = _make_task()
        ctx = ProcessStepContext(
            process_name="order_flow",
            step_index=1,
            total_steps=3,
        )
        detail = _task_to_detail(task, "order_flow", process_context=ctx)
        assert detail.process_context is not None
        assert detail.process_context.step_index == 1

    def test_detail_without_context(self) -> None:
        task = _make_task()
        detail = _task_to_detail(task, "order_flow")
        assert detail.process_context is None


# ---------------------------------------------------------------------------
# Endpoints wire process_context
# ---------------------------------------------------------------------------


class TestEndpointProcessContext:
    """list_tasks and get_task endpoints include process_context."""

    @pytest.fixture()
    def _setup_manager(self) -> tuple[MagicMock, ProcessTask]:
        from dazzle_back.runtime import task_routes

        task = _make_task()
        spec = _make_process_spec()

        manager = MagicMock()
        manager.list_tasks = AsyncMock(return_value=[task])
        manager.get_task = AsyncMock(return_value=task)

        run = MagicMock()
        run.process_name = "order_flow"
        manager.get_run = AsyncMock(return_value=run)
        manager.get_process_spec.return_value = spec

        task_routes._process_manager = manager
        yield manager, task
        task_routes._process_manager = None

    @pytest.mark.asyncio
    async def test_list_tasks_includes_context(self, _setup_manager: tuple) -> None:
        from dazzle_back.runtime.task_routes import list_tasks

        result = await list_tasks(assignee_id=None, status=None, limit=100)
        assert result.total == 1
        ctx = result.tasks[0].process_context
        assert ctx is not None
        assert ctx.process_name == "order_flow"
        assert ctx.step_index == 1
        assert ctx.previous_step == "validate"
        assert ctx.next_step == "approve"

    @pytest.mark.asyncio
    async def test_get_task_includes_context(self, _setup_manager: tuple) -> None:
        from dazzle_back.runtime.task_routes import get_task

        result = await get_task("t1")
        ctx = result.process_context
        assert ctx is not None
        assert ctx.process_name == "order_flow"
        assert ctx.step_index == 1

    @pytest.mark.asyncio
    async def test_list_tasks_no_run_no_context(self) -> None:
        from dazzle_back.runtime import task_routes

        task = _make_task()
        manager = MagicMock()
        manager.list_tasks = AsyncMock(return_value=[task])
        manager.get_run = AsyncMock(return_value=None)

        task_routes._process_manager = manager
        try:
            from dazzle_back.runtime.task_routes import list_tasks

            result = await list_tasks(assignee_id=None, status=None, limit=100)
            assert result.tasks[0].process_context is None
        finally:
            task_routes._process_manager = None
