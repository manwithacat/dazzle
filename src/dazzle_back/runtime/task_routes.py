"""
Task API routes for human task management.

These routes provide:
- Task listing (my tasks, all tasks)
- Task details (with outcome options)
- Task completion
- Task reassignment
"""

import logging
from datetime import UTC
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from dazzle.core.process.adapter import ProcessTask, TaskStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# Request/Response Models
class ProcessStepContext(BaseModel):
    """Process context for a task — where it sits in the workflow."""

    process_name: str
    step_index: int = 0
    total_steps: int = 0
    previous_step: str | None = None
    next_step: str | None = None
    next_step_kind: str | None = None


class TaskSummary(BaseModel):
    """Summary of a task for listing."""

    task_id: str
    run_id: str
    process_name: str | None = None
    step_name: str
    surface_name: str
    entity_name: str
    entity_id: str
    assignee_id: str | None
    assignee_role: str | None
    status: str
    due_at: str
    is_overdue: bool = False
    created_at: str
    process_context: ProcessStepContext | None = None


class TaskOutcomeResponse(BaseModel):
    """An available outcome for a task."""

    name: str
    label: str
    style: str = "primary"
    confirm: str | None = None


class TaskDetailResponse(BaseModel):
    """Full task details including outcomes."""

    task_id: str
    run_id: str
    process_name: str | None = None
    step_name: str
    surface_name: str
    entity_name: str
    entity_id: str
    assignee_id: str | None
    assignee_role: str | None
    status: str
    outcome: str | None
    due_at: str
    escalated_at: str | None
    completed_at: str | None
    created_at: str
    outcomes: list[TaskOutcomeResponse] = Field(default_factory=list)
    process_context: ProcessStepContext | None = None


class CompleteTaskRequest(BaseModel):
    """Request to complete a task."""

    outcome: str = Field(..., description="Selected outcome name")
    outcome_data: dict[str, Any] | None = Field(default=None, description="Additional outcome data")


class CompleteTaskResponse(BaseModel):
    """Response after completing a task."""

    success: bool
    message: str = "Task completed"


class ReassignTaskRequest(BaseModel):
    """Request to reassign a task."""

    new_assignee_id: str
    reason: str | None = None


class TaskListResponse(BaseModel):
    """Response for task listing."""

    tasks: list[TaskSummary]
    total: int


# Dependency placeholder - will be injected by server
_process_manager = None


def set_process_manager(manager: Any) -> None:
    """Set the process manager dependency."""
    global _process_manager
    _process_manager = manager


def get_process_manager() -> Any:
    """Get the process manager."""
    if _process_manager is None:
        raise HTTPException(503, "Process manager not initialized")
    return _process_manager


def _build_process_context(
    process_name: str,
    step_name: str,
    manager: Any,
) -> ProcessStepContext | None:
    """Build process step context showing where a task sits in the workflow."""
    process_spec = manager.get_process_spec(process_name)
    if not process_spec or not process_spec.steps:
        return None

    steps = process_spec.steps
    total = len(steps)
    step_index = 0
    prev_step = None
    next_step = None
    next_kind = None

    for i, s in enumerate(steps):
        if s.name == step_name:
            step_index = i
            if i > 0:
                prev_step = steps[i - 1].name
            # Use on_success if defined, otherwise next sequential step
            if s.on_success:
                next_step = s.on_success
                target = process_spec.get_step(s.on_success)
                if target:
                    next_kind = (
                        target.kind.value if hasattr(target.kind, "value") else str(target.kind)
                    )
            elif i + 1 < total:
                next_step = steps[i + 1].name
                next_kind = (
                    steps[i + 1].kind.value
                    if hasattr(steps[i + 1].kind, "value")
                    else str(steps[i + 1].kind)
                )
            break

    return ProcessStepContext(
        process_name=process_name,
        step_index=step_index,
        total_steps=total,
        previous_step=prev_step,
        next_step=next_step,
        next_step_kind=next_kind,
    )


def _task_to_summary(
    task: ProcessTask,
    process_name: str | None = None,
    process_context: ProcessStepContext | None = None,
) -> TaskSummary:
    """Convert ProcessTask to TaskSummary."""
    from datetime import datetime

    due_at = task.due_at
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=UTC)
    now = datetime.now(UTC)

    return TaskSummary(
        task_id=task.task_id,
        run_id=task.run_id,
        process_name=process_name,
        step_name=task.step_name,
        surface_name=task.surface_name,
        entity_name=task.entity_name,
        entity_id=task.entity_id,
        assignee_id=task.assignee_id,
        assignee_role=task.assignee_role,
        status=task.status.value,
        due_at=task.due_at.isoformat(),
        is_overdue=now > due_at,
        created_at=task.created_at.isoformat(),
        process_context=process_context,
    )


