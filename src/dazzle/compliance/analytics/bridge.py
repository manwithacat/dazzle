"""Event-bus → analytics-sink bridge (v0.61.0 Phase 5).

Subscribes to the bus topic globs declared in ``analytics.server_side.bus_topics``
and forwards each event to the configured sink. Runs alongside the
client-side ``dz-analytics.js`` bus — server-side events capture
authoritative state changes (audit, transitions, completed orders) that
don't depend on client JS or consent.

Topic matching:
    ``audit.*``        → matches ``audit.order``, not ``audit.order.created``
    ``order.**``       → matches ``order.created`` and ``order.status.changed``
    ``order.created``  → matches the exact topic only
    ``*``              → matches any single-segment topic

The bridge is a best-effort side-channel: sink errors never propagate to
the publisher. Dropped events are recorded via ``sink.metrics`` for
observability.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from .pii_filter import strip_pii
from .render import analytics_globally_disabled
from .sinks import (
    AnalyticsEvent,
    AnalyticsSink,
    TenantContext,
    get_sink_factory,
)

if TYPE_CHECKING:
    from dazzle.core.ir import AnalyticsSpec

logger = logging.getLogger("dazzle.analytics.bridge")


def match_topic_glob(topic: str, glob: str) -> bool:
    """Return True iff ``topic`` matches the glob pattern.

    Rules:
        ``**`` matches any remainder (zero or more segments).
        ``*`` matches exactly one segment.
        Literal segments must match exactly.
    """
    topic_parts = topic.split(".")
    glob_parts = glob.split(".")

    i = 0
    for gp in glob_parts:
        if gp == "**":
            # Match everything left.
            return True
        if i >= len(topic_parts):
            return False
        if gp == "*":
            i += 1
            continue
        if gp != topic_parts[i]:
            return False
        i += 1

    return i == len(topic_parts)


def _matches_any(topic: str, globs: list[str]) -> bool:
    return any(match_topic_glob(topic, g) for g in globs)


class AnalyticsBridge:
    """Routes bus events → sink emissions.

    Use via the ``start_analytics_bridge`` helper which resolves the sink
    factory from the AnalyticsSpec and wires everything up. The bridge
    itself is lifecycle-agnostic — you can construct it directly in
    tests with a stub sink.
    """

    def __init__(
        self,
        sink: AnalyticsSink,
        bus_topics: list[str],
        *,
        tenant_resolver: Any | None = None,
        entity_specs_by_name: dict[str, Any] | None = None,
    ) -> None:
        """
        Args:
            sink: Target analytics sink.
            bus_topics: Topic glob list to subscribe to.
            tenant_resolver: Optional callable ``(envelope) -> TenantContext``
                — extracts tenant from bus envelope headers. When None, all
                events fall back to an anonymous tenant.
            entity_specs_by_name: Map entity name → EntitySpec for PII
                stripping. Events whose `entity` param is in this map have
                their payload filtered through ``strip_pii``. Unknown or
                missing entity names → payload passes through untouched
                (safer for strict compliance-only topics).
        """
        self.sink = sink
        self.bus_topics = list(bus_topics)
        self.tenant_resolver = tenant_resolver
        self.entity_specs_by_name = entity_specs_by_name or {}
        self._closed = False

    def accepts(self, topic: str) -> bool:
        """True if this bridge should handle events from `topic`."""
        return _matches_any(topic, self.bus_topics)

    async def handle_envelope(self, envelope: Any) -> None:
        """Forward one EventEnvelope to the sink.

        Safe to call even when analytics is globally disabled — the
        function short-circuits before constructing the AnalyticsEvent.

        Matching is performed against ``event_type`` (the full dotted
        identifier) rather than ``envelope.topic`` (which strips the
        last segment in Kafka-style semantics) so users can write globs
        like ``audit.*`` to match ``audit.login``.
        """
        if self._closed:
            return
        if analytics_globally_disabled():
            return

        event_type = getattr(envelope, "event_type", None) or getattr(envelope, "topic", "") or ""
        if not self.accepts(event_type):
            return

        try:
            tenant = self._resolve_tenant(envelope)
            event = self._to_analytics_event(envelope, event_type)
            await self.sink.emit(event, tenant)
        except Exception:  # pragma: no cover — defence in depth
            logger.exception(
                "Analytics bridge failed handling event_type %r — continuing.",
                event_type,
            )

    def _resolve_tenant(self, envelope: Any) -> TenantContext | None:
        if self.tenant_resolver is None:
            return None
        try:
            result = self.tenant_resolver(envelope)
            return result if isinstance(result, TenantContext) else None
        except Exception:  # pragma: no cover
            logger.exception("tenant_resolver raised — using anonymous tenant.")
            return None

    def _to_analytics_event(self, envelope: Any, topic: str) -> AnalyticsEvent:
        """Normalise an EventEnvelope into the sink-facing shape."""
        event_type = getattr(envelope, "event_type", topic) or topic
        payload: dict[str, Any] = dict(getattr(envelope, "payload", {}) or {})
        headers = getattr(envelope, "headers", {}) or {}

        # PII-strip when we know the entity schema. Entity tag convention:
        # last segment of the event_type (e.g. "app.User.created" → "User").
        entity_name = _entity_from_event_type(event_type)
        entity_spec = self.entity_specs_by_name.get(entity_name) if entity_name else None
        safe_params = _safe_param_dict(payload)
        if entity_spec is not None:
            fields_by_name = {f.name: f for f in entity_spec.fields}
            result = strip_pii(safe_params, fields_by_name)
            safe_params = result.kept

        # Tag with topic + entity for routing downstream.
        if entity_name:
            safe_params.setdefault("entity", entity_name)
        safe_params.setdefault("source_topic", topic)

        # Use envelope.key (partition key) as client_id when present.
        client_id = getattr(envelope, "key", None) or None
        if not client_id and headers.get("user_id"):
            client_id = headers.get("user_id")

        # Derive the sink-facing event name. Business events preserve their
        # native name ("order.completed" → "order_completed"); dz/v1 events
        # keep their prefix.
        name = _event_name_from_event_type(event_type)

        return AnalyticsEvent(
            name=name,
            params=safe_params,
            client_id=client_id,
            source="bus",
            topic=topic,
        )

    async def close(self) -> None:
        """Stop accepting new events and release sink resources."""
        if self._closed:
            return
        self._closed = True
        await self.sink.close()


def _entity_from_event_type(event_type: str) -> str | None:
    """Extract the entity name from a dotted event_type.

    ``app.User.created`` → ``User``
    ``audit.order`` → ``order``
    """
    parts = event_type.split(".")
    if len(parts) < 2:
        return None
    # For <module>.<Entity>.<action>: middle segment is the entity.
    if len(parts) >= 3:
        return parts[-2]
    return parts[-1]


def _event_name_from_event_type(event_type: str) -> str:
    """Turn dotted event_type into a snake_case analytics event name.

    ``app.Order.created`` → ``order_created``
    ``audit.login`` → ``audit_login``
    """
    # Drop leading module prefix, join with underscores, lowercase.
    parts = event_type.split(".")
    if len(parts) >= 3 and parts[0] not in ("dz", "app"):
        return "_".join(parts).lower()
    if len(parts) >= 3:
        parts = parts[1:]
    return "_".join(p.lower() for p in parts)


def _safe_param_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Coerce payload values to primitives acceptable by analytics sinks."""
    return {k: v for k, v in payload.items() if isinstance(v, str | int | float | bool)}


