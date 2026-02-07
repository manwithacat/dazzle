"""
Channel manager for DAZZLE messaging runtime.

The ChannelManager is the main entry point for:
- Resolving channels at startup
- Managing outbox processing
- Sending messages through channels
- Providing status for Dazzle Bar

Example:
    manager = ChannelManager(db_manager, channels)
    await manager.initialize()

    # Queue a message for sending
    await manager.send(
        channel="notifications",
        operation="welcome",
        message_type="WelcomeEmail",
        payload={"to": "user@example.com", "subject": "Welcome!"},
        recipient="user@example.com",
    )
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .adapters import (
    FileEmailAdapter,
    InMemoryQueueAdapter,
    InMemoryStreamAdapter,
    KafkaAdapter,
    MailpitAdapter,
    RabbitMQAdapter,
    RedisStreamAdapter,
    SendResult,
)
from .adapters.base import BaseChannelAdapter
from .detection import ProviderStatus
from .outbox import OutboxMessage, OutboxRepository, create_outbox_message
from .resolver import ChannelResolution, ChannelResolver
from .templates import render_template

if TYPE_CHECKING:
    from dazzle.core.ir import ChannelSpec
    from dazzle_back.runtime.repository import DatabaseManager

logger = logging.getLogger("dazzle.channels")


@dataclass
class ChannelStatus:
    """Status of a resolved channel."""

    name: str
    kind: str
    provider_name: str
    status: str
    connection_url: str | None
    management_url: str | None
    detection_method: str
    metadata: dict[str, str] = field(default_factory=dict)
    last_health_check: datetime | None = None
    is_healthy: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "provider_name": self.provider_name,
            "status": self.status,
            "connection_url": self.connection_url,
            "management_url": self.management_url,
            "detection_method": self.detection_method,
            "metadata": self.metadata,
            "last_health_check": self.last_health_check.isoformat()
            if self.last_health_check
            else None,
            "is_healthy": self.is_healthy,
        }


class ChannelManager:
    """
    Manages messaging channels at runtime.

    Handles:
    - Channel resolution and adapter instantiation
    - Message queuing via outbox pattern
    - Background processing of outbox messages
    - Health checking and status reporting
    """

    def __init__(
        self,
        db_manager: DatabaseManager | None,
        channel_specs: list[ChannelSpec],
        *,
        build_id: str | None = None,
    ):
        """
        Initialize the channel manager.

        Args:
            db_manager: Database manager for outbox persistence
            channel_specs: List of channel specifications from DSL
            build_id: Build identifier for message tracking
        """
        self.db_manager = db_manager
        self.channel_specs = channel_specs
        self.build_id = build_id

        self._resolver = ChannelResolver()
        self._outbox: OutboxRepository | None = None
        self._resolutions: dict[str, ChannelResolution] = {}
        self._adapters: dict[str, BaseChannelAdapter] = {}
        self._statuses: dict[str, ChannelStatus] = {}
        self._initialized = False
        self._processor_task: asyncio.Task[None] | None = None

    async def initialize(self) -> None:
        """
        Initialize the channel manager.

        Resolves all channels, creates adapters, and initializes the outbox.
        """
        if self._initialized:
            return

        logger.info("Initializing channel manager...")

        # Initialize outbox if database is available
        if self.db_manager:
            self._outbox = OutboxRepository(self.db_manager)
            logger.info("Outbox repository initialized")

        # Resolve all channels
        for spec in self.channel_specs:
            try:
                resolution = await self._resolver.resolve(spec)
                self._resolutions[spec.name] = resolution

                # Create adapter
                adapter = self._create_adapter(resolution)
                if adapter:
                    await adapter.initialize()
                    self._adapters[spec.name] = adapter

                # Create status
                self._statuses[spec.name] = ChannelStatus(
                    name=spec.name,
                    kind=resolution.channel_kind,
                    provider_name=resolution.provider.provider_name,
                    status=resolution.provider.status.value,
                    connection_url=resolution.provider.connection_url,
                    management_url=resolution.provider.management_url,
                    detection_method=resolution.provider.detection_method,
                    metadata=resolution.provider.metadata,
                    last_health_check=datetime.now(UTC),
                    is_healthy=resolution.provider.status == ProviderStatus.AVAILABLE,
                )

                logger.info(
                    f"Channel '{spec.name}' resolved: {resolution.provider.provider_name} "
                    f"via {resolution.provider.detection_method}"
                )

            except Exception as e:
                logger.error(f"Failed to resolve channel '{spec.name}': {e}")
                self._statuses[spec.name] = ChannelStatus(
                    name=spec.name,
                    kind=spec.kind.value,
                    provider_name="unknown",
                    status="error",
                    connection_url=None,
                    management_url=None,
                    detection_method="failed",
                    metadata={"error": str(e)},
                    is_healthy=False,
                )

        self._initialized = True
        logger.info(f"Channel manager initialized with {len(self._adapters)} adapters")

    def _create_adapter(self, resolution: ChannelResolution) -> BaseChannelAdapter | None:
        """Create an adapter for a channel resolution."""
        adapter_map: dict[str, type[BaseChannelAdapter]] = {
            # Email adapters
            "mailpit": MailpitAdapter,
            "file": FileEmailAdapter,
            # Queue adapters (v0.16.0 - Issue #29)
            "rabbitmq": RabbitMQAdapter,
            "memory_queue": InMemoryQueueAdapter,
            # Stream adapters (v0.16.0 - Issue #29)
            "redis": RedisStreamAdapter,
            "kafka": KafkaAdapter,
            "memory_stream": InMemoryStreamAdapter,
        }

        adapter_class = adapter_map.get(resolution.provider.provider_name)
        if adapter_class:
            return adapter_class(resolution.provider)

        logger.warning(f"No adapter available for provider '{resolution.provider.provider_name}'")
        return None

    async def shutdown(self) -> None:
        """Shutdown the channel manager."""
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass

        for adapter in self._adapters.values():
            try:
                await adapter.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down adapter: {e}")

        self._initialized = False
        logger.info("Channel manager shut down")

    async def send(
        self,
        channel: str,
        operation: str,
        message_type: str,
        payload: dict[str, Any],
        recipient: str,
        *,
        scheduled_for: datetime | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        direct: bool = False,
    ) -> SendResult | OutboxMessage:
        """
        Send a message through a channel.

        By default, uses the outbox pattern for reliability.
        Set direct=True for immediate sending (bypasses outbox).

        Args:
            channel: Channel name
            operation: Operation name from DSL
            message_type: Message type from DSL
            payload: Message payload
            recipient: Primary recipient
            scheduled_for: Optional delayed delivery
            correlation_id: Optional correlation ID
            metadata: Optional metadata
            direct: If True, send immediately without outbox

        Returns:
            SendResult if direct=True, otherwise OutboxMessage
        """
        if not self._initialized:
            raise RuntimeError("Channel manager not initialized")

        if channel not in self._adapters:
            raise ValueError(f"Channel '{channel}' not available")

        if direct:
            # Send immediately
            adapter = self._adapters[channel]
            msg = OutboxMessage(
                id="direct-" + str(datetime.now(UTC).timestamp()),
                channel_name=channel,
                operation_name=operation,
                message_type=message_type,
                payload=payload,
                recipient=recipient,
                build_id=self.build_id,
            )
            return await adapter.send(msg)

        # Queue in outbox
        if not self._outbox:
            raise RuntimeError("Outbox not available - database required for queued sending")

        msg = create_outbox_message(
            channel_name=channel,
            operation_name=operation,
            message_type=message_type,
            payload=payload,
            recipient=recipient,
            scheduled_for=scheduled_for,
            correlation_id=correlation_id,
            build_id=self.build_id,
            metadata=metadata,
        )

        self._outbox.create(msg)
        logger.info(f"Message queued in outbox: {msg.id} for {channel}:{operation}")
        return msg

    async def process_outbox(self, batch_size: int = 10) -> int:
        """
        Process pending outbox messages.

        Args:
            batch_size: Number of messages to process per batch

        Returns:
            Number of messages processed
        """
        if not self._outbox:
            return 0

        pending = self._outbox.get_pending(limit=batch_size)
        processed = 0

        for msg in pending:
            # Try to claim the message
            if not self._outbox.mark_processing(msg.id):
                continue

            adapter = self._adapters.get(msg.channel_name)
            if not adapter:
                self._outbox.mark_failed(msg.id, f"No adapter for channel '{msg.channel_name}'")
                continue

            try:
                result = await adapter.send(msg)

                if result.is_success:
                    self._outbox.mark_sent(msg.id)
                    processed += 1
                else:
                    self._outbox.mark_failed(msg.id, result.error or "Unknown error")

            except Exception as e:
                logger.error(f"Error processing message {msg.id}: {e}")
                self._outbox.mark_failed(msg.id, str(e))

        return processed

    async def start_processor(self, interval: float = 5.0) -> None:
        """
        Start background outbox processor.

        Args:
            interval: Processing interval in seconds
        """
        if self._processor_task:
            return

        async def processor_loop() -> None:
            while True:
                try:
                    processed = await self.process_outbox()
                    if processed > 0:
                        logger.debug(f"Processed {processed} outbox messages")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Outbox processor error: {e}")

                await asyncio.sleep(interval)

        self._processor_task = asyncio.create_task(processor_loop())
        logger.info(f"Outbox processor started (interval: {interval}s)")

    def get_channel_status(self, channel: str) -> ChannelStatus | None:
        """Get status of a specific channel."""
        return self._statuses.get(channel)

    def get_all_statuses(self) -> list[ChannelStatus]:
        """Get status of all channels."""
        return list(self._statuses.values())

    def get_outbox_stats(self) -> dict[str, int]:
        """Get outbox statistics."""
        if not self._outbox:
            return {}
        return self._outbox.get_stats()

    def get_recent_messages(self, limit: int = 20) -> list[OutboxMessage]:
        """Get recent outbox messages for the email panel.

        Args:
            limit: Maximum messages to return

        Returns:
            List of recent messages, newest first
        """
        if not self._outbox:
            return []
        return self._outbox.get_recent(limit)

    async def health_check_all(self) -> dict[str, bool]:
        """Run health checks on all adapters."""
        results = {}
        for name, adapter in self._adapters.items():
            try:
                is_healthy = await adapter.health_check()
                results[name] = is_healthy

                if name in self._statuses:
                    self._statuses[name].is_healthy = is_healthy
                    self._statuses[name].last_health_check = datetime.now(UTC)

            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                results[name] = False

        return results

    def render_message(
        self,
        template: str,
        context: dict[str, Any],
    ) -> str:
        """
        Render a message template.

        Args:
            template: Template string
            context: Template context

        Returns:
            Rendered string
        """
        return render_template(template, context)


# =============================================================================
# Factory Function
# =============================================================================


def create_channel_manager(
    db_manager: DatabaseManager | None,
    channel_specs: list[ChannelSpec],
    build_id: str | None = None,
) -> ChannelManager:
    """
    Create a channel manager instance.

    Args:
        db_manager: Database manager for outbox
        channel_specs: Channel specifications from DSL
        build_id: Build identifier

    Returns:
        ChannelManager instance
    """
    return ChannelManager(
        db_manager=db_manager,
        channel_specs=channel_specs,
        build_id=build_id,
    )
