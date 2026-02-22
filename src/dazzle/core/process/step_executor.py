"""Standalone process step executor.

Extracted from celery_tasks.py to decouple step execution logic from
any specific task queue backend. Both CeleryProcessAdapter and
EventBusProcessAdapter use this module for actual step execution.

The executor is synchronous (uses psycopg sync connections) because
step execution happens in a worker context where blocking is acceptable.
"""

from __future__ import annotations

import importlib
import logging
import os
import uuid as uuid_mod
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from dazzle.core.ir.process import StepKind
from dazzle.core.process.adapter import (
    ProcessRun,
    ProcessStatus,
    ProcessTask,
    TaskStatus,
)

if TYPE_CHECKING:
    from dazzle.core.process.celery_state import ProcessStateStore

logger = logging.getLogger(__name__)

# Callback type for scheduling delayed work (timeout checks, process resumption).
# Adapters provide their own implementation:
#   - Celery: check_human_task_timeout.apply_async(args=[task_id], countdown=seconds)
#   - EventBus: publish delayed event to process.task_timeout topic
DelayedCallback = Any  # Callable[[str, float], None] — (task_id, delay_seconds)


_BUILTIN_OPS = frozenset({"create", "read", "update", "delete", "transition"})


def execute_process_steps(
    store: ProcessStateStore,
    run: ProcessRun,
    *,
    on_task_created: DelayedCallback | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Execute all steps of a process run sequentially.

    Args:
        store: State store for reading specs and saving state.
        run: The process run to execute.
        on_task_created: Callback invoked when a human task is created.
            Signature: (task_id: str, timeout_seconds: float) -> None.
            Used to schedule timeout checks via the adapter's mechanism.
        max_retries: Not used directly here — caller handles retry logic.

    Returns:
        Dict with status and results. Possible shapes:
        - {"status": "completed", "outputs": {...}}
        - {"status": "waiting", "step": "...", "task_id": "..."}
        - {"status": "failed", "error": "..."}
    """
    spec = store.get_process_spec(run.process_name)
    if not spec:
        logger.error(f"Process spec {run.process_name} not found")
        fail_run(store, run, f"Process spec {run.process_name} not found")
        return {"status": "failed", "error": f"Spec {run.process_name} not found"}

    # Update status to running
    run.status = ProcessStatus.RUNNING
    run.updated_at = datetime.now(UTC)
    store.save_run(run)

    logger.info(f"Starting process {run.process_name} run {run.run_id}")

    # Execute steps sequentially
    completed_steps: list[str] = []
    steps = spec.get("steps", [])

    try:
        for step in steps:
            step_name = step.get("name", "unknown")
            run.current_step = step_name
            run.updated_at = datetime.now(UTC)
            store.save_run(run)

            logger.info(f"Executing step {step_name} in run {run.run_id}")
            step_result = execute_step(store, run, spec, step, on_task_created=on_task_created)

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

        logger.info(f"Process {run.process_name} run {run.run_id} completed")
        return {"status": "completed", "outputs": run.outputs}

    except Exception as e:
        logger.exception(f"Process {run.run_id} failed at step {run.current_step}: {e}")
        run_compensation(store, run, spec, completed_steps, str(e))
        raise


def execute_step(
    store: ProcessStateStore,
    run: ProcessRun,
    spec: dict[str, Any],
    step: dict[str, Any],
    *,
    on_task_created: DelayedCallback | None = None,
) -> dict[str, Any]:
    """Execute a single process step."""
    kind = step.get("kind", "")

    if kind == StepKind.SERVICE.value or kind == "service":
        return _execute_service_step(run, step)
    elif kind == StepKind.HUMAN_TASK.value or kind == "human_task":
        return _execute_human_task_step(store, run, step, on_task_created=on_task_created)
    elif kind == StepKind.WAIT.value or kind == "wait":
        return _execute_wait_step(run, step)
    elif kind == StepKind.SEND.value or kind == "send":
        return _execute_send_step(run, step)
    elif kind == StepKind.QUERY.value or kind == "query":
        return _execute_query_step(store, run, step)
    elif kind == StepKind.FOREACH.value or kind == "foreach":
        return _execute_foreach_step(store, run, spec, step, on_task_created=on_task_created)
    else:
        logger.warning(f"Unknown step kind: {kind}")
        return {}


# ---------------------------------------------------------------------------
# Service step
# ---------------------------------------------------------------------------


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

    entity_name, method_name = parts[0], parts[1]

    if method_name in _BUILTIN_OPS:
        return _execute_builtin_entity_op(entity_name, method_name, run)

    # Custom Python service module
    module_name = entity_name.lower()
    try:
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


# ---------------------------------------------------------------------------
# Built-in entity CRUD
# ---------------------------------------------------------------------------


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
    """Execute a built-in entity CRUD operation."""
    from dazzle.core.process.celery_state import ProcessStateStore

    store = ProcessStateStore()
    meta = store.get_entity_meta(entity_name)
    if not meta:
        logger.error(f"No entity metadata for {entity_name} — cannot execute {operation}")
        return {}

    table_name = meta["table_name"]
    valid_fields = set(meta["fields"])
    merged = {**run.inputs, **run.context}
    internal_keys = {"entity_id", "entity_name", "event_type", "old_status", "new_status"}

    try:
        conn = _get_db_connection()
    except Exception as e:
        logger.error(f"DB connection failed for {entity_name}.{operation}: {e}")
        return {}

    try:
        if operation == "create":
            return _builtin_create(conn, table_name, valid_fields, merged, internal_keys)
        elif operation == "read":
            return _builtin_read(conn, table_name, merged)
        elif operation == "update":
            return _builtin_update(conn, table_name, valid_fields, merged, internal_keys)
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


def _builtin_read(conn: Any, table_name: str, merged: dict[str, Any]) -> dict[str, Any]:
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


def _builtin_delete(conn: Any, table_name: str, merged: dict[str, Any]) -> dict[str, Any]:
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
    conn: Any, table_name: str, meta: dict[str, Any], merged: dict[str, Any]
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


# ---------------------------------------------------------------------------
# Human task step
# ---------------------------------------------------------------------------


def _execute_human_task_step(
    store: ProcessStateStore,
    run: ProcessRun,
    step: dict[str, Any],
    *,
    on_task_created: DelayedCallback | None = None,
) -> dict[str, Any]:
    """Create a human task and pause the process."""
    task_id = str(uuid_mod.uuid4())
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

    # Schedule timeout check via adapter-provided callback
    if on_task_created:
        on_task_created(task_id, timeout_seconds)

    return {"wait": True, "task_id": task_id}


# ---------------------------------------------------------------------------
# Wait / Send steps
# ---------------------------------------------------------------------------


def _execute_wait_step(run: ProcessRun, step: dict[str, Any]) -> dict[str, Any]:
    """Execute a wait step."""
    logger.info(f"Process {run.run_id} waiting at step {step.get('name')}")
    return {"wait": True}


def _execute_send_step(run: ProcessRun, step: dict[str, Any]) -> dict[str, Any]:
    """Execute a send step."""
    channel = step.get("channel")
    logger.info(f"Send step {step.get('name')} via channel {channel}")
    return {"output": {"sent": True, "channel": channel}}


# ---------------------------------------------------------------------------
# Query step
# ---------------------------------------------------------------------------


def _execute_query_step(
    store: ProcessStateStore,
    run: ProcessRun,
    step: dict[str, Any],
) -> dict[str, Any]:
    """Execute a query step — SELECT entities matching a filter."""
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

    resolved: dict[str, Any] = {}
    for key, value in raw_filter.items():
        base_field = key.split("__")[0]
        if base_field not in valid_fields:
            logger.warning(
                f"Query filter field '{base_field}' not in {entity_name} metadata — skipping"
            )
            continue
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
                results.append({k: str(v) if hasattr(v, "hex") else v for k, v in record.items()})
        logger.info(f"Query step returned {len(results)} rows from {entity_name}")
        return {"output": results}
    except Exception as e:
        logger.exception(f"Query step on {entity_name} failed: {e}")
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Foreach step
# ---------------------------------------------------------------------------


def _execute_foreach_step(
    store: ProcessStateStore,
    run: ProcessRun,
    spec: dict[str, Any],
    step: dict[str, Any],
    *,
    on_task_created: DelayedCallback | None = None,
) -> dict[str, Any]:
    """Execute a foreach step — iterate over query results and run sub-steps."""
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
        run.context["item"] = item
        run.context["item_index"] = i
        item_results: dict[str, Any] = {}

        for sub_step in sub_steps:
            sub_name = sub_step.get("name", f"sub_{i}")
            try:
                result = execute_step(store, run, spec, sub_step, on_task_created=on_task_created)
                if result.get("output"):
                    item_results[sub_name] = result["output"]
                    run.context[sub_name] = result["output"]
            except Exception as e:
                logger.error(f"Foreach item {i} sub-step {sub_name} failed: {e}")
                errors += 1

        processed += 1
        results.append(item_results)

    run.context.pop("item", None)
    run.context.pop("item_index", None)

    logger.info(f"Foreach step processed {processed} items ({errors} errors)")
    return {"output": {"processed": processed, "errors": errors, "results": results}}


# ---------------------------------------------------------------------------
# Compensation & failure
# ---------------------------------------------------------------------------


def run_compensation(
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
                execute_step(store, run, spec, step["on_failure"])
            except Exception as e:
                logger.exception(f"Compensation for {step_name} failed: {e}")


def fail_run(store: ProcessStateStore, run: ProcessRun, error: str) -> None:
    """Mark a run as failed."""
    run.status = ProcessStatus.FAILED
    run.error = error
    run.completed_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    store.save_run(run)


def check_task_timeout(store: ProcessStateStore, task_id: str) -> dict[str, Any]:
    """Check if a human task has timed out.

    Returns a dict describing the action taken. The caller is responsible
    for scheduling follow-up timeout checks if needed.
    """
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
                fail_run(store, run, f"Human task {task_id} expired")

            return {"status": "expired"}
        else:
            task.status = TaskStatus.ESCALATED
            task.escalated_at = datetime.now(UTC)
            store.save_task(task)
            logger.warning(f"Human task {task_id} escalated")
            return {"status": "escalated", "needs_followup": True, "followup_seconds": 86400}

    return {"status": task.status.value, "not_due": True}
