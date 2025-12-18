"""
Process adapter interface for workflow execution backends.

This module defines the abstract interface that all process execution
backends must implement, allowing swappable runtime implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dazzle.core.ir.process import ProcessSpec, ScheduleSpec


class ProcessStatus(str, Enum):
    """Status of a process run."""

    PENDING = "pending"  # Created but not started
    RUNNING = "running"  # Currently executing
    DRAINING = "draining"  # Finishing current step, then stopping
    SUSPENDED = "suspended"  # Paused (e.g., during shutdown)
    WAITING = "waiting"  # Waiting for signal/human task
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Failed with error
    COMPENSATING = "compensating"  # Running compensation handlers
    CANCELLED = "cancelled"  # Manually cancelled


class TaskStatus(str, Enum):
    """Status of a human task."""

    PENDING = "pending"  # Awaiting assignment
    ASSIGNED = "assigned"  # Assigned to user
    IN_PROGRESS = "in_progress"  # User working on it
    COMPLETED = "completed"  # Successfully completed
    ESCALATED = "escalated"  # Escalated to supervisor
    EXPIRED = "expired"  # Timed out
    CANCELLED = "cancelled"  # Manually cancelled


class ProcessRun(BaseModel):
    """A single execution instance of a process."""

    run_id: str = Field(..., description="Unique run identifier")
    process_name: str = Field(..., description="Name of the process definition")
    process_version: str = Field(default="v1", description="Process version")
    dsl_version: str = Field(default="0.1", description="DSL version used")
    status: ProcessStatus = Field(default=ProcessStatus.PENDING)
    current_step: str | None = Field(default=None, description="Currently executing step")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Process inputs")
    context: dict[str, Any] = Field(default_factory=dict, description="Accumulated step outputs")
    outputs: dict[str, Any] | None = Field(default=None, description="Final process outputs")
    error: str | None = Field(default=None, description="Error message if failed")
    idempotency_key: str | None = Field(default=None, description="Deduplication key")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = Field(default=None)

    model_config = ConfigDict(frozen=False)


class ProcessTask(BaseModel):
    """A human task within a process run."""

    task_id: str = Field(..., description="Unique task identifier")
    run_id: str = Field(..., description="Parent process run ID")
    step_name: str = Field(..., description="Process step that created this task")
    surface_name: str = Field(..., description="Surface to render for the task")
    entity_name: str = Field(..., description="Entity type being operated on")
    entity_id: str = Field(..., description="Entity instance ID")
    assignee_id: str | None = Field(default=None, description="Assigned user ID")
    assignee_role: str | None = Field(default=None, description="Required role")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    outcome: str | None = Field(default=None, description="Selected outcome (approve/reject/etc)")
    outcome_data: dict[str, Any] | None = Field(default=None, description="Additional outcome data")
    due_at: datetime = Field(..., description="Task deadline")
    escalated_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(frozen=False)


class ProcessAdapter(ABC):
    """
    Abstract interface for process execution backends.

    Implementations:
    - LiteProcessAdapter: In-process with SQLite (dev/simple deployments)
    - TemporalAdapter: Production-grade with Temporal (Phase 5)

    All methods are async to support both in-process and remote backends.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the adapter (database, connections, etc)."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Graceful shutdown, suspending running processes."""
        pass

    # Process Registration
    @abstractmethod
    async def register_process(self, spec: ProcessSpec) -> None:
        """Register a process definition."""
        pass

    @abstractmethod
    async def register_schedule(self, spec: ScheduleSpec) -> None:
        """Register a scheduled job."""
        pass

    # Process Lifecycle
    @abstractmethod
    async def start_process(
        self,
        process_name: str,
        inputs: dict[str, Any],
        idempotency_key: str | None = None,
        dsl_version: str | None = None,
    ) -> str:
        """
        Start a process instance.

        Args:
            process_name: Name of the registered process
            inputs: Input values for the process
            idempotency_key: Optional key for deduplication
            dsl_version: DSL version to bind this run to (for migrations)

        Returns:
            run_id: Unique identifier for this run
        """
        pass

    @abstractmethod
    async def get_run(self, run_id: str) -> ProcessRun | None:
        """Get a process run by ID."""
        pass

    @abstractmethod
    async def list_runs(
        self,
        process_name: str | None = None,
        status: ProcessStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProcessRun]:
        """List process runs with optional filters."""
        pass

    @abstractmethod
    async def cancel_process(self, run_id: str, reason: str) -> None:
        """Cancel a running process."""
        pass

    @abstractmethod
    async def suspend_process(self, run_id: str) -> None:
        """Suspend a running process (for graceful shutdown)."""
        pass

    @abstractmethod
    async def resume_process(self, run_id: str) -> None:
        """Resume a suspended process."""
        pass

    # Signals
    @abstractmethod
    async def signal_process(
        self,
        run_id: str,
        signal_name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Send a signal to a running process."""
        pass

    # Human Tasks
    @abstractmethod
    async def get_task(self, task_id: str) -> ProcessTask | None:
        """Get a human task by ID."""
        pass

    @abstractmethod
    async def list_tasks(
        self,
        run_id: str | None = None,
        assignee_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessTask]:
        """List human tasks with optional filters."""
        pass

    @abstractmethod
    async def complete_task(
        self,
        task_id: str,
        outcome: str,
        outcome_data: dict[str, Any] | None = None,
        completed_by: str | None = None,
    ) -> None:
        """Complete a human task with the selected outcome."""
        pass

    @abstractmethod
    async def reassign_task(
        self,
        task_id: str,
        new_assignee_id: str,
        reason: str | None = None,
    ) -> None:
        """Reassign a human task to another user."""
        pass

    # Version Management
    @abstractmethod
    async def list_runs_by_version(
        self,
        dsl_version: str,
        status: ProcessStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessRun]:
        """
        List runs for a specific DSL version.

        Args:
            dsl_version: DSL version to filter by
            status: Optional status filter
            limit: Maximum number of results

        Returns:
            List of ProcessRun instances
        """
        pass

    @abstractmethod
    async def count_active_runs_by_version(
        self,
        dsl_version: str,
    ) -> int:
        """
        Count active (non-terminal) runs for a DSL version.

        Used for migration drain monitoring.

        Args:
            dsl_version: DSL version to count

        Returns:
            Number of active runs
        """
        pass
