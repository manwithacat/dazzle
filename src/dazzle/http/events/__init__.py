"""
Dazzle Event-First Architecture.

This package provides the core event infrastructure for Dazzle applications:
- EventEnvelope: Canonical event schema
- EventBus: Abstract interface for event publish/subscribe
- RedisBus: the production tier (``NullBus`` when ``REDIS_URL`` is unset)
- Outbox/Inbox: Transactional guarantees for at-least-once delivery

The event DSL (``event_model``, ``subscribe``, ``projection``, ``stream``,
``hless``, ``ingest``), the Kafka tier (flense ship F) and the PostgreSQL and
in-memory tiers (flense ship AR) are parked under DD-006.
"""

# --- Zero-dep imports (always available) ---
from dazzle.http.events.bus import (
    ConsumerNotFoundError,
    ConsumerStatus,
    EventBus,
    EventBusError,
    EventHandler,
    EventNotFoundError,
    NackReason,
    PublishError,
    SubscriptionError,
    SubscriptionInfo,
    TopicNotFoundError,
)
from dazzle.http.events.envelope import EventEnvelope
from dazzle.http.events.null import EVENTS_AVAILABLE, NullBus, NullEventFramework

# --- Heavy imports (require psycopg and other extras) ---
if EVENTS_AVAILABLE:
    from dazzle.http.events.base_event_bus import BaseEventBus
    from dazzle.http.events.consumer import (
        ConsumerConfig,
        ConsumerGroup,
        ConsumerStats,
        IdempotentConsumer,
        idempotent,
    )
    from dazzle.http.events.framework import (
        EventFramework,
        EventFrameworkConfig,
        FrameworkStats,
    )
    from dazzle.http.events.inbox import EventInbox, InboxEntry, ProcessingResult
    from dazzle.http.events.outbox import EventOutbox, OutboxEntry, OutboxStatus
    from dazzle.http.events.publisher import OutboxPublisher, PublisherConfig, PublisherStats

    # v0.22.0 - Redis Streams event bus (the production tier)
    from dazzle.http.events.redis_bus import (
        REDIS_AVAILABLE,
        RedisConfig,
    )

    # v0.22.0 - Tier configuration and factory
    from dazzle.http.events.tier import (
        EventTier,
        TierConfig,
        create_bus,
        detect_tier,
        get_tier_info,
    )

    # Conditional import for RedisBus
    if REDIS_AVAILABLE:
        from dazzle.http.events.redis_bus import RedisBus
    else:
        RedisBus = None  # type: ignore[misc,assignment]

# --- Build __all__ dynamically ---
__all__ = [
    # Envelope
    "EventEnvelope",
    # Bus interface
    "EventBus",
    "EventHandler",
    "SubscriptionInfo",
    "ConsumerStatus",
    "NackReason",
    # Null implementations
    "NullBus",
    "NullEventFramework",
    "EVENTS_AVAILABLE",
    # Exceptions
    "EventBusError",
    "TopicNotFoundError",
    "ConsumerNotFoundError",
    "EventNotFoundError",
    "PublishError",
    "SubscriptionError",
]

if EVENTS_AVAILABLE:
    __all__ += [
        # Bus implementations
        "BaseEventBus",
        # Outbox (transactional publishing)
        "EventOutbox",
        "OutboxEntry",
        "OutboxStatus",
        "OutboxPublisher",
        "PublisherConfig",
        "PublisherStats",
        # Inbox (idempotent consumption)
        "EventInbox",
        "InboxEntry",
        "ProcessingResult",
        # Consumer wrapper
        "IdempotentConsumer",
        "ConsumerConfig",
        "ConsumerStats",
        "ConsumerGroup",
        "idempotent",
        # Framework
        "EventFramework",
        "EventFrameworkConfig",
        "FrameworkStats",
        # Redis Streams event bus (the production tier)
        "REDIS_AVAILABLE",
        "RedisBus",
        "RedisConfig",
        # v0.22.0 - Tier configuration and factory
        "EventTier",
        "TierConfig",
        "create_bus",
        "detect_tier",
        "get_tier_info",
    ]
