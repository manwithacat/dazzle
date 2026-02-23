"""Redis-backed state store for CeleryProcessAdapter.

This module provides persistent state storage using Redis, suitable for
production deployments on platforms like Heroku where SQLite is not viable.

Key Features:
- Stores process runs, tasks, and schedules in Redis
- Supports horizontal scaling (multiple workers)
- Survives dyno restarts
- Uses Redis key patterns for efficient querying
- All keys have TTLs to prevent unbounded memory growth
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis

from dazzle.core.ir.process import ProcessSpec, ProcessStepSpec, ScheduleSpec
from dazzle.core.process.adapter import (
    ProcessRun,
    ProcessStatus,
    ProcessTask,
    TaskStatus,
)

logger = logging.getLogger(__name__)

# TTL constants (seconds)
_TTL_SPEC = 30 * 86400  # 30 days — process/schedule specs (re-registered on startup)
_TTL_ACTIVE_RUN = 30 * 86400  # 30 days — running/pending/waiting/suspended runs
_TTL_COMPLETED_RUN = 7 * 86400  # 7 days — completed/failed/cancelled runs
_TTL_ACTIVE_TASK = 30 * 86400  # 30 days — pending/in-progress tasks
_TTL_COMPLETED_TASK = 7 * 86400  # 7 days — completed/cancelled tasks
_TTL_INDEX = 30 * 86400  # 30 days — index sets (refreshed on write)
_TTL_ENTITY_META = 30 * 86400  # 30 days — entity metadata


class _ProcessEncoder(json.JSONEncoder):
    """JSON encoder that handles common DB types (UUID, datetime, Decimal)."""

    def default(self, obj: object) -> object:
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _get_redis_client(url: str | None = None) -> redis.Redis:
    """Get Redis client, handling Heroku's rediss:// URL."""
    import redis as redis_lib

    if url is None:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    ssl_params = {}
    if url.startswith("rediss://"):
        import ssl

        ssl_params = {"ssl_cert_reqs": ssl.CERT_NONE}

    return redis_lib.from_url(url, decode_responses=True, **ssl_params)


