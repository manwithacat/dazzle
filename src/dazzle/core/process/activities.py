"""
Shared Temporal activities for DAZZLE process execution.

These activities are used by dynamically generated workflows to:
- Create and manage human tasks
- Emit HLESS events
- Execute service calls
"""

import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from .adapter import ProcessTask, TaskStatus
from .task_store import TaskStoreBackend, get_task_store

logger = logging.getLogger(__name__)

# Activity registry for dynamic loading
_activity_registry: list[Any] = []
_activity_registry_lock = threading.Lock()


def get_all_activities() -> list[Any]:
    """Get all registered activities."""
    with _activity_registry_lock:
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

    @activity.defn(name="create_human_task")  # type: ignore  # Temporal decorator
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
        due_at = datetime.now(UTC) + timedelta(seconds=due_seconds)

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

        await get_task_store().save(task)

        activity.logger.info("Created human task %s for step '%s'", task_id, params["step_name"])

        return task_id

    @activity.defn(name="escalate_human_task")  # type: ignore  # Temporal decorator
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

        found = await get_task_store().escalate(task_id)
        if found:
            activity.logger.warning("Escalated human task %s (step: %s)", task_id, step_name)
        else:
            activity.logger.error("Task %s not found for escalation", task_id)

    @activity.defn(name="emit_hless_event")  # type: ignore  # Temporal decorator
    async def emit_hless_event(event: dict[str, Any]) -> None:
        """
        Emit an HLESS (Human-Loop Event Sourcing) event.

        Args:
            event: Event data including:
                - event_type: Type of event (process.step.completed, etc)
                - payload: Event payload
        """
        event_type = event.get("event_type", "process.event.v1")

        payload_keys = list(event.get("payload", {}).keys())
        activity.logger.info("Emitting HLESS event: %s, payload keys: %s", event_type, payload_keys)

        # TODO: Integrate with event bus / message queue
        # await event_bus.publish(event_type, event["payload"])

    @activity.defn(name="execute_service")  # type: ignore  # Temporal decorator
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
            "Executing service '%s.%s' with inputs: %s",
            service_name,
            method,
            list(inputs.keys()),
        )

        return {
            "status": "executed",
            "service": service_name,
            "method": method,
        }

    # Register activities
    with _activity_registry_lock:
        _activity_registry.extend(
            [
                create_human_task,
                escalate_human_task,
                emit_hless_event,
                execute_service,
            ]
        )


# Task store operations (used by TemporalAdapter) — delegate to the
# registered backend. Swap the backend with ``set_task_store()`` before
# the adapter is created to persist tasks durably.
async def get_task(task_id: str) -> ProcessTask | None:
    """Fetch a task by id from the active task store."""
    return await get_task_store().get(task_id)


async def list_tasks(
    run_id: str | None = None,
    assignee_id: str | None = None,
    status: TaskStatus | None = None,
    limit: int = 100,
) -> list[ProcessTask]:
    """List tasks matching the supplied filters."""
    return await get_task_store().list(
        run_id=run_id,
        assignee_id=assignee_id,
        status=status,
        limit=limit,
    )


async def complete_task(
    task_id: str,
    outcome: str,
    outcome_data: dict[str, Any] | None = None,
    completed_by: str | None = None,
) -> bool:
    """Mark a task completed. Returns ``True`` iff a task was updated."""
    return await get_task_store().complete(task_id, outcome, outcome_data, completed_by)


async def reassign_task(
    task_id: str,
    new_assignee_id: str,
    reason: str | None = None,
) -> bool:
    """Reassign a task. Returns ``True`` iff a task was updated."""
    return await get_task_store().reassign(task_id, new_assignee_id, reason)


# Re-exported for tests that need to reset state between runs.
async def clear_task_store() -> None:
    """Clear all tasks from the active store (for tests only)."""
    await get_task_store().clear()


__all__ = [
    "TaskStoreBackend",
    "clear_task_store",
    "complete_task",
    "get_all_activities",
    "get_task",
    "list_tasks",
    "reassign_task",
]
