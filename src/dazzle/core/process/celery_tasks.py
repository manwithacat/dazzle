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


@celery_app.task(
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
    elif kind == StepKind.QUERY.value or kind == "query":
        return _execute_query_step(store, run, step)
    elif kind == StepKind.FOREACH.value or kind == "foreach":
        return _execute_foreach_step(store, run, spec, step)
    else:
        logger.warning(f"Unknown step kind: {kind}")
        return {}


_BUILTIN_OPS = frozenset({"create", "read", "update", "delete", "transition"})


def _execute_service_step(run: ProcessRun, step: dict[str, Any]) -> dict[str, Any]:
    """Execute a service call step.

    Supports two modes:
    1. Built-in entity CRUD: ``Entity.create``, ``Entity.read``, etc.
    2. Custom Python service: ``services/{module}_service.py``
    """
    service_name = step.get("service")
    if not service_name:
        return {}

    logger.info(f"Executing service {service_name}")

    parts = service_name.split(".")
    if len(parts) != 2:
        logger.warning(f"Invalid service name format: {service_name}")
        return {}

    entity_name, method_name = parts[0], parts[1]

    # Check for built-in entity CRUD operation
    if method_name in _BUILTIN_OPS:
        return _execute_builtin_entity_op(entity_name, method_name, run)

    # Fall back to custom Python service module
    module_name = entity_name.lower()
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


def _get_db_connection() -> Any:
    """Get a sync psycopg3 connection using DATABASE_URL."""
    import psycopg

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set — cannot execute built-in entity operations")
    return psycopg.connect(database_url, autocommit=True)


def _execute_builtin_entity_op(
    entity_name: str,
    operation: str,
    run: ProcessRun,
) -> dict[str, Any]:
    """Execute a built-in entity CRUD operation.

    Reads entity metadata from Redis (stored by ProcessManager at startup)
    and performs the operation directly against PostgreSQL.

    Supported operations: create, read, update, delete, transition.
    """
    import uuid as uuid_mod

    store = _get_store()
    meta = store.get_entity_meta(entity_name)
    if not meta:
        logger.error(f"No entity metadata for {entity_name} — cannot execute {operation}")
        return {}

    table_name = meta["table_name"]
    valid_fields = set(meta["fields"])
    merged = {**run.inputs, **run.context}

    # Strip process-internal keys from merged data
    _INTERNAL_KEYS = {"entity_id", "entity_name", "event_type", "old_status", "new_status"}

    try:
        conn = _get_db_connection()
    except Exception as e:
        logger.error(f"DB connection failed for {entity_name}.{operation}: {e}")
        return {}

    try:
        if operation == "create":
            return _builtin_create(conn, table_name, valid_fields, merged, _INTERNAL_KEYS, uuid_mod)
        elif operation == "read":
            return _builtin_read(conn, table_name, merged)
        elif operation == "update":
            return _builtin_update(conn, table_name, valid_fields, merged, _INTERNAL_KEYS)
        elif operation == "delete":
            return _builtin_delete(conn, table_name, merged)
        elif operation == "transition":
            return _builtin_transition(conn, table_name, meta, merged)
        else:
            return {}
    except Exception as e:
        logger.exception(f"Built-in {entity_name}.{operation} failed: {e}")
        raise
    finally:
        conn.close()


def _builtin_create(
    conn: Any,
    table_name: str,
    valid_fields: set[str],
    merged: dict[str, Any],
    internal_keys: set[str],
    uuid_mod: Any,
) -> dict[str, Any]:
    """INSERT a new entity row."""
    data = {k: v for k, v in merged.items() if k in valid_fields and k not in internal_keys}
    if "id" not in data:
        data["id"] = str(uuid_mod.uuid4())

    columns = list(data.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    col_list = ", ".join(columns)
    values = [data[c] for c in columns]

    sql = f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders}) RETURNING id'  # noqa: S608
    logger.info(f"Built-in create: INSERT INTO {table_name} ({col_list})")

    with conn.cursor() as cur:
        cur.execute(sql, values)
        row = cur.fetchone()
        created_id = str(row[0]) if row else data["id"]

    return {"output": {"id": created_id, **data}}


