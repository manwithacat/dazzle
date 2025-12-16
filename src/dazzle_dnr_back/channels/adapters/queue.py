"""
Queue channel adapters for DAZZLE messaging.

Provides adapters for:
- RabbitMQ (production queue)
- In-memory queue (fallback, development)
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
    """Adapter for RabbitMQ queue.

    Sends messages to RabbitMQ queues using aio-pika.
    Perfect for production message queuing with delivery guarantees.
    """

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)
        self._url = detection_result.connection_url or "amqp://localhost:5672"
        self._connection = None
        self._channel = None

    @property
    def provider_name(self) -> str:
        return "rabbitmq"

    async def initialize(self) -> None:
        """Initialize the RabbitMQ connection."""
        await super().initialize()

        try:
            import aio_pika

            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = await self._connection.channel()
            logger.info(f"RabbitMQ adapter initialized (url: {self._url})")

        except ImportError:
            logger.error("aio-pika not installed. Install with: pip install aio-pika")
            raise RuntimeError(
                "aio-pika is required for RabbitMQ adapter. "
                "Install with: pip install 'dazzle[rabbitmq]'"
            )
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown the RabbitMQ connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._channel = None
        await super().shutdown()

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
                error="RabbitMQ adapter not initialized",
            )

        try:
            import aio_pika

            start = time.monotonic()

            # Declare queue (idempotent)
            queue = await self._channel.declare_queue(
                message.channel_name,
                durable=True,
            )

            # Prepare message
            message_body = json.dumps(message.payload).encode()
            rabbitmq_message = aio_pika.Message(
                body=message_body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
                message_id=message.id,
                correlation_id=message.correlation_id,
            )

            # Publish to queue
            await self._channel.default_exchange.publish(
                rabbitmq_message,
                routing_key=message.channel_name,
            )

            latency = (time.monotonic() - start) * 1000

            logger.info(
                f"Message sent to RabbitMQ queue '{message.channel_name}': {message.id}"
            )

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=message.id,
                latency_ms=latency,
                provider_response={
                    "queue": message.channel_name,
                    "message_count": queue.declaration_result.message_count,
                },
            )

        except Exception as e:
            logger.error(f"Error sending to RabbitMQ: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )

    async def receive(self, count: int = 1, timeout: float = 30.0) -> list[dict[str, Any]]:
        """Receive messages from the queue.

        Args:
            count: Maximum messages to receive
            timeout: Wait timeout in seconds

        Returns:
            List of received messages
        """
        if not self._channel:
            return []

        try:

            messages = []
            queue = await self._channel.declare_queue(
                self._channel.name if hasattr(self._channel, "name") else "default",
                durable=True,
            )

            async with asyncio.timeout(timeout):
                for _ in range(count):
                    try:
                        incoming_message = await queue.get(timeout=timeout)
                        if incoming_message:
                            messages.append(
                                {
                                    "id": incoming_message.message_id,
                                    "body": json.loads(incoming_message.body.decode()),
                                    "correlation_id": incoming_message.correlation_id,
                                    "_raw": incoming_message,
                                }
                            )
                    except TimeoutError:
                        break

            return messages

        except Exception as e:
            logger.error(f"Error receiving from RabbitMQ: {e}")
            return []

    async def ack(self, message_id: str) -> None:
        """Acknowledge a message.

        Args:
            message_id: ID of message to acknowledge
        """
        # Note: In real implementation, would need to track messages
        # and call message.ack() on the raw RabbitMQ message
        logger.debug(f"Acknowledging message {message_id}")

    async def nack(self, message_id: str, requeue: bool = True) -> None:
        """Negative acknowledge a message.

        Args:
            message_id: ID of message to nack
            requeue: Whether to requeue the message
        """
        # Note: In real implementation, would need to track messages
        # and call message.nack() on the raw RabbitMQ message
        logger.debug(f"Nacking message {message_id}, requeue={requeue}")

    async def health_check(self) -> bool:
        """Check if RabbitMQ connection is healthy."""
        if not self._connection or self._connection.is_closed:
            return False

        try:
            # Try to declare a temporary queue
            if self._channel:
                await self._channel.declare_queue("_health_check", auto_delete=True)
                return True
        except Exception as e:
            logger.debug(f"RabbitMQ health check failed: {e}")

        return False


class InMemoryQueueAdapter(QueueAdapter):
    """In-memory queue adapter (fallback).

    Queues stored in memory, lost on restart.
    Always available, useful for development and testing.
    """

    # Class-level queues shared across all instances
    _queues: ClassVar[dict[str, asyncio.Queue]] = {}
    _messages: ClassVar[dict[str, dict[str, Any]]] = {}

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)

    @property
    def provider_name(self) -> str:
        return "memory_queue"

    async def initialize(self) -> None:
        """Initialize the in-memory queue adapter."""
        await super().initialize()
        logger.info("In-memory queue adapter initialized")

    async def send(self, message: OutboxMessage) -> SendResult:
        """Send message to in-memory queue.

        Args:
            message: Outbox message to send

        Returns:
            SendResult with status
        """
        try:
            start = time.monotonic()

            # Ensure queue exists
            if message.channel_name not in self._queues:
                self._queues[message.channel_name] = asyncio.Queue()

            # Store message with metadata
            message_data = {
                "id": message.id,
                "body": message.payload,
                "correlation_id": message.correlation_id,
                "timestamp": time.time(),
            }

            # Add to queue
            await self._queues[message.channel_name].put(message_data)

            # Track for ack/nack
            self._messages[message.id] = message_data

            latency = (time.monotonic() - start) * 1000

            logger.info(
                f"Message sent to in-memory queue '{message.channel_name}': {message.id}"
            )

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=message.id,
                latency_ms=latency,
                provider_response={
                    "queue": message.channel_name,
                    "queue_size": self._queues[message.channel_name].qsize(),
                },
            )

        except Exception as e:
            logger.error(f"Error sending to in-memory queue: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )

    async def receive(self, count: int = 1, timeout: float = 30.0) -> list[dict[str, Any]]:
        """Receive messages from the queue.

        Args:
            count: Maximum messages to receive
            timeout: Wait timeout in seconds

        Returns:
            List of received messages
        """
        messages = []

        # Get default queue or first available
        queue = None
        if self._queues:
            queue = list(self._queues.values())[0]

        if not queue:
            return []

        try:
            async with asyncio.timeout(timeout):
                for _ in range(count):
                    try:
                        msg = await queue.get()
                        messages.append(msg)
                    except TimeoutError:
                        break
        except TimeoutError:
            pass

        return messages

    async def ack(self, message_id: str) -> None:
        """Acknowledge a message.

        Args:
            message_id: ID of message to acknowledge
        """
        if message_id in self._messages:
            del self._messages[message_id]
            logger.debug(f"Acknowledged message {message_id}")

    async def nack(self, message_id: str, requeue: bool = True) -> None:
        """Negative acknowledge a message.

        Args:
            message_id: ID of message to nack
            requeue: Whether to requeue the message
        """
        if requeue and message_id in self._messages:
            # For simplicity, we just keep it in _messages for requeue
            logger.debug(f"Nacked message {message_id}, requeue={requeue}")
        else:
            if message_id in self._messages:
                del self._messages[message_id]

    async def health_check(self) -> bool:
        """In-memory queue is always healthy."""
        return True

    def get_queue_size(self, queue_name: str) -> int:
        """Get the current size of a queue.

        Args:
            queue_name: Name of the queue

        Returns:
            Number of messages in queue
        """
        if queue_name in self._queues:
            return self._queues[queue_name].qsize()
        return 0

    def get_all_queue_sizes(self) -> dict[str, int]:
        """Get sizes of all queues.

        Returns:
            Dictionary mapping queue names to sizes
        """
        return {name: queue.qsize() for name, queue in self._queues.items()}