def _task_to_detail(
    task: ProcessTask,
    process_name: str | None = None,
    outcomes: list[TaskOutcomeResponse] | None = None,
    process_context: ProcessStepContext | None = None,
) -> TaskDetailResponse:
    """Convert ProcessTask to TaskDetailResponse."""
    return TaskDetailResponse(
        task_id=task.task_id,
        run_id=task.run_id,
        process_name=process_name,
        step_name=task.step_name,
        surface_name=task.surface_name,
        entity_name=task.entity_name,
        entity_id=task.entity_id,
        assignee_id=task.assignee_id,
        assignee_role=task.assignee_role,
        status=task.status.value,
        outcome=task.outcome,
        due_at=task.due_at.isoformat(),
        escalated_at=task.escalated_at.isoformat() if task.escalated_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        created_at=task.created_at.isoformat(),
        outcomes=outcomes or [],
        process_context=process_context,
    )


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    assignee_id: str | None = Query(None, description="Filter by assignee"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
) -> TaskListResponse:
    """
    List tasks with optional filters.

    - **assignee_id**: Filter tasks by assignee
    - **status**: Filter by task status (pending, completed, escalated, etc.)
    - **limit**: Maximum number of tasks to return
    """
    manager = get_process_manager()

    # Parse status if provided
    task_status = None
    if status:
        try:
            task_status = TaskStatus(status)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")

    tasks = await manager.list_tasks(
        assignee_id=assignee_id,
        status=task_status,
        limit=limit,
    )

    # Get process names and context for each task
    summaries = []
    for task in tasks:
        run = await manager.get_run(task.run_id)
        process_name = run.process_name if run else None
        ctx = (
            _build_process_context(process_name, task.step_name, manager) if process_name else None
        )
        summaries.append(_task_to_summary(task, process_name, ctx))

    return TaskListResponse(tasks=summaries, total=len(summaries))


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(task_id: str) -> TaskDetailResponse:
    """
    Get detailed task information including available outcomes.

    Returns task details with the surface to render and outcome buttons
    to display.
    """
    manager = get_process_manager()

    task = await manager.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    # Get process run for process name
    run = await manager.get_run(task.run_id)
    process_name = run.process_name if run else None

    # Get outcomes from process spec
    outcomes: list[TaskOutcomeResponse] = []
    if process_name:
        process_spec = manager.get_process_spec(process_name)
        if process_spec:
            step = process_spec.get_step(task.step_name)
            if step and step.human_task:
                for outcome in step.human_task.outcomes:
                    outcomes.append(
                        TaskOutcomeResponse(
                            name=outcome.name,
                            label=outcome.label,
                            style=outcome.style,
                            confirm=outcome.confirm,
                        )
                    )

    # Build process step context
    ctx = _build_process_context(process_name, task.step_name, manager) if process_name else None

    return _task_to_detail(task, process_name, outcomes, ctx)


@router.post("/{task_id}/complete", response_model=CompleteTaskResponse)
async def complete_task(
    task_id: str,
    body: CompleteTaskRequest,
) -> CompleteTaskResponse:
    """
    Complete a task with the selected outcome.

    The outcome must be one of the valid outcomes defined in the
    process step's human_task configuration.
    """
    manager = get_process_manager()

    task = await manager.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status != TaskStatus.PENDING:
        raise HTTPException(400, f"Task already {task.status.value}")

    # Validate outcome
    run = await manager.get_run(task.run_id)
    if run:
        process_spec = manager.get_process_spec(run.process_name)
        if process_spec:
            step = process_spec.get_step(task.step_name)
            if step and step.human_task:
                valid_outcomes = {o.name for o in step.human_task.outcomes}
                if body.outcome not in valid_outcomes:
                    raise HTTPException(
                        400,
                        f"Invalid outcome '{body.outcome}'. "
                        f"Valid outcomes: {', '.join(valid_outcomes)}",
                    )

    # Complete the task
    await manager.complete_task(
        task_id=task_id,
        outcome=body.outcome,
        outcome_data=body.outcome_data,
    )

    logger.info(f"Task {task_id} completed with outcome: {body.outcome}")

    return CompleteTaskResponse(
        success=True,
        message=f"Task completed with outcome: {body.outcome}",
    )


@router.post("/{task_id}/reassign", response_model=CompleteTaskResponse)
async def reassign_task(
    task_id: str,
    body: ReassignTaskRequest,
) -> CompleteTaskResponse:
    """
    Reassign a task to a different user.

    Only pending or escalated tasks can be reassigned.
    """
    manager = get_process_manager()

    task = await manager.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status not in (TaskStatus.PENDING, TaskStatus.ESCALATED):
        raise HTTPException(400, f"Cannot reassign task with status: {task.status.value}")

    await manager.reassign_task(
        task_id=task_id,
        new_assignee_id=body.new_assignee_id,
        reason=body.reason,
    )

    logger.info(f"Task {task_id} reassigned to {body.new_assignee_id}")

    return CompleteTaskResponse(
        success=True,
        message=f"Task reassigned to {body.new_assignee_id}",
    )


@router.get("/{task_id}/surface-url")
async def get_task_surface_url(task_id: str) -> dict[str, str]:
    """
    Get the URL to render the task's surface.

    Returns a URL that includes the task_id query parameter
    for TaskContext injection.
    """
    manager = get_process_manager()

    task = await manager.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    # Build surface URL with task context
    url = f"/surfaces/{task.surface_name}/{task.entity_id}?task_id={task_id}"

    return {"url": url, "surface_name": task.surface_name, "entity_id": task.entity_id}
