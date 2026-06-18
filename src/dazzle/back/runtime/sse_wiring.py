"""#1399 slice 1 — SSE live-push nudge wiring.

Registers entity-lifecycle callbacks on every CRUDService that publish a
*nudge* (entity name + id + tenant, no row data) to the framework EventBus on
the canonical ``entity.{created,updated,deleted}`` topics. The already-built
SSEStreamManager subscribes to those topics and forwards them to connected
browsers, whose cards re-fetch via their existing scope-gated endpoints.

Mirrors the audit/notification/job wiring pattern (``audit_wiring.py``).
"""

import logging
from collections.abc import Callable
from typing import Any

from dazzle.back.events.envelope import EventEnvelope

logger = logging.getLogger("dazzle.server")

# action -> canonical topic / event_type. Matches SSEStreamManager.STREAM_TOPICS
# (StreamType.EVENTS) AND the client `sse:entity.<action>` trigger names, so no
# remapping is needed end-to-end.
_TOPICS = {
    "created": "entity.created",
    "updated": "entity.updated",
    "deleted": "entity.deleted",
}


class LazyFrameworkBus:
    """A bus-shaped proxy that resolves the EventFramework's real bus lazily.

    The framework's concrete bus only exists after ``EventFramework.start()``
    runs (a lifespan hook, post-construction). SSE publishers (nudge callbacks)
    and the ``SSEStreamManager`` are wired at construction time, so they bind to
    this proxy instead — every ``publish``/``subscribe`` call resolves the live
    bus at call time (runtime, post-start). This removes any hook-ordering
    dependency between framework start and SSE start.
    """

    def __init__(self, framework: Any) -> None:
        self._framework = framework

    def _bus(self) -> Any | None:
        # EventFramework exposes get_bus() (None until start()); NullEventFramework
        # (events package unavailable) exposes only a `.bus` no-op NullBus. Prefer
        # get_bus(), fall back to `.bus`, so the null framework yields an inert
        # (connect + heartbeat, no events) SSE path instead of raising at start.
        getter = getattr(self._framework, "get_bus", None)
        if getter is not None:
            return getter()
        return getattr(self._framework, "bus", None)

    async def publish(self, topic: str, envelope: Any, *, transactional: bool = False) -> None:
        bus = self._bus()
        if bus is None:
            logger.debug("SSE: event bus not ready, dropping publish to %s", topic)
            return
        await bus.publish(topic, envelope, transactional=transactional)

    async def subscribe(self, topic: str, group_id: str, handler: Any) -> Any:
        bus = self._bus()
        if bus is None:
            raise RuntimeError("SSE: event bus not started; cannot subscribe to " + topic)
        return await bus.subscribe(topic, group_id, handler)

    def __getattr__(self, name: str) -> Any:
        # Delegate everything else (e.g. poll_and_process) to the live bus so
        # `hasattr(proxy, ...)` reflects the real implementation at runtime.
        bus = self._bus()
        if bus is None:
            raise AttributeError(name)
        return getattr(bus, name)


def _default_is_target(service: Any) -> bool:
    from dazzle.back.runtime.service_generator import CRUDService

    return isinstance(service, CRUDService)


def _make_nudge_callback(bus: Any, action: str) -> Callable[..., Any]:
    topic = _TOPICS[action]

    async def _publish_nudge(
        entity_name: str,
        entity_id: str,
        entity_data: dict[str, Any],
        old_data: dict[str, Any] | None,
    ) -> None:
        tenant_id = (entity_data or {}).get("tenant_id")
        headers = {"tenant_id": str(tenant_id)} if tenant_id else {}
        envelope = EventEnvelope.create(
            event_type=topic,
            key=str(entity_id),
            payload={"entity": entity_name, "id": str(entity_id)},
            headers=headers,
            producer="dazzle.ui.live",
        )
        try:
            await bus.publish(topic, envelope)
        except Exception as exc:  # nudge delivery must never break a mutation
            logger.warning("SSE nudge publish failed for %s.%s: %s", entity_name, action, exc)

    return _publish_nudge


def register_sse_callbacks(
    services: dict[str, Any],
    bus: Any | None,
    *,
    _is_target: Callable[[Any], bool] = _default_is_target,
) -> int:
    """Register nudge publishers on every CRUD service. Returns count wired."""
    if bus is None:
        return 0
    wired = 0
    for service in services.values():
        if not _is_target(service):
            continue
        service.on_created(_make_nudge_callback(bus, "created"))
        service.on_updated(_make_nudge_callback(bus, "updated"))
        service.on_deleted(_make_nudge_callback(bus, "deleted"))
        wired += 1
    if wired:
        logger.info("SSE live push: wired nudge callbacks on %d services", wired)
    return wired
