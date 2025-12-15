"""
Dazzle Event-First Architecture.

This package provides the core event infrastructure for Dazzle applications:
- EventEnvelope: Canonical event schema (Kafka-shaped)
- EventBus: Abstract interface for event publish/subscribe
- DevBusMemory: In-memory bus for tests
- DevBrokerSQLite: Zero-Docker SQLite-backed broker for development
- Outbox/Inbox: Transactional guarantees for at-least-once delivery
"""

from dazzle_dnr_back.events.bus import (
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
from dazzle_dnr_back.events.consumer import (
    ConsumerConfig,
    ConsumerGroup,
    ConsumerStats,
    IdempotentConsumer,
    idempotent,
)
from dazzle_dnr_back.events.dev_memory import DevBusMemory
from dazzle_dnr_back.events.dev_sqlite import DevBrokerSQLite
from dazzle_dnr_back.events.envelope import EventEnvelope
from dazzle_dnr_back.events.framework import (
    EventFramework,
    EventFrameworkConfig,
    FrameworkStats,
    get_framework,
    init_framework,
    shutdown_framework,
)
from dazzle_dnr_back.events.inbox import EventInbox, InboxEntry, ProcessingResult
from dazzle_dnr_back.events.outbox import EventOutbox, OutboxEntry, OutboxStatus
from dazzle_dnr_back.events.publisher import OutboxPublisher, PublisherConfig, PublisherStats
from dazzle_dnr_back.events.service_mixin import (
    EventEmittingCRUDService,
    EventEmittingMixin,
)

__all__ = [
    # Envelope
    "EventEnvelope",
    # Bus interface
    "EventBus",
    "EventHandler",
    "SubscriptionInfo",
    "ConsumerStatus",
    "NackReason",
    # Bus implementations
    "DevBusMemory",
    "DevBrokerSQLite",
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
    "get_framework",
    "init_framework",
    "shutdown_framework",
    # Service mixin
    "EventEmittingMixin",
    "EventEmittingCRUDService",
    # Exceptions
    "EventBusError",
    "TopicNotFoundError",
    "ConsumerNotFoundError",
    "EventNotFoundError",
    "PublishError",
    "SubscriptionError",
]
