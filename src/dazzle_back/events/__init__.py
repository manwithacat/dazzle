"""
Dazzle Event-First Architecture.

This package provides the core event infrastructure for Dazzle applications:
- EventEnvelope: Canonical event schema (Kafka-shaped)
- EventBus: Abstract interface for event publish/subscribe
- DevBusMemory: In-memory bus for tests
- DevBrokerSQLite: Zero-Docker SQLite-backed broker for development
- KafkaBus: Production Kafka adapter (v0.18.0 Phase I)
- Outbox/Inbox: Transactional guarantees for at-least-once delivery
- Multi-tenancy strategies (v0.18.0 Phase I)
- Topology drift detection (v0.18.0 Phase I)
"""

from dazzle_back.events.bus import (
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
from dazzle_back.events.consumer import (
    ConsumerConfig,
    ConsumerGroup,
    ConsumerStats,
    IdempotentConsumer,
    idempotent,
)
from dazzle_back.events.dev_memory import DevBusMemory
from dazzle_back.events.dev_sqlite import DevBrokerSQLite
from dazzle_back.events.envelope import EventEnvelope
from dazzle_back.events.framework import (
    EventFramework,
    EventFrameworkConfig,
    FrameworkStats,
    get_framework,
    init_framework,
    shutdown_framework,
)
from dazzle_back.events.inbox import EventInbox, InboxEntry, ProcessingResult

# v0.18.0 Phase I additions
from dazzle_back.events.kafka_bus import (
    KAFKA_AVAILABLE,
    KafkaConfig,
)
from dazzle_back.events.multi_tenancy import (
    HybridTenancyStrategy,
    NamespacePerTenantStrategy,
    SharedTopicsStrategy,
    TenancyMode,
    TenancyStrategy,
    TenantContext,
    TenantEventConsumer,
    TenantEventPublisher,
    create_strategy,
)
from dazzle_back.events.outbox import EventOutbox, OutboxEntry, OutboxStatus

# v0.22.0 - PostgreSQL event bus (Tier 1 - Heroku pilots)
from dazzle_back.events.postgres_bus import (
    ASYNCPG_AVAILABLE,
    PostgresConfig,
)
from dazzle_back.events.publisher import OutboxPublisher, PublisherConfig, PublisherStats

# v0.22.0 - Redis Streams event bus (Tier 2 - Heroku growth)
from dazzle_back.events.redis_bus import (
    REDIS_AVAILABLE,
    RedisConfig,
)
from dazzle_back.events.service_mixin import (
    EventEmittingCRUDService,
    EventEmittingMixin,
)

# v0.22.0 - Tier configuration and factory
from dazzle_back.events.tier import (
    EventTier,
    TierConfig,
    create_bus,
    detect_tier,
    get_tier_info,
)
from dazzle_back.events.topology_drift import (
    DriftIssue,
    DriftReport,
    DriftSeverity,
    DriftType,
    ExpectedConsumer,
    ExpectedTopic,
    ExpectedTopology,
    TopologyDriftDetector,
    TopologyExtractor,
    TopologyFingerprint,
    check_topology_drift,
)

# Conditional import for KafkaBus
if KAFKA_AVAILABLE:
    from dazzle_back.events.kafka_bus import KafkaBus
else:
    KafkaBus = None  # type: ignore[misc,assignment]

# Conditional import for PostgresBus
if ASYNCPG_AVAILABLE:
    from dazzle_back.events.postgres_bus import PostgresBus
else:
    PostgresBus = None  # type: ignore[misc,assignment]

# Conditional import for RedisBus
if REDIS_AVAILABLE:
    from dazzle_back.events.redis_bus import RedisBus
else:
    RedisBus = None  # type: ignore[misc,assignment]

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
    # v0.18.0 Phase I - Kafka adapter
    "KAFKA_AVAILABLE",
    "KafkaBus",
    "KafkaConfig",
    # v0.22.0 - PostgreSQL event bus (Tier 1)
    "ASYNCPG_AVAILABLE",
    "PostgresBus",
    "PostgresConfig",
    # v0.22.0 - Redis Streams event bus (Tier 2)
    "REDIS_AVAILABLE",
    "RedisBus",
    "RedisConfig",
    # v0.22.0 - Tier configuration and factory
    "EventTier",
    "TierConfig",
    "create_bus",
    "detect_tier",
    "get_tier_info",
    # v0.18.0 Phase I - Multi-tenancy
    "TenancyMode",
    "TenancyStrategy",
    "TenantContext",
    "SharedTopicsStrategy",
    "NamespacePerTenantStrategy",
    "HybridTenancyStrategy",
    "TenantEventPublisher",
    "TenantEventConsumer",
    "create_strategy",
    # v0.18.0 Phase I - Topology drift detection
    "DriftType",
    "DriftSeverity",
    "DriftIssue",
    "DriftReport",
    "TopologyFingerprint",
    "ExpectedTopic",
    "ExpectedConsumer",
    "ExpectedTopology",
    "TopologyExtractor",
    "TopologyDriftDetector",
    "check_topology_drift",
]
