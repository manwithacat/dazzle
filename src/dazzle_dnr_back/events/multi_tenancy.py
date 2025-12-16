"""
Multi-Tenancy Strategies for Event-First Architecture.

This module provides strategies for handling multi-tenant event streams:

1. SHARED_TOPICS: All tenants share the same topics
   - Tenant isolation via partition keys
   - Simple topology, easier to manage
   - Consumer groups can filter by tenant

2. NAMESPACE_PER_TENANT: Each tenant gets prefixed topics
   - Full tenant isolation at topic level
   - Separate consumer groups per tenant
   - Better for strict compliance requirements

3. HYBRID: Shared internal topics, namespaced external topics
   - Balance of simplicity and isolation
   - Internal events shared, external events isolated

Part of v0.18.0 Event-First Architecture (Issue #25, Phase I).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from dazzle_dnr_back.events.envelope import EventEnvelope

if TYPE_CHECKING:
    from dazzle_dnr_back.events.bus import EventBus

logger = logging.getLogger("dazzle.events.multi_tenancy")


class TenancyMode(str, Enum):
    """Multi-tenancy strategy modes."""

    SHARED_TOPICS = "shared_topics"
    NAMESPACE_PER_TENANT = "namespace_per_tenant"
    HYBRID = "hybrid"


@dataclass
class TenantContext:
    """Current tenant context for event operations."""

    tenant_id: str
    tenant_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required")


class TenancyStrategy(ABC):
    """Abstract base class for multi-tenancy strategies."""

    @property
    @abstractmethod
    def mode(self) -> TenancyMode:
        """Get the tenancy mode."""
        ...

    @abstractmethod
    def get_topic_name(self, base_topic: str, tenant: TenantContext) -> str:
        """
        Get the actual topic name for a tenant.

        Args:
            base_topic: Logical topic name (e.g., "app.orders")
            tenant: Tenant context

        Returns:
            Physical topic name to use
        """
        ...

    @abstractmethod
    def get_consumer_group(self, base_group: str, tenant: TenantContext) -> str:
        """
        Get the consumer group ID for a tenant.

        Args:
            base_group: Logical consumer group (e.g., "order-processor")
            tenant: Tenant context

        Returns:
            Physical consumer group ID to use
        """
        ...

    @abstractmethod
    def get_partition_key(self, base_key: str, tenant: TenantContext) -> str:
        """
        Get the partition key for an event.

        Args:
            base_key: Logical partition key (e.g., order_id)
            tenant: Tenant context

        Returns:
            Physical partition key to use
        """
        ...

    @abstractmethod
    def enrich_envelope(self, envelope: EventEnvelope, tenant: TenantContext) -> EventEnvelope:
        """
        Enrich an event envelope with tenant information.

        Args:
            envelope: Event envelope to enrich
            tenant: Tenant context

        Returns:
            Enriched envelope with tenant metadata
        """
        ...

    @abstractmethod
    def extract_tenant(self, envelope: EventEnvelope) -> TenantContext | None:
        """
        Extract tenant context from an event envelope.

        Args:
            envelope: Event envelope to extract from

        Returns:
            Tenant context if found, None otherwise
        """
        ...

    @abstractmethod
    def validate_access(self, envelope: EventEnvelope, expected_tenant: TenantContext) -> bool:
        """
        Validate that an event belongs to the expected tenant.

        Args:
            envelope: Event envelope to validate
            expected_tenant: Expected tenant context

        Returns:
            True if access is allowed, False otherwise
        """
        ...


class SharedTopicsStrategy(TenancyStrategy):
    """
    Shared topics strategy - all tenants share the same topics.

    Tenant isolation is achieved through:
    - Tenant ID in partition key for ordering within tenant
    - Tenant ID in event headers for filtering
    - Consumer-side tenant validation

    Best for:
    - Simpler infrastructure
    - Moderate tenant count
    - Shared analytics across tenants
    """

    def __init__(
        self,
        partition_key_prefix: bool = True,
        header_key: str = "x-tenant-id",
    ) -> None:
        """
        Initialize the shared topics strategy.

        Args:
            partition_key_prefix: Whether to prefix partition keys with tenant ID
            header_key: Header key for storing tenant ID
        """
        self._partition_key_prefix = partition_key_prefix
        self._header_key = header_key

    @property
    def mode(self) -> TenancyMode:
        return TenancyMode.SHARED_TOPICS

    def get_topic_name(self, base_topic: str, tenant: TenantContext) -> str:
        """Topics are shared - return base topic as-is."""
        return base_topic

    def get_consumer_group(self, base_group: str, tenant: TenantContext) -> str:
        """Consumer groups are shared across tenants."""
        return base_group

    def get_partition_key(self, base_key: str, tenant: TenantContext) -> str:
        """Optionally prefix partition key with tenant ID."""
        if self._partition_key_prefix:
            return f"{tenant.tenant_id}:{base_key}"
        return base_key

    def enrich_envelope(self, envelope: EventEnvelope, tenant: TenantContext) -> EventEnvelope:
        """Add tenant ID to event headers."""
        new_headers = dict(envelope.headers)
        new_headers[self._header_key] = tenant.tenant_id
        if tenant.tenant_name:
            new_headers["x-tenant-name"] = tenant.tenant_name

        return EventEnvelope(
            event_id=envelope.event_id,
            event_type=envelope.event_type,
            event_version=envelope.event_version,
            key=self.get_partition_key(envelope.key, tenant),
            payload=envelope.payload,
            headers=new_headers,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            timestamp=envelope.timestamp,
            producer=envelope.producer,
        )

    def extract_tenant(self, envelope: EventEnvelope) -> TenantContext | None:
        """Extract tenant ID from event headers."""
        tenant_id = envelope.headers.get(self._header_key)
        if not tenant_id:
            return None

        return TenantContext(
            tenant_id=tenant_id,
            tenant_name=envelope.headers.get("x-tenant-name"),
        )

    def validate_access(self, envelope: EventEnvelope, expected_tenant: TenantContext) -> bool:
        """Validate tenant ID matches expected tenant."""
        actual = self.extract_tenant(envelope)
        if not actual:
            return False
        return actual.tenant_id == expected_tenant.tenant_id


class NamespacePerTenantStrategy(TenancyStrategy):
    """
    Namespace per tenant strategy - each tenant gets prefixed topics.

    Tenant isolation is achieved through:
    - Topic names prefixed with tenant ID
    - Separate consumer groups per tenant
    - Physical isolation at Kafka level

    Best for:
    - Strict compliance requirements
    - Independent tenant scaling
    - Strong isolation guarantees
    """

    def __init__(
        self,
        topic_separator: str = ".",
        group_separator: str = "-",
    ) -> None:
        """
        Initialize the namespace per tenant strategy.

        Args:
            topic_separator: Separator between tenant and topic name
            group_separator: Separator between tenant and group name
        """
        self._topic_separator = topic_separator
        self._group_separator = group_separator

    @property
    def mode(self) -> TenancyMode:
        return TenancyMode.NAMESPACE_PER_TENANT

    def get_topic_name(self, base_topic: str, tenant: TenantContext) -> str:
        """Prefix topic with tenant namespace."""
        return f"{tenant.tenant_id}{self._topic_separator}{base_topic}"

    def get_consumer_group(self, base_group: str, tenant: TenantContext) -> str:
        """Prefix consumer group with tenant."""
        return f"{tenant.tenant_id}{self._group_separator}{base_group}"

    def get_partition_key(self, base_key: str, tenant: TenantContext) -> str:
        """Partition key doesn't need tenant prefix - topic is isolated."""
        return base_key

    def enrich_envelope(self, envelope: EventEnvelope, tenant: TenantContext) -> EventEnvelope:
        """Add tenant metadata to headers (for audit/tracing)."""
        new_headers = dict(envelope.headers)
        new_headers["x-tenant-id"] = tenant.tenant_id
        if tenant.tenant_name:
            new_headers["x-tenant-name"] = tenant.tenant_name

        return EventEnvelope(
            event_id=envelope.event_id,
            event_type=envelope.event_type,
            event_version=envelope.event_version,
            key=envelope.key,
            payload=envelope.payload,
            headers=new_headers,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            timestamp=envelope.timestamp,
            producer=envelope.producer,
        )

    def extract_tenant(self, envelope: EventEnvelope) -> TenantContext | None:
        """Extract tenant ID from headers."""
        tenant_id = envelope.headers.get("x-tenant-id")
        if not tenant_id:
            return None

        return TenantContext(
            tenant_id=tenant_id,
            tenant_name=envelope.headers.get("x-tenant-name"),
        )

    def validate_access(self, envelope: EventEnvelope, expected_tenant: TenantContext) -> bool:
        """Validate tenant - should always match since topics are isolated."""
        actual = self.extract_tenant(envelope)
        if not actual:
            # If no tenant in envelope, assume it's the expected tenant
            # (since topic isolation guarantees it)
            return True
        return actual.tenant_id == expected_tenant.tenant_id


