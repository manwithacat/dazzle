"""
Stream channel adapters for DAZZLE messaging.

Provides adapters for:
- Redis Streams (production stream)
- Kafka (production stream)
- In-memory stream (fallback, development)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any, ClassVar

from .base import SendResult, SendStatus, StreamAdapter

if TYPE_CHECKING:
    from ..detection import DetectionResult
    from ..outbox import OutboxMessage

logger = logging.getLogger("dazzle.channels.adapters.stream")


class RedisAdapter(StreamAdapter):
    """Adapter for Redis Streams.

    Sends messages to Redis Streams using redis-py async.
    Perfect for production event streaming with consumer groups.
    """

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)
        self._url = detection_result.connection_url or "redis://localhost:6379"
        self._client = None

    @property
    def provider_name(self) -> str:
        return "redis"

    async def initialize(self) -> None:
        """Initialize the Redis connection."""
        await super().initialize()

        try:
            import redis.asyncio as redis

            self._client = redis.from_url(self._url, decode_responses=False)
            # Test connection
            await self._client.ping()
            logger.info(f"Redis adapter initialized (url: {self._url})")

        except ImportError:
            logger.error("redis not installed. Install with: pip install redis")
            raise RuntimeError(
                "redis is required for Redis adapter. "
                "Install with: pip install 'dazzle[redis]'"
            )
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown the Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
        await super().shutdown()

    async def send(self, message: OutboxMessage) -> SendResult:
        """Send message to Redis Stream.

        Args:
            message: Outbox message to send

        Returns:
            SendResult with status
        """
        if not self._client:
            return SendResult(
                status=SendStatus.FAILED,
                error="Redis adapter not initialized",
            )

        try:
            start = time.monotonic()

            # Add to stream with XADD
            stream_id = await self._client.xadd(
                message.channel_name,
                {
                    "payload": json.dumps(message.payload),
                    "message_id": message.id,
                    "correlation_id": message.correlation_id or "",
                    "operation": message.operation_name,
                    "message_type": message.message_type,
                },
            )

            latency = (time.monotonic() - start) * 1000

            logger.info(
                f"Message sent to Redis stream '{message.channel_name}': {message.id} -> {stream_id.decode() if isinstance(stream_id, bytes) else stream_id}"
            )

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=message.id,
                latency_ms=latency,
                provider_response={
                    "stream": message.channel_name,
                    "stream_id": stream_id.decode() if isinstance(stream_id, bytes) else stream_id,
                },
            )

        except Exception as e:
            logger.error(f"Error sending to Redis stream: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )

    async def subscribe(
        self,
        group: str,
        consumer: str,
        callback: Any,
    ) -> None:
        """Subscribe to the stream.

        Args:
            group: Consumer group name
            consumer: Consumer name within group
            callback: Async callback for messages
        """
        if not self._client:
            logger.error("Cannot subscribe: Redis adapter not initialized")
            return

        try:
            # Create consumer group if needed
            stream_name = "default"  # Would need to be configured
            try:
                await self._client.xgroup_create(
                    stream_name, group, id="0", mkstream=True
                )
            except Exception:
                # Group might already exist
                pass

            # Read from group
            while True:
                messages = await self._client.xreadgroup(
                    group,
                    consumer,
                    {stream_name: ">"},
                    count=10,
                    block=5000,
                )

                for stream, stream_messages in messages:
                    for msg_id, fields in stream_messages:
                        try:
                            await callback(fields)
                            # Acknowledge the message
                            await self._client.xack(stream, group, msg_id)
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")

        except asyncio.CancelledError:
            logger.info(f"Subscription cancelled for {group}/{consumer}")
        except Exception as e:
            logger.error(f"Error in Redis subscription: {e}")

    async def unsubscribe(self) -> None:
        """Unsubscribe from the stream."""
        # Subscriptions are task-based, cancel the task
        logger.info("Unsubscribing from Redis stream")

    async def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        if not self._client:
            return False

        try:
            await self._client.ping()
            return True
        except Exception as e:
            logger.debug(f"Redis health check failed: {e}")
            return False


class KafkaAdapter(StreamAdapter):
    """Adapter for Kafka streams.

    Sends messages to Kafka topics using aiokafka.
    Perfect for production event streaming at scale.
    """

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)
        self._bootstrap_servers = detection_result.connection_url or "localhost:9092"
        self._producer = None
        self._consumer = None

    @property
    def provider_name(self) -> str:
        return "kafka"

    async def initialize(self) -> None:
        """Initialize the Kafka producer."""
        await super().initialize()

        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            logger.info(f"Kafka adapter initialized (servers: {self._bootstrap_servers})")

        except ImportError:
            logger.error("aiokafka not installed. Install with: pip install aiokafka")
            raise RuntimeError(
                "aiokafka is required for Kafka adapter. "
                "Install with: pip install 'dazzle[kafka]'"
            )
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown the Kafka producer and consumer."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
        await super().shutdown()

    async def send(self, message: OutboxMessage) -> SendResult:
        """Send message to Kafka topic.

        Args:
            message: Outbox message to send

        Returns:
            SendResult with status
        """
        if not self._producer:
            return SendResult(
                status=SendStatus.FAILED,
                error="Kafka adapter not initialized",
            )

        try:
            start = time.monotonic()

            # Send to topic (topic name = channel name)
            record_metadata = await self._producer.send_and_wait(
                message.channel_name,
                value={
                    "payload": message.payload,
                    "message_id": message.id,
                    "correlation_id": message.correlation_id,
                    "operation": message.operation_name,
                    "message_type": message.message_type,
                },
                key=message.id.encode("utf-8"),
            )

            latency = (time.monotonic() - start) * 1000

            logger.info(
                f"Message sent to Kafka topic '{message.channel_name}': "
                f"{message.id} -> partition={record_metadata.partition}, "
                f"offset={record_metadata.offset}"
            )

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=message.id,
                latency_ms=latency,
                provider_response={
                    "topic": message.channel_name,
                    "partition": record_metadata.partition,
                    "offset": record_metadata.offset,
                },
            )

        except Exception as e:
            logger.error(f"Error sending to Kafka: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )

    async def subscribe(
        self,
        group: str,
        consumer: str,
        callback: Any,
    ) -> None:
        """Subscribe to Kafka topic.

        Args:
            group: Consumer group name
            consumer: Consumer name (used in client_id)
            callback: Async callback for messages
        """
        try:
            from aiokafka import AIOKafkaConsumer

            if not self._consumer:
                self._consumer = AIOKafkaConsumer(
                    # Would need topic name configured
                    "default",
                    bootstrap_servers=self._bootstrap_servers,
                    group_id=group,
                    client_id=consumer,
                    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                )
                await self._consumer.start()

            # Consume messages
            async for msg in self._consumer:
                try:
                    await callback(msg.value)
                except Exception as e:
                    logger.error(f"Error processing Kafka message: {e}")

        except asyncio.CancelledError:
            logger.info(f"Kafka subscription cancelled for {group}/{consumer}")
        except Exception as e:
            logger.error(f"Error in Kafka subscription: {e}")

    async def unsubscribe(self) -> None:
        """Unsubscribe from Kafka topics."""
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
        logger.info("Unsubscribed from Kafka")

    async def health_check(self) -> bool:
        """Check if Kafka connection is healthy."""
        if not self._producer:
            return False

        # Kafka producer doesn't have a simple ping
        # Check if producer is started
        return True


class InMemoryStreamAdapter(StreamAdapter):
    """In-memory stream adapter (fallback).

    Streams stored in memory, lost on restart.
    Always available, useful for development and testing.
    """

    # Class-level streams shared across all instances
    _streams: ClassVar[dict[str, list[dict[str, Any]]]] = {}
    _subscribers: ClassVar[dict[str, list[Any]]] = {}

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)

    @property
    def provider_name(self) -> str:
        return "memory_stream"

    async def initialize(self) -> None:
        """Initialize the in-memory stream adapter."""
        await super().initialize()
        logger.info("In-memory stream adapter initialized")

    async def send(self, message: OutboxMessage) -> SendResult:
        """Send message to in-memory stream.

        Args:
            message: Outbox message to send

        Returns:
            SendResult with status
        """
        try:
            start = time.monotonic()

            # Ensure stream exists
            if message.channel_name not in self._streams:
                self._streams[message.channel_name] = []

            # Create stream entry
            entry = {
                "id": f"{int(time.time() * 1000)}-{len(self._streams[message.channel_name])}",
                "message_id": message.id,
                "correlation_id": message.correlation_id,
                "payload": message.payload,
                "operation": message.operation_name,
                "message_type": message.message_type,
                "timestamp": time.time(),
            }

            # Add to stream
            self._streams[message.channel_name].append(entry)

            # Notify subscribers
            if message.channel_name in self._subscribers:
                for callback in self._subscribers[message.channel_name]:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(entry)
                        else:
                            callback(entry)
                    except Exception as e:
                        logger.error(f"Error notifying subscriber: {e}")

            latency = (time.monotonic() - start) * 1000

            logger.info(
                f"Message sent to in-memory stream '{message.channel_name}': "
                f"{message.id} -> {entry['id']}"
            )

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=message.id,
                latency_ms=latency,
                provider_response={
                    "stream": message.channel_name,
                    "stream_id": entry["id"],
                    "stream_length": len(self._streams[message.channel_name]),
                },
            )

        except Exception as e:
            logger.error(f"Error sending to in-memory stream: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )

    async def subscribe(
        self,
        group: str,
        consumer: str,
        callback: Any,
    ) -> None:
        """Subscribe to the stream.

        Args:
            group: Consumer group name (not used in memory implementation)
            consumer: Consumer name (not used in memory implementation)
            callback: Async callback for messages
        """
        # For in-memory, we just track callbacks per stream
        # Would need stream name configured
        stream_name = "default"

        if stream_name not in self._subscribers:
            self._subscribers[stream_name] = []

        self._subscribers[stream_name].append(callback)
        logger.info(f"Subscribed to in-memory stream '{stream_name}' as {group}/{consumer}")

    async def unsubscribe(self) -> None:
        """Unsubscribe from the stream."""
        # Clear all subscribers
        self._subscribers.clear()
        logger.info("Unsubscribed from in-memory stream")

    async def health_check(self) -> bool:
        """In-memory stream is always healthy."""
        return True

    def get_stream_length(self, stream_name: str) -> int:
        """Get the current length of a stream.

        Args:
            stream_name: Name of the stream

        Returns:
            Number of entries in stream
        """
        if stream_name in self._streams:
            return len(self._streams[stream_name])
        return 0

    def get_stream_entries(
        self,
        stream_name: str,
        start: int = 0,
        count: int = 10,
    ) -> list[dict[str, Any]]:
        """Get entries from a stream.

        Args:
            stream_name: Name of the stream
            start: Start index
            count: Number of entries to return

        Returns:
            List of stream entries
        """
        if stream_name not in self._streams:
            return []

        stream = self._streams[stream_name]
        return stream[start : start + count]