def _builtin_read(
    conn: Any,
    table_name: str,
    merged: dict[str, Any],
) -> dict[str, Any]:
    """SELECT an entity row by ID."""
    entity_id = merged.get("entity_id") or merged.get("id")
    if not entity_id:
        logger.error(f"Built-in read: no entity_id in inputs for {table_name}")
        return {}

    sql = f'SELECT * FROM "{table_name}" WHERE id = %s'  # noqa: S608
    with conn.cursor() as cur:
        cur.execute(sql, [entity_id])
        row = cur.fetchone()
        if not row:
            return {"output": None}
        # psycopg3 returns tuples; convert via description
        columns = [desc.name for desc in cur.description]
        result = dict(zip(columns, row, strict=False))
    return {"output": {k: str(v) if hasattr(v, "hex") else v for k, v in result.items()}}


def _builtin_update(
    conn: Any,
    table_name: str,
    valid_fields: set[str],
    merged: dict[str, Any],
    internal_keys: set[str],
) -> dict[str, Any]:
    """UPDATE entity fields by ID."""
    entity_id = merged.get("entity_id") or merged.get("id")
    if not entity_id:
        logger.error(f"Built-in update: no entity_id in inputs for {table_name}")
        return {}

    data = {
        k: v
        for k, v in merged.items()
        if k in valid_fields and k not in internal_keys and k != "id"
    }
    if not data:
        logger.warning(f"Built-in update: no valid fields to update for {table_name}")
        return {"output": {"id": str(entity_id), "updated": False}}

    set_clause = ", ".join(f"{col} = %s" for col in data)
    values = list(data.values()) + [entity_id]

    sql = f'UPDATE "{table_name}" SET {set_clause} WHERE id = %s'  # noqa: S608
    logger.info(f"Built-in update: UPDATE {table_name} SET {set_clause}")

    with conn.cursor() as cur:
        cur.execute(sql, values)
        updated = cur.rowcount > 0

    return {"output": {"id": str(entity_id), "updated": updated, **data}}


def _builtin_delete(
    conn: Any,
    table_name: str,
    merged: dict[str, Any],
) -> dict[str, Any]:
    """DELETE an entity row by ID."""
    entity_id = merged.get("entity_id") or merged.get("id")
    if not entity_id:
        logger.error(f"Built-in delete: no entity_id in inputs for {table_name}")
        return {}

    sql = f'DELETE FROM "{table_name}" WHERE id = %s'  # noqa: S608
    with conn.cursor() as cur:
        cur.execute(sql, [entity_id])
        deleted = cur.rowcount > 0

    return {"output": {"id": str(entity_id), "deleted": deleted}}


def _builtin_transition(
    conn: Any,
    table_name: str,
    meta: dict[str, Any],
    merged: dict[str, Any],
) -> dict[str, Any]:
    """Update the entity's status field (state machine transition)."""
    entity_id = merged.get("entity_id") or merged.get("id")
    if not entity_id:
        logger.error(f"Built-in transition: no entity_id in inputs for {table_name}")
        return {}

    status_field = meta.get("status_field")
    if not status_field:
        logger.error(f"Built-in transition: no status_field in metadata for {table_name}")
        return {}

    new_status = merged.get("new_status") or merged.get(status_field)
    if not new_status:
        logger.error(f"Built-in transition: no new_status in inputs for {table_name}")
        return {}

    sql = f'UPDATE "{table_name}" SET {status_field} = %s WHERE id = %s'  # noqa: S608
    logger.info(f"Built-in transition: {table_name}.{status_field} -> {new_status}")

    with conn.cursor() as cur:
        cur.execute(sql, [new_status, entity_id])
        updated = cur.rowcount > 0

    return {"output": {"id": str(entity_id), status_field: new_status, "transitioned": updated}}


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


