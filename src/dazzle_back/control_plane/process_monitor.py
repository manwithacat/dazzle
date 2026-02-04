"""
Process Monitor - queries process state from Redis.

Reads the same Redis keys used by the CeleryProcessAdapter/LiteProcessAdapter
to provide visibility into running processes, completed tasks, and execution history.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis import Redis


class ProcessStatus(StrEnum):
    """Process run status (matches Dazzle core)."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    SUSPENDED = "suspended"
    COMPENSATING = "compensating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    """Human task status."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    ESCALATED = "escalated"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass
class ProcessRunInfo:
    """Summary of a process run."""

    id: str
    process_name: str
    status: str
    started_at: float | None = None
    completed_at: float | None = None
    current_step: str | None = None
    error: str | None = None
    tenant_id: str | None = None
    dsl_version: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate run duration."""
        if not self.started_at:
            return None
        end = self.completed_at or time.time()
        return end - self.started_at

    @property
    def duration_str(self) -> str:
        """Format duration as human-readable string."""
        duration = self.duration_seconds
        if duration is None:
            return "-"
        if duration < 60:
            return f"{duration:.1f}s"
        if duration < 3600:
            return f"{duration / 60:.1f}m"
        return f"{duration / 3600:.1f}h"


@dataclass
class HumanTaskInfo:
    """Summary of a human task."""

    id: str
    run_id: str
    task_type: str
    status: str
    assignee: str | None = None
    due_at: float | None = None
    created_at: float | None = None
    completed_at: float | None = None

    @property
    def is_overdue(self) -> bool:
        """Check if task is past due."""
        if self.due_at is None:
            return False
        return time.time() > self.due_at and self.status in ("pending", "assigned")


@dataclass
class ProcessStats:
    """Aggregate process statistics."""

    total_runs: int = 0
    running: int = 0
    waiting: int = 0
    completed: int = 0
    failed: int = 0
    pending_tasks: int = 0
    overdue_tasks: int = 0


class ProcessMonitor:
    """
    Monitors process state stored in Redis.

    Uses the same key structure as CeleryProcessAdapter's ProcessStateStore.
    """

    # Redis key prefix (matches CeleryProcessAdapter)
    PREFIX = "dazzle:"

    def __init__(self, redis: Redis[Any]):
        self._redis = redis

    def _key(self, *parts: str) -> str:
        """Build a Redis key with prefix."""
        return self.PREFIX + ":".join(parts)

    def get_stats(self) -> ProcessStats:
        """Get aggregate process statistics."""
        stats = ProcessStats()

        # Count runs by status
        for status in ProcessStatus:
            key = self._key("runs_by_status", status.value)
            count = self._redis.scard(key) or 0
            stats.total_runs += count

            if status == ProcessStatus.RUNNING:
                stats.running = count
            elif status == ProcessStatus.WAITING:
                stats.waiting = count
            elif status == ProcessStatus.COMPLETED:
                stats.completed = count
            elif status == ProcessStatus.FAILED:
                stats.failed = count

        # Count pending tasks
        stats.pending_tasks = self._redis.scard(self._key("tasks_by_status", "pending")) or 0

        # Count overdue tasks (approximate - scan pending tasks)
        pending_task_ids = self._redis.smembers(self._key("tasks_by_status", "pending")) or set()
        time.time()
        for task_id in list(pending_task_ids)[:100]:  # Limit scan
            task = self.get_task(task_id)
            if task and task.is_overdue:
                stats.overdue_tasks += 1

        return stats

    def get_recent_runs(self, count: int = 20, status: str | None = None) -> list[ProcessRunInfo]:
        """
        Get recent process runs.

        Args:
            count: Maximum number of runs to return
            status: Optional status filter

        Returns:
            List of ProcessRunInfo, newest first
        """
        if status:
            run_ids = self._redis.smembers(self._key("runs_by_status", status)) or set()
            run_ids = list(run_ids)[:count]
        else:
            run_ids = self._redis.zrevrange(self._key("runs_by_time"), 0, count - 1) or []

        runs = []
        for run_id in run_ids:
            run = self.get_run(run_id)
            if run:
                runs.append(run)

        # Sort by started_at descending
        runs.sort(key=lambda r: r.started_at or 0, reverse=True)
        return runs[:count]

    def get_run(self, run_id: str) -> ProcessRunInfo | None:
        """Get a single process run by ID."""
        data = self._redis.get(self._key("process_run", run_id))
        if not data:
            return None

        try:
            run_data = json.loads(data)
            return ProcessRunInfo(
                id=run_data.get("id", run_id),
                process_name=run_data.get("process_name", "unknown"),
                status=run_data.get("status", "unknown"),
                started_at=self._parse_timestamp(run_data.get("started_at")),
                completed_at=self._parse_timestamp(run_data.get("completed_at")),
                current_step=run_data.get("current_step"),
                error=run_data.get("error"),
                tenant_id=run_data.get("tenant_id"),
                dsl_version=run_data.get("dsl_version"),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def get_active_runs(self) -> list[ProcessRunInfo]:
        """Get all currently active (running or waiting) runs."""
        runs = []
        for status in [
            ProcessStatus.RUNNING,
            ProcessStatus.WAITING,
            ProcessStatus.PENDING,
        ]:
            runs.extend(self.get_recent_runs(count=50, status=status.value))
        return runs

    def get_task(self, task_id: str) -> HumanTaskInfo | None:
        """Get a single human task by ID."""
        data = self._redis.get(self._key("process_task", task_id))
        if not data:
            return None

        try:
            task_data = json.loads(data)
            return HumanTaskInfo(
                id=task_data.get("id", task_id),
                run_id=task_data.get("run_id", ""),
                task_type=task_data.get("task_type", "unknown"),
                status=task_data.get("status", "unknown"),
                assignee=task_data.get("assignee"),
                due_at=self._parse_timestamp(task_data.get("due_at")),
                created_at=self._parse_timestamp(task_data.get("created_at")),
                completed_at=self._parse_timestamp(task_data.get("completed_at")),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def get_pending_tasks(self, count: int = 20) -> list[HumanTaskInfo]:
        """Get pending human tasks."""
        task_ids = self._redis.smembers(self._key("tasks_by_status", "pending")) or set()
        task_ids = list(task_ids)[:count]

        tasks = []
        for task_id in task_ids:
            task = self.get_task(task_id)
            if task:
                tasks.append(task)

        # Sort by due_at (most urgent first)
        tasks.sort(key=lambda t: t.due_at or float("inf"))
        return tasks

    def get_tasks_for_run(self, run_id: str) -> list[HumanTaskInfo]:
        """Get all tasks for a process run."""
        task_ids = self._redis.smembers(self._key("tasks_by_run", run_id)) or set()

        tasks = []
        for task_id in task_ids:
            task = self.get_task(task_id)
            if task:
                tasks.append(task)

        return tasks

    def _parse_timestamp(self, value: Any) -> float | None:
        """Parse a timestamp from various formats."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.timestamp()
            except ValueError:
                try:
                    return float(value)
                except ValueError:
                    return None
        return None