class HybridTenancyStrategy(TenancyStrategy):
    """
    Hybrid strategy - shared internal topics, namespaced external topics.

    Internal events (between services in same app) use shared topics.
    External events (to partners, integrations) use per-tenant topics.

    Best for:
    - Balance of simplicity and isolation
    - Partner-facing events need isolation
    - Internal events can be shared
    """

    def __init__(
        self,
        external_prefixes: list[str] | None = None,
        topic_separator: str = ".",
    ) -> None:
        """
        Initialize the hybrid strategy.

        Args:
            external_prefixes: Topic prefixes that are considered external
            topic_separator: Separator for tenant namespace
        """
        self._external_prefixes = external_prefixes or ["external.", "partner.", "api."]
        self._topic_separator = topic_separator
        self._shared_strategy = SharedTopicsStrategy()
        self._namespaced_strategy = NamespacePerTenantStrategy(topic_separator=topic_separator)

    @property
    def mode(self) -> TenancyMode:
        return TenancyMode.HYBRID

    def _is_external(self, topic: str) -> bool:
        """Check if a topic is external."""
        return any(topic.startswith(prefix) for prefix in self._external_prefixes)

    def get_topic_name(self, base_topic: str, tenant: TenantContext) -> str:
        """External topics are namespaced, internal topics are shared."""
        if self._is_external(base_topic):
            return self._namespaced_strategy.get_topic_name(base_topic, tenant)
        return self._shared_strategy.get_topic_name(base_topic, tenant)

    def get_consumer_group(self, base_group: str, tenant: TenantContext) -> str:
        """Consumer groups follow topic pattern."""
        # Determine if this is for an external topic
        # In practice, you'd need more context here
        return base_group

    def get_partition_key(self, base_key: str, tenant: TenantContext) -> str:
        """Internal topics need tenant prefix for ordering."""
        return self._shared_strategy.get_partition_key(base_key, tenant)

    def enrich_envelope(self, envelope: EventEnvelope, tenant: TenantContext) -> EventEnvelope:
        """Enrich with tenant info."""
        return self._shared_strategy.enrich_envelope(envelope, tenant)

    def extract_tenant(self, envelope: EventEnvelope) -> TenantContext | None:
        """Extract tenant from envelope."""
        return self._shared_strategy.extract_tenant(envelope)

    def validate_access(self, envelope: EventEnvelope, expected_tenant: TenantContext) -> bool:
        """Validate tenant access."""
        return self._shared_strategy.validate_access(envelope, expected_tenant)


