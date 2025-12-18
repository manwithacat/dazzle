"""
TaskContext for human task rendering in surfaces.

When a surface is rendered as part of a human task, TaskContext
provides task-specific information like outcomes, due dates, and
assignee details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class TaskOutcome:
    """An outcome button to render in the task UI."""

    name: str  # e.g., "approve"
    label: str  # e.g., "Approve Expense"
    style: str = "primary"  # "primary", "danger", "secondary", "warning"
    confirm: str | None = None  # Confirmation prompt before action
    sets: list[dict[str, Any]] = field(default_factory=list)  # Field assignments
    goto: str = "complete"  # Next step or "complete"/"fail"


@dataclass
class TaskContext:
    """
    Context injected into surfaces when rendered as a human task.

    This enables surfaces to display task-specific controls:
    - Outcome buttons (approve/reject/etc)
    - Due date and time remaining
    - Assignment information
    - Process context
    """

    task_id: str
    process_name: str
    process_run_id: str
    step_name: str
    surface_name: str
    entity_name: str
    entity_id: str
    due_at: datetime
    outcomes: list[TaskOutcome]
    assignee_id: str | None = None
    assignee_role: str | None = None
    created_at: datetime | None = None
    escalated_at: datetime | None = None

    @property
    def is_overdue(self) -> bool:
        """Check if task is past due date."""
        now = datetime.now(UTC)
        due = self.due_at
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        return now > due

    @property
    def is_escalated(self) -> bool:
        """Check if task has been escalated."""
        return self.escalated_at is not None

    @property
    def time_remaining(self) -> str:
        """Human-readable time remaining until due."""
        now = datetime.now(UTC)
        due = self.due_at
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)

        delta = due - now

        if delta.total_seconds() < 0:
            return "Overdue"

        if delta.days > 0:
            return f"{delta.days} day{'s' if delta.days != 1 else ''}"
        elif delta.seconds >= 3600:
            hours = delta.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''}"
        elif delta.seconds >= 60:
            minutes = delta.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            return "Less than a minute"

    @property
    def urgency(self) -> str:
        """Get urgency level based on time remaining."""
        now = datetime.now(UTC)
        due = self.due_at
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)

        delta = due - now

        if delta.total_seconds() < 0:
            return "critical"  # Overdue
        elif delta.days < 1:
            return "high"  # Due within 24 hours
        elif delta.days < 3:
            return "medium"  # Due within 3 days
        else:
            return "low"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for template rendering."""
        return {
            "task_id": self.task_id,
            "process_name": self.process_name,
            "process_run_id": self.process_run_id,
            "step_name": self.step_name,
            "surface_name": self.surface_name,
            "entity_name": self.entity_name,
            "entity_id": self.entity_id,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "escalated_at": self.escalated_at.isoformat() if self.escalated_at else None,
            "assignee_id": self.assignee_id,
            "assignee_role": self.assignee_role,
            "is_overdue": self.is_overdue,
            "is_escalated": self.is_escalated,
            "time_remaining": self.time_remaining,
            "urgency": self.urgency,
            "outcomes": [
                {
                    "name": o.name,
                    "label": o.label,
                    "style": o.style,
                    "confirm": o.confirm,
                }
                for o in self.outcomes
            ],
        }

    def to_json(self) -> str:
        """Convert to JSON string for frontend."""
        import json

        return json.dumps(self.to_dict())


def create_task_context_from_task(
    task: Any,
    outcomes: list[TaskOutcome] | None = None,
) -> TaskContext:
    """
    Create TaskContext from a ProcessTask instance.

    Args:
        task: ProcessTask instance from the adapter
        outcomes: List of TaskOutcome from the process step spec

    Returns:
        TaskContext for surface rendering
    """
    return TaskContext(
        task_id=task.task_id,
        process_name=getattr(task, "process_name", ""),
        process_run_id=task.run_id,
        step_name=task.step_name,
        surface_name=task.surface_name,
        entity_name=task.entity_name,
        entity_id=task.entity_id,
        due_at=task.due_at,
        outcomes=outcomes or [],
        assignee_id=task.assignee_id,
        assignee_role=task.assignee_role,
        created_at=task.created_at,
        escalated_at=task.escalated_at,
    )
