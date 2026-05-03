"""Entity-event → job-enqueue plumbing (#953 cycle 6).

Wires the cycle-1 ``JobTrigger`` declarations to the cycle-3 queue
so a project author's

    job thumbnail_render "Generate thumbnail":
      trigger: on_create Manuscript when source_pdf is_set
      run: app.jobs:render_thumbnail

…enqueues a `thumbnail_render` job whenever a Manuscript is
created with a non-null ``source_pdf``.

Mirrors #956 cycle 4's audit-emitter wiring shape:
``register_job_triggers`` iterates the AppSpec's jobs, looks up the
matching service for each trigger's entity, and attaches the
three lifecycle callbacks. Cycle-3 ``BaseService.on_*`` infra is
re-used as-is.

Cycle 7 will refine ``when_condition`` evaluation against the row
(currently we honour just the basic ``is_set`` / ``is_null`` shape;
arbitrary expression evaluation is its own primitive). Cycle 8 will
swap the queue from in-memory to Redis-backed.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from dazzle_back.runtime.job_queue import JobQueue

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure: should_fire
# ---------------------------------------------------------------------------


def should_fire(
    trigger: Any,
    *,
    event_kind: str,
    old_data: dict[str, Any] | None,
    new_data: dict[str, Any] | None,
) -> bool:
    """Decide whether ``trigger`` matches the given mutation.

    Args:
        trigger: A ``JobTrigger`` IR node — has ``event``,
            optional ``field``, optional ``when_condition``.
        event_kind: ``"created"`` / ``"updated"`` / ``"deleted"``
            from the service callback.
        old_data: Pre-mutation field values (``None`` for create).
        new_data: Post-mutation field values (``None`` for delete).

    Returns:
        True when the trigger should fire — caller (cycle-6 callback
        factory) then enqueues the job. False short-circuits without
        a queue write.
    """
    trigger_event = (getattr(trigger, "event", "") or "").lower()
    trigger_field = (getattr(trigger, "field", None) or "").strip()
    when = (getattr(trigger, "when_condition", None) or "").strip()

    # 1. Event match — `field_changed` has special semantics that
    #    requires inspecting old vs new on the named field. The
    #    callback factory dispatches both ``updated`` and
    #    ``field_changed`` for an update event; this branch must
    #    only fire for the latter, so the explicit `event_kind`
    #    check is required.
    if trigger_event == "field_changed":
        if event_kind != "field_changed":
            return False
        if not trigger_field:
            return False
        if old_data is None or new_data is None:
            # Field-changed on create or delete is meaningless —
            # those go through `created` / `deleted` instead.
            return False
        if old_data.get(trigger_field) == new_data.get(trigger_field):
            return False  # value didn't actually change
    elif trigger_event != event_kind:
        return False

    # 2. when_condition — cycle-1 supports `is_set` / `is_null`
    #    over a named field; arbitrary expression eval is cycle-7.
    if when:
        return _evaluate_when(when, new_data or old_data or {})

    return True


def _evaluate_when(condition: str, row: dict[str, Any]) -> bool:
    """Tiny `is_set` / `is_null` evaluator for cycle-1 trigger
    conditions.

    Supports two forms:
      * ``"<field> is_set"`` — True when ``row[field]`` is truthy
        (covers the common "non-null + non-empty" check).
      * ``"<field> is_null"`` — True when ``row[field]`` is None.

    Anything else logs a warning and returns False (fail-closed —
    a misconfigured trigger shouldn't accidentally enqueue).
    """
    parts = condition.split(maxsplit=1)
    if len(parts) != 2:
        logger.warning("Unparseable when_condition %r — denying", condition)
        return False
    field_name, op = parts
    op = op.strip()
    value = row.get(field_name)
    if op == "is_set":
        return bool(value)
    if op == "is_null":
        return value is None
    logger.warning(
        "Unknown when_condition operator %r — cycle-7 will add expression eval",
        op,
    )
    return False


# ---------------------------------------------------------------------------
# Callback factory
# ---------------------------------------------------------------------------


def build_trigger_callbacks(
    *,
    job_name: str,
    triggers: list[Any],
    queue: JobQueue,
) -> dict[str, Callable[..., Awaitable[None]]]:
    """Build on_created / on_updated / on_deleted callbacks for one
    job's triggers.

    Each callback walks the triggers, asks `should_fire`, and
    enqueues a single message per matching trigger. Failures inside
    `submit` are swallowed + logged so a queue blip doesn't break
    the user's mutation.
    """

    async def _safe_submit(payload: dict[str, Any]) -> None:
        try:
            await queue.submit(job_name, payload=payload)
        except Exception:
            logger.warning("Job enqueue failed for %s — continuing", job_name, exc_info=True)

    async def _dispatch(
        event_kind: str,
        entity_id: str,
        new_data: dict[str, Any] | None,
        old_data: dict[str, Any] | None,
    ) -> None:
        for trigger in triggers:
            if should_fire(
                trigger,
                event_kind=event_kind,
                old_data=old_data,
                new_data=new_data,
            ):
                await _safe_submit(
                    {
                        "entity_id": entity_id,
                        "entity_type": getattr(trigger, "entity", ""),
                        "event": event_kind,
                        "row": new_data or old_data or {},
                    }
                )

    async def on_created(
        entity_id: str,
        entity_data: dict[str, Any],
        _old: dict[str, Any] | None,
        _op: str,
    ) -> None:
        await _dispatch("created", entity_id, entity_data, None)

    async def on_updated(
        entity_id: str,
        entity_data: dict[str, Any],
        old_data: dict[str, Any] | None,
        _op: str,
    ) -> None:
        await _dispatch("updated", entity_id, entity_data, old_data)
        # `field_changed` triggers also evaluate against an update —
        # `should_fire` handles the field-comparison branch.
        await _dispatch("field_changed", entity_id, entity_data, old_data)

    async def on_deleted(
        entity_id: str,
        entity_data: dict[str, Any],
        _old: dict[str, Any] | None,
        _op: str,
    ) -> None:
        await _dispatch("deleted", entity_id, entity_data, entity_data)

    return {
        "on_created": on_created,
        "on_updated": on_updated,
        "on_deleted": on_deleted,
    }


# ---------------------------------------------------------------------------
# Wiring (called from server.py)
# ---------------------------------------------------------------------------


def register_job_triggers(
    services: dict[str, Any],
    jobs: list[Any],
    queue: JobQueue,
) -> int:
    """Register trigger callbacks against the matching entity
    services for every `JobSpec` that declares one or more
    triggers.

    Pure-scheduled jobs (no triggers) are skipped — they're
    enqueued by cycle-7's cron scheduler, not entity events.

    Returns:
        Number of (job, trigger) pairs successfully wired.
        Missing services log a warning and skip rather than
        crashing the deploy.
    """
    if not jobs:
        return 0

    wired = 0
    for job in jobs:
        triggers = list(getattr(job, "triggers", []) or [])
        if not triggers:
            continue
        # Group triggers by entity so each service gets one set of
        # callbacks containing only its relevant triggers.
        by_entity: dict[str, list[Any]] = {}
        for trigger in triggers:
            entity_name = getattr(trigger, "entity", "")
            if not entity_name:
                continue
            by_entity.setdefault(entity_name, []).append(trigger)

        for entity_name, entity_triggers in by_entity.items():
            target = services.get(entity_name)
            if target is None:
                logger.warning(
                    "Cannot wire job trigger for %s: service not found",
                    entity_name,
                )
                continue
            callbacks = build_trigger_callbacks(
                job_name=job.name,
                triggers=entity_triggers,
                queue=queue,
            )
            target.on_created(callbacks["on_created"])
            target.on_updated(callbacks["on_updated"])
            target.on_deleted(callbacks["on_deleted"])
            wired += 1

    if wired:
        logger.info(
            "Wired job triggers for %d (job, entity) pair%s",
            wired,
            "" if wired == 1 else "s",
        )
    return wired
