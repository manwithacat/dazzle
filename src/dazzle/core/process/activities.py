"""
Shared Temporal activities for DAZZLE process execution.

These activities are used by dynamically generated workflows to:
- Create and manage human tasks
- Emit HLESS events
- Execute service calls
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from .adapter import ProcessTask, TaskStatus

logger = logging.getLogger(__name__)

# Activity registry for dynamic loading
_activity_registry: list[Any] = []

# In-memory task store (for development - production uses database)
_task_store: dict[str, ProcessTask] = {}


def get_all_activities() -> list[Any]:
    """Get all registered activities."""
    return list(_activity_registry)


# Check if temporalio is available
try:
    from temporalio import activity

    _TEMPORAL_AVAILABLE = True
except ImportError:
    _TEMPORAL_AVAILABLE = False

    # Create dummy decorator for when Temporal isn't installed
    class _DummyActivity:
        @staticmethod
        def defn(fn: Any = None, name: str | None = None) -> Any:
            def decorator(func: Any) -> Any:
                return func

            return decorator if fn is None else decorator(fn)

    activity = _DummyActivity()


if _TEMPORAL_AVAILABLE:

    @activity.defn(name="create_human_task")  # type: ignore[misc]
    async def create_human_task(params: dict[str, Any]) -> str:
        """
        Create a ProcessTask record for a human task step.

        Args:
            params: Task parameters including:
                - workflow_id: Parent workflow ID
                - step_name: Step that created the task
                - surface: Surface to render
                - entity_name: Entity type
                - entity_id: Entity instance ID
                - assignee_id: Assigned user (optional)
                - assignee_role: Required role (optional)
                - due_seconds: Seconds until due
                - outcomes: Available outcome buttons

        Returns:
            task_id: Unique task identifier
        """
        task_id = str(uuid4())

        due_seconds = params.get("due_seconds", 86400)  # Default 24 hours
        due_at = datetime.utcnow() + timedelta(seconds=due_seconds)

        task = ProcessTask(
            task_id=task_id,
            run_id=params["workflow_id"],
            step_name=params["step_name"],
            surface_name=params.get("surface", ""),
            entity_name=params.get("entity_name", ""),
            entity_id=params.get("entity_id", ""),
            assignee_id=params.get("assignee_id"),
            assignee_role=params.get("assignee_role"),
            status=TaskStatus.PENDING,
            due_at=due_at,
        )

        # Store task (in production, this would be database insert)
        _task_store[task_id] = task

        activity.logger.info(f"Created human task {task_id} for step '{params['step_name']}'")

        return task_id

    @activity.defn(name="escalate_human_task")  # type: ignore[misc]
    async def escalate_human_task(params: dict[str, Any]) -> None:
        """
        Escalate an overdue human task.

        Args:
            params: Task parameters including:
                - task_id: Task to escalate
                - step_name: Step name for logging
        """
        task_id = params["task_id"]
        step_name = params.get("step_name", "unknown")

        if task_id in _task_store:
            task = _task_store[task_id]
            task.status = TaskStatus.ESCALATED
            task.escalated_at = datetime.utcnow()

            activity.logger.warning(f"Escalated human task {task_id} (step: {step_name})")
        else:
            activity.logger.error(f"Task {task_id} not found for escalation")

    @activity.defn(name="emit_hless_event")  # type: ignore[misc]
    async def emit_hless_event(event: dict[str, Any]) -> None:
        """
        Emit an HLESS (Human-Loop Event Sourcing) event.

        Args:
            event: Event data including:
                - event_type: Type of event (process.step.completed, etc)
                - payload: Event payload
        """
        event_type = event.get("event_type", "process.event.v1")

        activity.logger.info(
            f"Emitting HLESS event: {event_type}, payload keys: {list(event.get('payload', {}).keys())}"
        )

        # TODO: Integrate with event bus / message queue
        # await event_bus.publish(event_type, event["payload"])

    @activity.defn(name="execute_service")  # type: ignore[misc]
    async def execute_service(params: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a service from the service registry.

        Args:
            params: Service parameters including:
                - service_name: Name of the service to call
                - method: Service method to invoke
                - inputs: Input arguments

        Returns:
            Service execution result
        """
        service_name = params.get("service_name", "unknown")
        method = params.get("method", "execute")
        inputs = params.get("inputs", {})

        activity.logger.info(
            f"Executing service '{service_name}.{method}' with inputs: {list(inputs.keys())}"
        )

        # TODO: Integrate with service registry
        # service = get_service(service_name)
        # return await getattr(service, method)(**inputs)

        return {
            "status": "executed",
            "service": service_name,
            "method": method,
        }

    # Register activities
    _activity_registry.extend(
        [
            create_human_task,
            escalate_human_task,
            emit_hless_event,
            execute_service,
        ]
    )


# Database operations for tasks (used by adapter)
async def get_task_from_db(task_id: str) -> ProcessTask | None:
    """
    Get a task from the database.

    In development mode, uses in-memory store.
    Production would use actual database.
    """
    return _task_store.get(task_id)


async def list_tasks_from_db(
    run_id: str | None = None,
    assignee_id: str | None = None,
    status: TaskStatus | None = None,
    limit: int = 100,
) -> list[ProcessTask]:
    """
    List tasks from the database with filters.
    """
    tasks = list(_task_store.values())

    # Apply filters
    if run_id:
        tasks = [t for t in tasks if t.run_id == run_id]
    if assignee_id:
        tasks = [t for t in tasks if t.assignee_id == assignee_id]
    if status:
        tasks = [t for t in tasks if t.status == status]

    return tasks[:limit]


async def complete_task_in_db(
    task_id: str,
    outcome: str,
    outcome_data: dict[str, Any] | None = None,
    completed_by: str | None = None,
) -> None:
    """
    Mark a task as completed in the database.
    """
    if task_id in _task_store:
        task = _task_store[task_id]
        task.status = TaskStatus.COMPLETED
        task.outcome = outcome
        task.outcome_data = outcome_data
        task.completed_at = datetime.utcnow()

        logger.info(f"Task {task_id} completed with outcome '{outcome}'")


async def reassign_task_in_db(
    task_id: str,
    new_assignee_id: str,
    reason: str | None = None,
) -> None:
    """
    Reassign a task to a new user.
    """
    if task_id in _task_store:
        task = _task_store[task_id]
        old_assignee = task.assignee_id
        task.assignee_id = new_assignee_id

        logger.info(
            f"Task {task_id} reassigned from {old_assignee} to {new_assignee_id}"
            + (f": {reason}" if reason else "")
        )


# Clear task store (for testing)
def clear_task_store() -> None:
    """Clear the in-memory task store (for testing)."""
    _task_store.clear()