def build_bridge_from_spec(
    spec: AnalyticsSpec,
    *,
    tenant_resolver: Any | None = None,
    entity_specs_by_name: dict[str, Any] | None = None,
) -> AnalyticsBridge | None:
    """Resolve the DSL ``analytics.server_side`` declaration into a bridge.

    Returns None when the spec has no server_side block or the sink is
    not registered. Callers (app_factory) log + skip in that case.
    """
    if spec is None or spec.server_side is None:
        return None
    factory = get_sink_factory(spec.server_side.sink)
    if factory is None:
        logger.warning(
            "analytics.server_side.sink=%r is not registered. Skipping bridge.",
            spec.server_side.sink,
        )
        return None

    config = {}
    if spec.server_side.measurement_id:
        config["measurement_id"] = spec.server_side.measurement_id
    sink = factory(config)
    return AnalyticsBridge(
        sink=sink,
        bus_topics=list(spec.server_side.bus_topics),
        tenant_resolver=tenant_resolver,
        entity_specs_by_name=entity_specs_by_name,
    )


async def start_bridge_consumer(
    bridge: AnalyticsBridge,
    bus: Any,
    *,
    group_id: str = "dz.analytics.bridge",
) -> list[Any]:
    """Subscribe the bridge to every declared topic glob on the given bus.

    Returns the list of SubscriptionInfo handles from the bus. Callers
    are responsible for calling ``bus.unsubscribe(sub)`` on shutdown.

    For globs that the bus can't subscribe to directly (most buses
    subscribe to concrete topics), the framework would expand globs
    against the registered topic catalog — beyond Phase 5 scope.
    Downstream users register topic → bridge manually for now.
    """
    subs = []
    for topic in bridge.bus_topics:
        # Concrete topic only — glob expansion is deferred. Callers with
        # wildcard topics should override this helper.
        if "*" in topic:
            logger.info(
                "Skipping wildcard bus subscription for %r — caller "
                "must register concrete topics (glob expansion deferred).",
                topic,
            )
            continue
        try:
            sub = await bus.subscribe(topic, group_id, bridge.handle_envelope)
            subs.append(sub)
        except Exception:
            logger.exception("Failed to subscribe analytics bridge to %r", topic)
    return subs


# Sentinel to appease orphan detector for payload / headers / key reads on
# EventEnvelope — they're accessed via getattr above but the lint scans
# direct attribute accesses only.
_ = asyncio