def _execute_query_step(
    store: ProcessStateStore,
    run: ProcessRun,
    step: dict[str, Any],
) -> dict[str, Any]:
    """Execute a query step — SELECT entities matching a filter.

    Step fields:
        query_entity: Entity name (= table name)
        query_filter: Django-style filter dict, e.g. {"due_date__lt": "today", "status__not_in": ["completed"]}
        query_limit: Max rows (default 1000)

    Special filter values:
        "today" → current date
        "now" → current datetime
    """
    from datetime import UTC, date, datetime

    entity_name = step.get("query_entity")
    if not entity_name:
        logger.error("Query step missing query_entity")
        return {}

    meta = store.get_entity_meta(entity_name)
    if not meta:
        logger.error(f"No entity metadata for {entity_name} — cannot execute query")
        return {}

    table_name = meta["table_name"]
    valid_fields = set(meta["fields"])
    raw_filter: dict[str, Any] = step.get("query_filter") or {}
    limit = step.get("query_limit", 1000)

    # Resolve date literals and validate field names
    resolved: dict[str, Any] = {}
    for key, value in raw_filter.items():
        # Extract base field name (strip __operator suffix)
        base_field = key.split("__")[0]
        if base_field not in valid_fields:
            logger.warning(
                f"Query filter field '{base_field}' not in {entity_name} metadata — skipping"
            )
            continue
        # Resolve date literals
        if isinstance(value, str):
            if value == "today":
                value = date.today().isoformat()
            elif value == "now":
                value = datetime.now(UTC).isoformat()
        elif isinstance(value, list):
            value = [
                date.today().isoformat()
                if v == "today"
                else datetime.now(UTC).isoformat()
                if v == "now"
                else v
                for v in value
            ]
        resolved[key] = value

    # Build query using QueryBuilder
    from dazzle_back.runtime.query_builder import QueryBuilder

    builder = QueryBuilder(table_name=table_name)
    builder.add_filters(resolved)
    builder.set_pagination(page=1, page_size=limit)

    where_clause, params = builder.build_where_clause()
    sql = f'SELECT * FROM "{table_name}"'  # noqa: S608
    if where_clause:
        sql += f" WHERE {where_clause}"
    sql += f" LIMIT {limit}"

    logger.info(f"Query step: {sql} (params={params})")

    try:
        conn = _get_db_connection()
    except Exception as e:
        logger.error(f"DB connection failed for query on {entity_name}: {e}")
        return {}

    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            if not rows:
                return {"output": []}
            columns = [desc.name for desc in cur.description]
            results = []
            for row in rows:
                record = dict(zip(columns, row, strict=False))
                # Convert UUIDs to strings for JSON compatibility
                results.append({k: str(v) if hasattr(v, "hex") else v for k, v in record.items()})
        logger.info(f"Query step returned {len(results)} rows from {entity_name}")
        return {"output": results}
    except Exception as e:
        logger.exception(f"Query step on {entity_name} failed: {e}")
        raise
    finally:
        conn.close()


def _execute_foreach_step(
    store: ProcessStateStore,
    run: ProcessRun,
    spec: dict[str, Any],
    step: dict[str, Any],
) -> dict[str, Any]:
    """Execute a foreach step — iterate over query results and run sub-steps.

    Step fields:
        foreach_source: Context key holding the list (e.g. "check_overdue" → run.context["check_overdue"])
        foreach_steps: List of step dicts to execute for each item

    Each iteration merges the current item into run.context as "item", so sub-steps
    can reference item fields via run.context["item"]["field_name"].
    """
    source_key = step.get("foreach_source")
    if not source_key:
        logger.error("Foreach step missing foreach_source")
        return {}

    items = run.context.get(source_key)
    if not isinstance(items, list):
        logger.warning(f"Foreach source '{source_key}' is not a list (got {type(items).__name__})")
        return {"output": {"processed": 0}}

    sub_steps = step.get("foreach_steps", [])
    if not sub_steps:
        logger.warning("Foreach step has no sub-steps")
        return {"output": {"processed": 0}}

    processed = 0
    errors = 0
    results: list[dict[str, Any]] = []

    for i, item in enumerate(items):
        # Merge current item into context for sub-step access
        run.context["item"] = item
        run.context["item_index"] = i
        item_results: dict[str, Any] = {}

        for sub_step in sub_steps:
            sub_name = sub_step.get("name", f"sub_{i}")
            try:
                result = _execute_step(store, run, spec, sub_step)
                if result.get("output"):
                    item_results[sub_name] = result["output"]
                    run.context[sub_name] = result["output"]
            except Exception as e:
                logger.error(f"Foreach item {i} sub-step {sub_name} failed: {e}")
                errors += 1

        processed += 1
        results.append(item_results)

    # Clean up iteration context
    run.context.pop("item", None)
    run.context.pop("item_index", None)

    logger.info(f"Foreach step processed {processed} items ({errors} errors)")
    return {"output": {"processed": processed, "errors": errors, "results": results}}


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


@celery_app.task
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


@celery_app.task
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


@celery_app.task
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
