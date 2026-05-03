"""Entity-event → notification-dispatch plumbing (#952 cycle 4).

Wires the cycle-1 ``NotificationSpec`` declarations to the cycle-2
:class:`NotificationDispatcher` so a project author's

    notification welcome_email "Welcome":
      on: User created
      channels: [email]
      subject: "Welcome to {{ name }}"
      template: emails/welcome.html
      recipients: field(email)

…dispatches a `welcome_email` notification whenever a User is
created. Mirrors #953 cycle 6's `job_triggers.py` shape and #956
cycle 4's audit-emitter wiring shape so all three primitives plug
into the same `BaseService.on_*` callback infra.

Status-change triggers (``on: Invoice.status -> overdue``) match
when ``status`` field transitions to the named ``to_value``.
Field-change triggers fire when any value of the named field
changes. Created / updated / deleted events match the corresponding
service callback directly.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

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
        trigger: A :class:`NotificationTrigger` IR node — has
            ``event``, optional ``field``, optional ``to_value``.
        event_kind: ``"created"`` / ``"updated"`` / ``"deleted"`` /
            ``"field_changed"`` / ``"status_changed"`` from the
            callback factory.
        old_data: Pre-mutation field values (``None`` for create).
        new_data: Post-mutation field values (``None`` for delete).

    Returns:
        True when the trigger should fire — caller then dispatches
        via the cycle-2 :class:`NotificationDispatcher`. False
        short-circuits without a dispatch.
    """
    trigger_event = (getattr(trigger, "event", "") or "").lower()
    trigger_field = (getattr(trigger, "field", None) or "").strip()
    to_value = (getattr(trigger, "to_value", None) or "").strip()

    if trigger_event == "field_changed":
        if event_kind != "field_changed":
            return False
        if not trigger_field:
            return False
        if old_data is None or new_data is None:
            return False
        return old_data.get(trigger_field) != new_data.get(trigger_field)

    if trigger_event == "status_changed":
        if event_kind != "field_changed":
            return False
        # `status_changed` is a specialisation of `field_changed`
        # over a `field` (default `"status"`) with an optional
        # `to_value` filter.
        field_name = trigger_field or "status"
        if old_data is None or new_data is None:
            return False
        new_value = new_data.get(field_name)
        old_value = old_data.get(field_name)
        if old_value == new_value:
            return False
        if to_value:
            return str(new_value) == to_value
        return True

    return trigger_event == event_kind


# ---------------------------------------------------------------------------
# Callback factory
# ---------------------------------------------------------------------------


def build_trigger_callbacks(
    *,
    spec: Any,  # NotificationSpec
    dispatcher: Any,  # NotificationDispatcher
) -> dict[str, Callable[..., Awaitable[None]]]:
    """Build on_created / on_updated / on_deleted callbacks for one
    notification spec.

    Each callback asks `should_fire` and dispatches via the cycle-2
    dispatcher when the trigger matches. Failures inside `dispatch`
    are swallowed + logged — a single notification failure must not
    break the user's mutation. Cycle 5 will route the dispatch through
    the queue + retry pipeline.
    """

    async def _safe_dispatch(payload: dict[str, Any]) -> None:
        try:
            dispatcher.dispatch(spec, payload)
        except Exception:
            logger.warning(
                "Notification dispatch failed for %s — continuing",
                getattr(spec, "name", "<unknown>"),
                exc_info=True,
            )

    trigger = getattr(spec, "trigger", None)

    async def _maybe(
        event_kind: str,
        entity_id: str,
        new_data: dict[str, Any] | None,
        old_data: dict[str, Any] | None,
    ) -> None:
        if trigger is None:
            return
        if not should_fire(
            trigger,
            event_kind=event_kind,
            old_data=old_data,
            new_data=new_data,
        ):
            return
        payload = dict(new_data or old_data or {})
        # Surface entity_id consistently in the rendered payload so
        # template authors can ${entity_id}-link without juggling row
        # vs id sources.
        payload.setdefault("entity_id", entity_id)
        await _safe_dispatch(payload)

    async def on_created(
        entity_id: str,
        entity_data: dict[str, Any],
        _old: dict[str, Any] | None,
        _op: str,
    ) -> None:
        await _maybe("created", entity_id, entity_data, None)

    async def on_updated(
        entity_id: str,
        entity_data: dict[str, Any],
        old_data: dict[str, Any] | None,
        _op: str,
    ) -> None:
        await _maybe("updated", entity_id, entity_data, old_data)
        # `field_changed` + `status_changed` triggers also evaluate
        # against an update — `should_fire` handles the field
        # comparison branches.
        await _maybe("field_changed", entity_id, entity_data, old_data)

    async def on_deleted(
        entity_id: str,
        entity_data: dict[str, Any],
        _old: dict[str, Any] | None,
        _op: str,
    ) -> None:
        await _maybe("deleted", entity_id, entity_data, entity_data)

    return {
        "on_created": on_created,
        "on_updated": on_updated,
        "on_deleted": on_deleted,
    }


# ---------------------------------------------------------------------------
# Wiring (called from server.py)
# ---------------------------------------------------------------------------


def register_notification_triggers(
    services: dict[str, Any],
    notifications: list[Any],
    dispatcher: Any,  # NotificationDispatcher
) -> int:
    """Register dispatch callbacks against the matching entity
    service for every :class:`NotificationSpec` that declares a
    trigger.

    Notifications without a trigger entity are skipped — they're
    invoked manually from project code (e.g. the password-reset
    flow which fires its own dispatch when the reset link is
    requested).

    Returns:
        Number of (notification, entity) pairs successfully wired.
        Missing services log a warning and skip rather than crashing
        the deploy — same fail-safe pattern as ``register_job_triggers``.
    """
    if not notifications:
        return 0

    wired = 0
    for spec in notifications:
        trigger = getattr(spec, "trigger", None)
        if trigger is None:
            continue
        entity_name = getattr(trigger, "entity", "")
        if not entity_name:
            continue
        target = services.get(entity_name)
        if target is None:
            logger.warning(
                "Cannot wire notification %s: service for %s not found",
                getattr(spec, "name", "<unknown>"),
                entity_name,
            )
            continue
        callbacks = build_trigger_callbacks(spec=spec, dispatcher=dispatcher)
        target.on_created(callbacks["on_created"])
        target.on_updated(callbacks["on_updated"])
        target.on_deleted(callbacks["on_deleted"])
        wired += 1

    if wired:
        logger.info(
            "Wired notification triggers for %d (notification, entity) pair%s",
            wired,
            "" if wired == 1 else "s",
        )
    return wired
