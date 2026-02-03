"""Celery tasks for process execution.

These tasks handle:
- Individual step execution within a process
- Saga compensation on failure
- Human task timeout checking
- Scheduled process triggering

Configuration:
    Set REDIS_URL environment variable for Redis connection.
    Run worker with: celery -A dazzle.core.process.celery_tasks worker -l info --beat
"""

from __future__ import annotations

import logging
import os
import ssl
from datetime import UTC, datetime
from typing import Any

from celery import Celery

from dazzle.core.ir.process import StepKind
from dazzle.core.process.adapter import ProcessRun, ProcessStatus, ProcessTask, TaskStatus
from dazzle.core.process.celery_state import ProcessStateStore

logger = logging.getLogger(__name__)

# Celery app configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

broker_use_ssl = None
if REDIS_URL.startswith("rediss://"):
    broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}

celery_app = Celery(
    "dazzle_processes",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["dazzle.core.process.celery_tasks"],
)

celery_app.conf.update(
    broker_use_ssl=broker_use_ssl,
    redis_backend_use_ssl=broker_use_ssl,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
    worker_prefetch_multiplier=1,
    task_routes={
        "dazzle.core.process.celery_tasks.*": {"queue": "process"},
    },
    task_default_queue="celery",
)


def _get_store() -> ProcessStateStore:
    """Get state store instance."""
    return ProcessStateStore()


@celery_app.task(  # type: ignore[misc]
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
)
def execute_process(self: Any, run_id: str) -> dict[str, Any]:
    """Execute a process from start to finish.

    This is the main entry point for process execution. It:
    1. Loads the process run and spec
    2. Executes each step in sequence
    3. Handles failures with compensation
    4. Updates run status throughout
    """
    from celery.exceptions import MaxRetriesExceededError

    store = _get_store()
    run = store.get_run(run_id)

    if not run:
        logger.error(f"Process run {run_id} not found")
        return {"error": f"Run {run_id} not found"}

    spec = store.get_process_spec(run.process_name)
    if not spec:
        logger.error(f"Process spec {run.process_name} not found")
        _fail_run(store, run, f"Process spec {run.process_name} not found")
        return {"error": f"Spec {run.process_name} not found"}

    # Update status to running
    run.status = ProcessStatus.RUNNING
    run.updated_at = datetime.now(UTC)
    store.save_run(run)

    logger.info(f"Starting process {run.process_name} run {run_id}")

    # Execute steps sequentially
    completed_steps: list[str] = []
    steps = spec.get("steps", [])

    try:
        for step in steps:
            step_name = step.get("name", "unknown")
            run.current_step = step_name
            run.updated_at = datetime.now(UTC)
            store.save_run(run)

            logger.info(f"Executing step {step_name} in run {run_id}")
            step_result = _execute_step(store, run, spec, step)

            if step_result.get("wait"):
                run.status = ProcessStatus.WAITING
                run.updated_at = datetime.now(UTC)
                store.save_run(run)
                return {
                    "status": "waiting",
                    "step": step_name,
                    "task_id": step_result.get("task_id"),
                }

            if step_result.get("output"):
                run.context[step_name] = step_result["output"]

            completed_steps.append(step_name)

        # All steps completed
        run.status = ProcessStatus.COMPLETED
        run.completed_at = datetime.now(UTC)
        run.outputs = run.context
        run.updated_at = datetime.now(UTC)
        store.save_run(run)

        logger.info(f"Process {run.process_name} run {run_id} completed")
        return {"status": "completed", "outputs": run.outputs}

    except Exception as e:
        logger.exception(f"Process {run_id} failed at step {run.current_step}: {e}")
        _run_compensation(store, run, spec, completed_steps, str(e))

        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            _fail_run(store, run, str(e))
            return {"status": "failed", "error": str(e)}


def _execute_step(
    store: ProcessStateStore,
    run: ProcessRun,
    spec: dict[str, Any],
    step: dict[str, Any],
) -> dict[str, Any]:
    """Execute a single process step."""
    kind = step.get("kind", "")

    if kind == StepKind.SERVICE.value or kind == "service":
        return _execute_service_step(run, step)
    elif kind == StepKind.HUMAN_TASK.value or kind == "human_task":
        return _execute_human_task_step(store, run, step)
    elif kind == StepKind.WAIT.value or kind == "wait":
        return _execute_wait_step(run, step)
    elif kind == StepKind.SEND.value or kind == "send":
        return _execute_send_step(run, step)
    else:
        logger.warning(f"Unknown step kind: {kind}")
        return {}


def _execute_service_step(run: ProcessRun, step: dict[str, Any]) -> dict[str, Any]:
    """Execute a service call step."""
    service_name = step.get("service")
    if not service_name:
        return {}

    logger.info(f"Executing service {service_name}")

    parts = service_name.split(".")
    if len(parts) != 2:
        logger.warning(f"Invalid service name format: {service_name}")
        return {}

    module_name, method_name = parts[0].lower(), parts[1]

    try:
        import importlib

        module = importlib.import_module(f"services.{module_name}_service")
        method = getattr(module, method_name, None)
        if method and callable(method):
            result = method(**run.inputs, **run.context)
            return {"output": result}
        else:
            logger.warning(f"Service method {service_name} not found")
            return {}
    except ImportError as e:
        logger.warning(f"Service module not found: {e}")
        return {}
    except Exception as e:
        logger.exception(f"Service {service_name} failed: {e}")
        raise