class ProcessStateStore:
    """Redis-backed state store for process execution.

    Key Schema:
        process:spec:{name} - Process specification JSON
        schedule:spec:{name} - Schedule specification JSON
        run:{run_id} - Process run JSON
        run:idx:process:{name} - Set of run IDs for a process
        run:idx:status:{status} - Set of run IDs by status
        task:{task_id} - Human task JSON
        task:idx:run:{run_id} - Set of task IDs for a run
    """

    def __init__(self, redis_client: redis.Redis | None = None, redis_url: str | None = None):
        """Initialize the state store.

        Args:
            redis_client: Optional pre-configured Redis client
            redis_url: Optional Redis URL (uses REDIS_URL env var if not provided)
        """
        self._redis = redis_client or _get_redis_client(redis_url)

    # Process Specifications

    def register_process(self, spec: ProcessSpec) -> None:
        """Register a process specification."""
        key = f"process:spec:{spec.name}"
        # Store as JSON - ProcessSpec should be serializable
        data = {
            "name": spec.name,
            "version": getattr(spec, "version", "1.0"),
            "steps": [self._serialize_step(s) for s in spec.steps],
        }
        self._redis.set(key, json.dumps(data, cls=_ProcessEncoder), ex=_TTL_SPEC)
        logger.debug(f"Registered process spec: {spec.name}")

    def get_process_spec(self, name: str) -> dict[str, Any] | None:
        """Get a process specification by name."""
        key = f"process:spec:{name}"
        data = self._redis.get(key)
        if not data:
            return None
        # Return raw dict - caller will need to handle reconstruction
        result: dict[str, Any] = json.loads(data)
        return result

    def _serialize_step(self, step: ProcessStepSpec) -> dict[str, Any]:
        """Serialize a process step to dict."""
        data: dict[str, Any] = {
            "name": step.name,
            "kind": step.kind.value if hasattr(step.kind, "value") else str(step.kind),
            "service": getattr(step, "service", None),
            "surface": getattr(step, "surface", None),
            "channel": getattr(step, "channel", None),
            "timeout_seconds": getattr(step, "timeout_seconds", None),
        }
        # Query step fields
        if getattr(step, "query_entity", None):
            data["query_entity"] = step.query_entity
            data["query_filter"] = getattr(step, "query_filter", None)
            data["query_limit"] = getattr(step, "query_limit", 1000)
        # Foreach step fields
        if getattr(step, "foreach_source", None):
            data["foreach_source"] = step.foreach_source
            data["foreach_steps"] = [
                self._serialize_step(s) for s in getattr(step, "foreach_steps", [])
            ]
        return data

    # Schedule Specifications

    def register_schedule(self, spec: ScheduleSpec) -> None:
        """Register a schedule specification."""
        key = f"schedule:spec:{spec.name}"
        data = {
            "name": spec.name,
            "process_name": getattr(spec, "process_name", spec.name),
            "cron": getattr(spec, "cron", None),
            "interval_seconds": getattr(spec, "interval_seconds", None),
        }
        self._redis.set(key, json.dumps(data, cls=_ProcessEncoder), ex=_TTL_SPEC)
        logger.debug(f"Registered schedule spec: {spec.name}")

    def get_schedule_spec(self, name: str) -> dict[str, Any] | None:
        """Get a schedule specification by name."""
        key = f"schedule:spec:{name}"
        data = self._redis.get(key)
        if not data:
            return None
        result: dict[str, Any] = json.loads(data)
        return result

    def list_schedule_specs(self) -> list[dict[str, Any]]:
        """List all registered schedules."""
        pattern = "schedule:spec:*"
        keys = self._redis.keys(pattern)
        specs = []
        for key in keys:
            data = self._redis.get(key)
            if data:
                specs.append(json.loads(data))
        return specs

    def set_schedule_last_run(self, name: str, timestamp: datetime) -> None:
        """Record the last run time for a schedule."""
        key = f"schedule:lastrun:{name}"
        self._redis.set(key, timestamp.isoformat(), ex=_TTL_SPEC)

    # Process Runs

    def save_run(self, run: ProcessRun) -> None:
        """Save a process run."""
        key = f"run:{run.run_id}"
        data = {
            "run_id": run.run_id,
            "process_name": run.process_name,
            "process_version": run.process_version,
            "dsl_version": run.dsl_version,
            "status": run.status.value,
            "inputs": run.inputs,
            "context": run.context,
            "outputs": run.outputs,
            "current_step": run.current_step,
            "error": run.error,
            "idempotency_key": run.idempotency_key,
            "started_at": run.started_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
        terminal = run.status in (
            ProcessStatus.COMPLETED,
            ProcessStatus.FAILED,
            ProcessStatus.CANCELLED,
        )
        ttl = _TTL_COMPLETED_RUN if terminal else _TTL_ACTIVE_RUN
        self._redis.set(key, json.dumps(data, cls=_ProcessEncoder), ex=ttl)

        # Update indexes (refresh TTL on each write)
        idx_process = f"run:idx:process:{run.process_name}"
        idx_status = f"run:idx:status:{run.status.value}"
        self._redis.sadd(idx_process, run.run_id)
        self._redis.expire(idx_process, _TTL_INDEX)
        self._redis.sadd(idx_status, run.run_id)
        self._redis.expire(idx_status, _TTL_INDEX)

        logger.debug(f"Saved run {run.run_id} with status {run.status}")

    def get_run(self, run_id: str) -> ProcessRun | None:
        """Get a process run by ID."""
        key = f"run:{run_id}"
        data = self._redis.get(key)
        if not data:
            return None
        return self._deserialize_run(json.loads(data))

    def _deserialize_run(self, data: dict[str, Any]) -> ProcessRun:
        """Deserialize a process run from dict."""
        return ProcessRun(
            run_id=data["run_id"],
            process_name=data["process_name"],
            process_version=data.get("process_version", "1.0"),
            dsl_version=data.get("dsl_version", "0.1"),
            status=ProcessStatus(data["status"]),
            inputs=data.get("inputs", {}),
            context=data.get("context", {}),
            outputs=data.get("outputs"),
            current_step=data.get("current_step"),
            error=data.get("error"),
            idempotency_key=data.get("idempotency_key"),
            started_at=datetime.fromisoformat(data["started_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            completed_at=(
                datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
            ),
        )

    def list_runs(
        self,
        process_name: str | None = None,
        status: ProcessStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProcessRun]:
        """List process runs with optional filters."""
        if process_name:
            run_ids = self._redis.smembers(f"run:idx:process:{process_name}")
        elif status:
            run_ids = self._redis.smembers(f"run:idx:status:{status.value}")
        else:
            # Get all runs - scan for run:* keys
            run_ids = set()
            for key in self._redis.scan_iter("run:*"):
                if key.startswith("run:") and not key.startswith("run:idx:"):
                    run_ids.add(key.replace("run:", ""))

        # Apply offset and limit
        run_ids = sorted(run_ids)[offset : offset + limit]

        runs = []
        for run_id in run_ids:
            run = self.get_run(run_id)
            if run:
                # Apply status filter if both filters specified
                if status and run.status != status:
                    continue
                runs.append(run)

        return runs

    def list_runs_by_version(
        self,
        dsl_version: str,
        status: ProcessStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessRun]:
        """List runs for a specific DSL version."""
        all_runs = self.list_runs(status=status, limit=1000)
        return [r for r in all_runs if r.dsl_version == dsl_version][:limit]

    def count_active_runs_by_version(self, dsl_version: str) -> int:
        """Count active runs for a DSL version."""
        active_statuses = {
            ProcessStatus.PENDING,
            ProcessStatus.RUNNING,
            ProcessStatus.WAITING,
            ProcessStatus.SUSPENDED,
        }
        count = 0
        for status in active_statuses:
            runs = self.list_runs(status=status, limit=1000)
            count += len([r for r in runs if r.dsl_version == dsl_version])
        return count

    # Human Tasks

    def save_task(self, task: ProcessTask) -> None:
        """Save a human task."""
        key = f"task:{task.task_id}"
        data = {
            "task_id": task.task_id,
            "run_id": task.run_id,
            "step_name": task.step_name,
            "surface_name": task.surface_name,
            "entity_name": task.entity_name,
            "entity_id": task.entity_id,
            "assignee_role": task.assignee_role,
            "assignee_id": task.assignee_id,
            "status": task.status.value,
            "outcome": task.outcome,
            "outcome_data": task.outcome_data,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "escalated_at": task.escalated_at.isoformat() if task.escalated_at else None,
        }
        terminal = task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
        ttl = _TTL_COMPLETED_TASK if terminal else _TTL_ACTIVE_TASK
        self._redis.set(key, json.dumps(data, cls=_ProcessEncoder), ex=ttl)

        # Update indexes (refresh TTL on each write)
        idx_run = f"task:idx:run:{task.run_id}"
        self._redis.sadd(idx_run, task.task_id)
        self._redis.expire(idx_run, _TTL_INDEX)
        if task.assignee_id:
            idx_assignee = f"task:idx:assignee:{task.assignee_id}"
            self._redis.sadd(idx_assignee, task.task_id)
            self._redis.expire(idx_assignee, _TTL_INDEX)

    def get_task(self, task_id: str) -> ProcessTask | None:
        """Get a human task by ID."""
        key = f"task:{task_id}"
        data = self._redis.get(key)
        if not data:
            return None
        return self._deserialize_task(json.loads(data))

    def _deserialize_task(self, data: dict[str, Any]) -> ProcessTask:
        """Deserialize a task from dict."""
        return ProcessTask(
            task_id=data["task_id"],
            run_id=data["run_id"],
            step_name=data["step_name"],
            surface_name=data.get("surface_name", ""),
            entity_name=data.get("entity_name", ""),
            entity_id=data.get("entity_id", ""),
            assignee_role=data.get("assignee_role"),
            assignee_id=data.get("assignee_id"),
            status=TaskStatus(data["status"]),
            outcome=data.get("outcome"),
            outcome_data=data.get("outcome_data"),
            due_at=datetime.fromisoformat(data["due_at"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            completed_at=(
                datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
            ),
            escalated_at=(
                datetime.fromisoformat(data["escalated_at"]) if data.get("escalated_at") else None
            ),
        )

    def list_tasks(
        self,
        run_id: str | None = None,
        assignee_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessTask]:
        """List human tasks with optional filters."""
        if run_id:
            task_ids = self._redis.smembers(f"task:idx:run:{run_id}")
        elif assignee_id:
            task_ids = self._redis.smembers(f"task:idx:assignee:{assignee_id}")
        else:
            # Get all tasks
            task_ids = set()
            for key in self._redis.scan_iter("task:*"):
                if key.startswith("task:") and not key.startswith("task:idx:"):
                    task_ids.add(key.replace("task:", ""))

        task_ids = sorted(task_ids)[:limit]

        tasks = []
        for task_id in task_ids:
            task = self.get_task(task_id)
            if task:
                if status and task.status != status:
                    continue
                tasks.append(task)

        return tasks

    # Entity Metadata (for built-in CRUD operations in service steps)

    def save_entity_meta(self, entity_name: str, meta: dict[str, Any]) -> None:
        """Store entity metadata for use by built-in service step operations."""
        key = f"entity:meta:{entity_name}"
        self._redis.set(key, json.dumps(meta, cls=_ProcessEncoder), ex=_TTL_ENTITY_META)

    def get_entity_meta(self, entity_name: str) -> dict[str, Any] | None:
        """Get entity metadata by name."""
        key = f"entity:meta:{entity_name}"
        data = self._redis.get(key)
        if not data:
            return None
        result: dict[str, Any] = json.loads(data)
        return result