@dataclass
class TenantEventPublisher:
    """
    Tenant-aware event publisher.

    Wraps an EventBus with multi-tenancy support, ensuring all events
    are properly tagged and routed according to the tenancy strategy.
    """

    bus: EventBus
    strategy: TenancyStrategy
    tenant: TenantContext

    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope,
        *,
        transactional: bool = False,
    ) -> None:
        """
        Publish an event with tenant context.

        Args:
            topic: Logical topic name
            envelope: Event envelope
            transactional: Use transactional outbox
        """
        # Get physical topic name
        physical_topic = self.strategy.get_topic_name(topic, self.tenant)

        # Enrich envelope with tenant info
        enriched = self.strategy.enrich_envelope(envelope, self.tenant)

        # Publish to physical topic
        await self.bus.publish(physical_topic, enriched, transactional=transactional)


@dataclass
class TenantEventConsumer:
    """
    Tenant-aware event consumer.

    Wraps subscription handling with tenant validation, ensuring
    consumers only process events for their tenant.
    """

    bus: EventBus
    strategy: TenancyStrategy
    tenant: TenantContext

    async def subscribe(
        self,
        topic: str,
        group_id: str,
        handler: Any,
    ) -> Any:
        """
        Subscribe to events for this tenant.

        Args:
            topic: Logical topic name
            group_id: Logical consumer group
            handler: Event handler function

        Returns:
            SubscriptionInfo
        """
        # Get physical topic and group
        physical_topic = self.strategy.get_topic_name(topic, self.tenant)
        physical_group = self.strategy.get_consumer_group(group_id, self.tenant)

        # Wrap handler with tenant validation
        async def validated_handler(envelope: EventEnvelope) -> None:
            if not self.strategy.validate_access(envelope, self.tenant):
                logger.warning(f"Rejected event {envelope.event_id} - tenant mismatch")
                return
            await handler(envelope)

        # Subscribe with validated handler
        return await self.bus.subscribe(physical_topic, physical_group, validated_handler)


def create_strategy(mode: TenancyMode, **kwargs: Any) -> TenancyStrategy:
    """
    Factory function to create a tenancy strategy.

    Args:
        mode: Tenancy mode to use
        **kwargs: Strategy-specific configuration

    Returns:
        Configured TenancyStrategy instance
    """
    if mode == TenancyMode.SHARED_TOPICS:
        return SharedTopicsStrategy(**kwargs)
    elif mode == TenancyMode.NAMESPACE_PER_TENANT:
        return NamespacePerTenantStrategy(**kwargs)
    elif mode == TenancyMode.HYBRID:
        return HybridTenancyStrategy(**kwargs)
    else:
        raise ValueError(f"Unknown tenancy mode: {mode}")
