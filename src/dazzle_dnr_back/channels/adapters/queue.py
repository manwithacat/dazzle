"""
Queue channel adapters for DAZZLE messaging.

Provides adapters for:
- RabbitMQ (production)
- In-memory queue (development/testing fallback)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any, ClassVar

from .base import QueueAdapter, SendResult, SendStatus

if TYPE_CHECKING:
    from ..detection import DetectionResult
    from ..outbox import OutboxMessage

logger = logging.getLogger("dazzle.channels.adapters.queue")


class RabbitMQAdapter(QueueAdapter):
    """Adapter for RabbitMQ message queue.

    Uses aio-pika for async AMQP communication.
    Requires: pip install aio-pika
    """

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)
        self._url = detection_result.connection_url or "amqp://localhost:5672"
        self._connection: Any = None
        self._channel: Any = None
        self._declared_queues: set[str] = set()
        self._pending_acks: dict[str, Any] = {}

    @property
    def provider_name(self) -> str:
        return "rabbitmq"

    async def initialize(self) -> None:
        """Initialize RabbitMQ connection."""
        try:
            import aio_pika

            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = await self._connection.channel()
            await super().initialize()
            logger.info(f"RabbitMQ adapter initialized ({self._url})")

        except ImportError:
            raise ImportError(
                "aio-pika is required for RabbitMQ support. "
                "Install it with: pip install 'dazzle[rabbitmq]'"
            )
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise

    async def shutdown(self) -> None:
        """Close RabbitMQ connection."""
        if self._connection:
            try:
                await self._connection.close()
            except Exception as e:
                logger.warning(f"Error closing RabbitMQ connection: {e}")
        self._connection = None
        self._channel = None
        self._declared_queues.clear()
        await super().shutdown()
        logger.info("RabbitMQ adapter shut down")

    async def _ensure_queue(self, queue_name: str) -> None:
        """Ensure queue exists."""
        if queue_name not in self._declared_queues:
            await self._channel.declare_queue(queue_name, durable=True)
            self._declared_queues.add(queue_name)

    async def send(self, message: OutboxMessage) -> SendResult:
        """Send message to RabbitMQ queue.

        Args:
            message: Outbox message to send

        Returns:
            SendResult with status
        """
        if not self._channel:
            return SendResult(
                status=SendStatus.FAILED,
                error="RabbitMQ channel not initialized",
            )

        try:
            import aio_pika

            start = time.monotonic()

            # Ensure queue exists
            await self._ensure_queue(message.channel_name)

            # Build message
            body = json.dumps({
                "id": message.id,
                "operation": message.operation_name,
                "type": message.message_type,
                "payload": message.payload,
                "recipient": message.recipient,
                "correlation_id": message.correlation_id,
                "metadata": message.metadata,
            }).encode()

            amqp_message = aio_pika.Message(
                body=body,
                content_type="application/json",
                message_id=message.id,
                correlation_id=message.correlation_id,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )

            # Publish to queue
            await self._channel.default_exchange.publish(
                amqp_message,
                routing_key=message.channel_name,
            )

            latency = (time.monotonic() - start) * 1000

            logger.info(f"Message sent to RabbitMQ queue '{message.channel_name}': {message.id}")

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=message.id,
                latency_ms=latency,
                provider_response={
                    "queue": message.channel_name,
                    "routing_key": message.channel_name,
                },
            )

        except Exception as e:
            logger.error(f"RabbitMQ send error: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )

    async def receive(self, count: int = 1, timeout: float = 30.0) -> list[dict[str, Any]]:
        """Receive messages from RabbitMQ queue.

        Args:
            count: Maximum messages to receive
            timeout: Wait timeout in seconds

        Returns:
            List of received messages
        """
        if not self._channel:
            return []

        messages: list[dict[str, Any]] = []
        try:
            queue = await self._channel.get_queue(self.detection_result.metadata.get("queue_name", "default"))

            async with asyncio.timeout(timeout):
                async for incoming in queue.iterator():
                    body = json.loads(incoming.body.decode())
                    body["_delivery_tag"] = incoming.delivery_tag
                    messages.append(body)
                    self._pending_acks[body.get("id", str(incoming.delivery_tag))] = incoming

                    if len(messages) >= count:
                        break

        except TimeoutError:
            pass
        except Exception as e:
            logger.error(f"RabbitMQ receive error: {e}")

        return messages

    async def ack(self, message_id: str) -> None:
        """Acknowledge a message.

        Args:
            message_id: ID of message to acknowledge
        """
        if message_id in self._pending_acks:
            msg = self._pending_acks.pop(message_id)
            await msg.ack()
            logger.debug(f"Message acknowledged: {message_id}")

    async def nack(self, message_id: str, requeue: bool = True) -> None:
        """Negative acknowledge a message.

        Args:
            message_id: ID of message to nack
            requeue: Whether to requeue the message
        """
        if message_id in self._pending_acks:
            msg = self._pending_acks.pop(message_id)
            await msg.nack(requeue=requeue)
            logger.debug(f"Message nacked (requeue={requeue}): {message_id}")

    async def health_check(self) -> bool:
        """Check if RabbitMQ is accessible."""
        if not self._connection:
            return False

        try:
            return not self._connection.is_closed
        except Exception:
            return False


class InMemoryQueueAdapter(QueueAdapter):
    """In-memory queue adapter for development/testing.

    Queues are stored in memory and shared across all instances.
    Data is lost on process restart.
    """

    # Class-level shared queues
    _queues: ClassVar[dict[str, asyncio.Queue[dict[str, Any]]]] = {}
    _pending: ClassVar[dict[str, dict[str, Any]]] = {}
    _lock: ClassVar[asyncio.Lock | None] = None

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Get or create the class lock."""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @property
    def provider_name(self) -> str:
        return "memory_queue"

    async def initialize(self) -> None:
        """Initialize in-memory queue adapter."""
        await super().initialize()
        logger.info("In-memory queue adapter initialized")

    async def shutdown(self) -> None:
        """Shutdown in-memory queue adapter."""
        await super().shutdown()
        logger.info("In-memory queue adapter shut down")

    @classmethod
    def _get_queue(cls, name: str) -> asyncio.Queue[dict[str, Any]]:
        """Get or create a queue by name."""
        if name not in cls._queues:
            cls._queues[name] = asyncio.Queue()
        return cls._queues[name]

    async def send(self, message: OutboxMessage) -> SendResult:
        """Send message to in-memory queue.

        Args:
            message: Outbox message to send

        Returns:
            SendResult with status
        """
        try:
            start = time.monotonic()

            queue = self._get_queue(message.channel_name)

            msg_data = {
                "id": message.id,
                "operation": message.operation_name,
                "type": message.message_type,
                "payload": message.payload,
                "recipient": message.recipient,
                "correlation_id": message.correlation_id,
                "metadata": message.metadata,
            }

            await queue.put(msg_data)

            latency = (time.monotonic() - start) * 1000

            logger.info(f"Message sent to in-memory queue '{message.channel_name}': {message.id}")

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=message.id,
                latency_ms=latency,
                provider_response={
                    "queue": message.channel_name,
                    "queue_size": queue.qsize(),
                },
            )

        except Exception as e:
            logger.error(f"In-memory queue send error: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )

    async def receive(self, count: int = 1, timeout: float = 30.0) -> list[dict[str, Any]]:
        """Receive messages from in-memory queue.

        Args:
            count: Maximum messages to receive
            timeout: Wait timeout in seconds

        Returns:
            List of received messages
        """
        queue_name = self.detection_result.metadata.get("queue_name", "default")
        queue = self._get_queue(queue_name)
        messages: list[dict[str, Any]] = []

        try:
            async with asyncio.timeout(timeout):
                while len(messages) < count:
                    msg = await queue.get()
                    messages.append(msg)
                    # Store for ack/nack
                    async with self._get_lock():
                        self._pending[msg["id"]] = msg

        except TimeoutError:
            pass
        except Exception as e:
            logger.error(f"In-memory queue receive error: {e}")

        return messages

    async def ack(self, message_id: str) -> None:
        """Acknowledge a message.

        Args:
            message_id: ID of message to acknowledge
        """
        async with self._get_lock():
            if message_id in self._pending:
                del self._pending[message_id]
                logger.debug(f"Message acknowledged: {message_id}")

    async def nack(self, message_id: str, requeue: bool = True) -> None:
        """Negative acknowledge a message.

        Args:
            message_id: ID of message to nack
            requeue: Whether to requeue the message
        """
        async with self._get_lock():
            if message_id in self._pending:
                msg = self._pending.pop(message_id)
                if requeue:
                    queue_name = msg.get("channel_name", "default")
                    queue = self._get_queue(queue_name)
                    await queue.put(msg)
                logger.debug(f"Message nacked (requeue={requeue}): {message_id}")

    async def health_check(self) -> bool:
        """In-memory queue is always healthy."""
        return True

    @classmethod
    def clear_all(cls) -> None:
        """Clear all queues (for testing)."""
        cls._queues.clear()
        cls._pending.clear()

    @classmethod
    def get_queue_size(cls, name: str) -> int:
        """Get size of a queue (for testing)."""
        if name in cls._queues:
            return cls._queues[name].qsize()
        return 0