def _execute_human_task_step(
    store: ProcessStateStore,
    run: ProcessRun,
    step: dict[str, Any],
) -> dict[str, Any]:
    """Create a human task and pause the process."""
    import uuid
    from datetime import timedelta

    task_id = str(uuid.uuid4())
    timeout_seconds = step.get("timeout_seconds", 86400 * 7)
    due_at = datetime.now(UTC) + timedelta(seconds=timeout_seconds)

    task = ProcessTask(
        task_id=task_id,
        run_id=run.run_id,
        step_name=step.get("name", ""),
        surface_name=step.get("surface", ""),
        entity_name=run.inputs.get("entity_name", ""),
        entity_id=run.inputs.get("entity_id", ""),
        assignee_role=step.get("assignee_role"),
        status=TaskStatus.PENDING,
        due_at=due_at,
    )

    store.save_task(task)
    logger.info(f"Created human task {task_id}")

    check_human_task_timeout.apply_async(args=[task_id], countdown=timeout_seconds)

    return {"wait": True, "task_id": task_id}


def _execute_wait_step(run: ProcessRun, step: dict[str, Any]) -> dict[str, Any]:
    """Execute a wait step."""
    logger.info(f"Process {run.run_id} waiting at step {step.get('name')}")
    return {"wait": True}


def _execute_send_step(run: ProcessRun, step: dict[str, Any]) -> dict[str, Any]:
    """Execute a send step."""
    channel = step.get("channel")
    logger.info(f"Send step {step.get('name')} via channel {channel}")
    return {"output": {"sent": True, "channel": channel}}


def _run_compensation(
    store: ProcessStateStore,
    run: ProcessRun,
    spec: dict[str, Any],
    completed_steps: list[str],
    error: str,
) -> None:
    """Run compensation handlers (saga pattern)."""
    run.status = ProcessStatus.COMPENSATING
    run.updated_at = datetime.now(UTC)
    store.save_run(run)

    logger.info(f"Running compensation for {run.run_id}, steps: {completed_steps}")

    steps = spec.get("steps", [])
    for step_name in reversed(completed_steps):
        step = next((s for s in steps if s.get("name") == step_name), None)
        if step and step.get("on_failure"):
            try:
                logger.info(f"Running compensation for step {step_name}")
                _execute_step(store, run, spec, step["on_failure"])
            except Exception as e:
                logger.exception(f"Compensation for {step_name} failed: {e}")


def _fail_run(store: ProcessStateStore, run: ProcessRun, error: str) -> None:
    """Mark a run as failed."""
    run.status = ProcessStatus.FAILED
    run.error = error
    run.completed_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    store.save_run(run)


@celery_app.task  # type: ignore[misc]
def check_human_task_timeout(task_id: str) -> dict[str, Any]:
    """Check if a human task has timed out."""
    store = _get_store()
    task = store.get_task(task_id)

    if not task:
        return {"error": f"Task {task_id} not found"}

    if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.EXPIRED):
        return {"status": task.status.value, "skipped": True}

    if datetime.now(UTC) > task.due_at:
        if task.status == TaskStatus.ESCALATED:
            task.status = TaskStatus.EXPIRED
            task.completed_at = datetime.now(UTC)
            store.save_task(task)
            logger.warning(f"Human task {task_id} expired")

            run = store.get_run(task.run_id)
            if run:
                _fail_run(store, run, f"Human task {task_id} expired")

            return {"status": "expired"}
        else:
            task.status = TaskStatus.ESCALATED
            task.escalated_at = datetime.now(UTC)
            store.save_task(task)
            logger.warning(f"Human task {task_id} escalated")

            check_human_task_timeout.apply_async(args=[task_id], countdown=86400)
            return {"status": "escalated"}

    return {"status": task.status.value, "not_due": True}


@celery_app.task  # type: ignore[misc]
def resume_process_after_task(
    task_id: str, outcome: str, outcome_data: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Resume a process after a human task is completed."""
    store = _get_store()
    task = store.get_task(task_id)

    if not task:
        return {"error": f"Task {task_id} not found"}

    run = store.get_run(task.run_id)
    if not run:
        return {"error": f"Run {task.run_id} not found"}

    run.context[f"{task.step_name}_outcome"] = outcome
    if outcome_data:
        run.context[f"{task.step_name}_data"] = outcome_data

    execute_process.delay(run.run_id)
    return {"status": "resumed", "run_id": run.run_id}


@celery_app.task  # type: ignore[misc]
def trigger_scheduled_process(schedule_name: str) -> dict[str, Any]:
    """Trigger a scheduled process."""
    import uuid

    store = _get_store()
    schedule = store.get_schedule_spec(schedule_name)

    if not schedule:
        return {"error": f"Schedule {schedule_name} not found"}

    process_name = schedule.get("process_name", schedule_name)
    spec = store.get_process_spec(process_name)

    if not spec:
        return {"error": f"Process {process_name} not found"}

    run_id = str(uuid.uuid4())
    run = ProcessRun(
        run_id=run_id,
        process_name=process_name,
        status=ProcessStatus.PENDING,
        inputs={"triggered_by": "schedule", "schedule_name": schedule_name},
    )
    store.save_run(run)
    store.set_schedule_last_run(schedule_name, datetime.now(UTC))

    execute_process.delay(run_id)

    logger.info(f"Triggered scheduled process {process_name} run {run_id}")
    return {"status": "triggered", "run_id": run_id}
