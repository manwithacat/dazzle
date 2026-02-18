"""
Stream channel adapters for DAZZLE messaging.

Provides adapters for:
- Redis Streams (production)
- Kafka (production)
- In-memory stream (development/testing fallback)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, ClassVar

from .base import SendResult, SendStatus, StreamAdapter

if TYPE_CHECKING:
    from ..detection import DetectionResult
    from ..outbox import OutboxMessage

logger = logging.getLogger("dazzle.channels.adapters.stream")


def _safe_json_loads(raw: bytes) -> dict[str, Any]:
    """Decode JSON from bytes, returning error dict on failure."""
    try:
        return dict(json.loads(raw.decode(errors="replace")))
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.warning("Malformed message payload: %s", exc)
        return {"_error": "malformed_payload", "_raw": raw.decode(errors="replace")[:200]}


class RedisStreamAdapter(StreamAdapter):
    """Adapter for Redis Streams.

    Uses redis-py async for Redis Streams communication.
    Requires: pip install redis
    """

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)
        self._url = detection_result.connection_url or "redis://localhost:6379"
        self._client: Any = None
        self._subscriptions: dict[str, asyncio.Task[None]] = {}

    @property
    def provider_name(self) -> str:
        return "redis"

    async def initialize(self) -> None:
        """Initialize Redis connection."""
        try:
            import redis.asyncio as redis

            self._client = redis.from_url(self._url)
            # Test connection
            await self._client.ping()
            await super().initialize()
            logger.info(f"Redis stream adapter initialized ({self._url})")

        except ImportError:
            raise ImportError(
                "redis is required for Redis Streams support. "
                "Install it with: pip install 'dazzle[redis]'"
            )
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def shutdown(self) -> None:
        """Close Redis connection."""
        # Cancel all subscriptions
        for task in self._subscriptions.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._subscriptions.clear()

        if self._client:
            try:
                await self._client.close()
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")
        self._client = None
        await super().shutdown()
        logger.info("Redis stream adapter shut down")

    async def send(self, message: OutboxMessage) -> SendResult:
        """Send message to Redis Stream using XADD.

        Args:
            message: Outbox message to send

        Returns:
            SendResult with status
        """
        if not self._client:
            return SendResult(
                status=SendStatus.FAILED,
                error="Redis client not initialized",
            )

        try:
            start = time.monotonic()

            # Build message fields
            fields = {
                "id": message.id,
                "operation": message.operation_name,
                "type": message.message_type,
                "payload": json.dumps(message.payload),
                "recipient": message.recipient or "",
            }

            if message.correlation_id:
                fields["correlation_id"] = message.correlation_id

            if message.metadata:
                fields["metadata"] = json.dumps(message.metadata)

            # XADD to stream
            stream_id = await self._client.xadd(message.channel_name, fields)

            latency = (time.monotonic() - start) * 1000

            logger.info(f"Message sent to Redis stream '{message.channel_name}': {stream_id}")

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=str(stream_id),
                latency_ms=latency,
                provider_response={
                    "stream": message.channel_name,
                    "stream_id": str(stream_id),
                },
            )

        except Exception as e:
            logger.error(f"Redis stream send error: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )

    async def subscribe(
        self,
        group: str,
        consumer: str,
        callback: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        """Subscribe to Redis Stream using consumer groups.

        Args:
            group: Consumer group name
            consumer: Consumer name within group
            callback: Async callback for messages
        """
        if not self._client:
            raise RuntimeError("Redis client not initialized")

        stream_name = self.detection_result.metadata.get("stream_name", "default")

        # Create consumer group if it doesn't exist
        try:
            await self._client.xgroup_create(stream_name, group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                logger.warning("Redis consumer group creation failed: %s", exc)
            else:
                logger.debug("Consumer group '%s' already exists", group)

        async def read_loop() -> None:
            while True:
                try:
                    # Read from stream
                    messages = await self._client.xreadgroup(
                        groupname=group,
                        consumername=consumer,
                        streams={stream_name: ">"},
                        count=10,
                        block=5000,
                    )

                    for stream, entries in messages:
                        for entry_id, fields in entries:
                            msg = {
                                "_stream_id": entry_id,
                                "_stream": stream,
                                **{
                                    k.decode(errors="replace")
                                    if isinstance(k, bytes)
                                    else k: v.decode(errors="replace")
                                    if isinstance(v, bytes)
                                    else v
                                    for k, v in fields.items()
                                },
                            }

                            # Parse JSON fields
                            if "payload" in msg:
                                try:
                                    msg["payload"] = json.loads(msg["payload"])
                                except json.JSONDecodeError:
                                    pass

                            if "metadata" in msg:
                                try:
                                    msg["metadata"] = json.loads(msg["metadata"])
                                except json.JSONDecodeError:
                                    pass

                            await callback(msg)

                            # Acknowledge
                            await self._client.xack(stream_name, group, entry_id)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Redis stream read error: {e}")
                    await asyncio.sleep(1)

        task = asyncio.create_task(read_loop())
        self._subscriptions[f"{stream_name}:{group}:{consumer}"] = task
        logger.info(f"Subscribed to Redis stream '{stream_name}' as {group}/{consumer}")

    async def unsubscribe(self) -> None:
        """Unsubscribe from all streams."""
        for key, task in list(self._subscriptions.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._subscriptions[key]
        logger.info("Unsubscribed from all Redis streams")

    async def health_check(self) -> bool:
        """Check if Redis is accessible."""
        if not self._client:
            return False

        try:
            await self._client.ping()
            return True
        except Exception:
            logger.debug("Redis health check failed", exc_info=True)
            return False


class KafkaAdapter(StreamAdapter):
    """Adapter for Apache Kafka.

    Uses aiokafka for async Kafka communication.
    Requires: pip install aiokafka
    """

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)
        self._bootstrap_servers = detection_result.connection_url or "localhost:9092"
        self._producer: Any = None
        self._consumers: dict[str, Any] = {}
        self._consumer_tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def provider_name(self) -> str:
        return "kafka"

    async def initialize(self) -> None:
        """Initialize Kafka producer."""
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
            await self._producer.start()
            await super().initialize()
            logger.info(f"Kafka adapter initialized ({self._bootstrap_servers})")

        except ImportError:
            raise ImportError(
                "aiokafka is required for Kafka support. "
                "Install it with: pip install 'dazzle[kafka]'"
            )
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise

    async def shutdown(self) -> None:
        """Close Kafka connections."""
        # Stop consumers
        for task in self._consumer_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._consumer_tasks.clear()

        for consumer in self._consumers.values():
            try:
                await consumer.stop()
            except Exception as e:
                logger.warning(f"Error stopping Kafka consumer: {e}")
        self._consumers.clear()

        # Stop producer
        if self._producer:
            try:
                await self._producer.stop()
            except Exception as e:
                logger.warning(f"Error stopping Kafka producer: {e}")
        self._producer = None

        await super().shutdown()
        logger.info("Kafka adapter shut down")

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
                error="Kafka producer not initialized",
            )

        try:
            start = time.monotonic()

            # Build message value
            value = {
                "id": message.id,
                "operation": message.operation_name,
                "type": message.message_type,
                "payload": message.payload,
                "recipient": message.recipient,
                "correlation_id": message.correlation_id,
                "metadata": message.metadata,
            }

            # Send to topic (channel_name = topic)
            result = await self._producer.send_and_wait(
                message.channel_name,
                value=value,
                key=message.id.encode() if message.id else None,
            )

            latency = (time.monotonic() - start) * 1000

            logger.info(
                f"Message sent to Kafka topic '{message.channel_name}': "
                f"partition={result.partition}, offset={result.offset}"
            )

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=f"{result.partition}:{result.offset}",
                latency_ms=latency,
                provider_response={
                    "topic": message.channel_name,
                    "partition": result.partition,
                    "offset": result.offset,
                },
            )

        except Exception as e:
            logger.error(f"Kafka send error: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )

    async def subscribe(
        self,
        group: str,
        consumer: str,
        callback: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        """Subscribe to Kafka topic using consumer groups.

        Args:
            group: Consumer group name
            consumer: Consumer name (used as client_id)
            callback: Async callback for messages
        """
        try:
            from aiokafka import AIOKafkaConsumer

            topic = self.detection_result.metadata.get("topic", "default")

            kafka_consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self._bootstrap_servers,
                group_id=group,
                client_id=consumer,
                value_deserializer=lambda v: _safe_json_loads(v),
                auto_offset_reset="earliest",
            )

            await kafka_consumer.start()
            self._consumers[f"{topic}:{group}"] = kafka_consumer

            async def consume_loop() -> None:
                try:
                    async for msg in kafka_consumer:
                        try:
                            data = {
                                "_topic": msg.topic,
                                "_partition": msg.partition,
                                "_offset": msg.offset,
                                **msg.value,
                            }
                            await callback(data)
                        except Exception as e:
                            logger.error(f"Error processing Kafka message: {e}")
                except asyncio.CancelledError:
                    pass

            task = asyncio.create_task(consume_loop())
            self._consumer_tasks[f"{topic}:{group}"] = task
            logger.info(f"Subscribed to Kafka topic '{topic}' as group '{group}'")

        except ImportError:
            raise ImportError(
                "aiokafka is required for Kafka support. "
                "Install it with: pip install 'dazzle[kafka]'"
            )

    async def unsubscribe(self) -> None:
        """Unsubscribe from all topics."""
        for _key, task in list(self._consumer_tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        for _key, consumer in list(self._consumers.items()):
            try:
                await consumer.stop()
            except Exception as e:
                logger.warning(f"Error stopping consumer: {e}")

        self._consumer_tasks.clear()
        self._consumers.clear()
        logger.info("Unsubscribed from all Kafka topics")

    async def health_check(self) -> bool:
        """Check if Kafka is accessible."""
        if not self._producer:
            return False

        try:
            # Check if producer is connected
            partitions = await self._producer.partitions_for("__consumer_offsets")
            return partitions is not None
        except Exception:
            logger.debug("Kafka health check failed", exc_info=True)
            return False


class InMemoryStreamAdapter(StreamAdapter):
    """In-memory stream adapter for development/testing.

    Streams are stored in memory and shared across all instances.
    Data is lost on process restart.
    """

    # Class-level shared streams (deque for each stream)
    _streams: ClassVar[dict[str, deque[dict[str, Any]]]] = {}
    _subscribers: ClassVar[
        dict[str, list[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]]]
    ] = {}
    _lock: ClassVar[asyncio.Lock | None] = None
    _counter: ClassVar[int] = 0

    def __init__(self, detection_result: DetectionResult):
        super().__init__(detection_result)
        self._subscription_task: asyncio.Task[None] | None = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Get or create the class lock."""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @property
    def provider_name(self) -> str:
        return "memory_stream"

    async def initialize(self) -> None:
        """Initialize in-memory stream adapter."""
        await super().initialize()
        logger.info("In-memory stream adapter initialized")

    async def shutdown(self) -> None:
        """Shutdown in-memory stream adapter."""
        if self._subscription_task:
            self._subscription_task.cancel()
            try:
                await self._subscription_task
            except asyncio.CancelledError:
                pass
        await super().shutdown()
        logger.info("In-memory stream adapter shut down")

    @classmethod
    def _get_stream(cls, name: str) -> deque[dict[str, Any]]:
        """Get or create a stream by name."""
        if name not in cls._streams:
            cls._streams[name] = deque(maxlen=10000)  # Keep last 10k messages
        return cls._streams[name]

    @classmethod
    def _next_id(cls) -> str:
        """Generate next stream ID."""
        cls._counter += 1
        return f"{int(time.time() * 1000)}-{cls._counter}"

    async def send(self, message: OutboxMessage) -> SendResult:
        """Send message to in-memory stream.

        Args:
            message: Outbox message to send

        Returns:
            SendResult with status
        """
        try:
            start = time.monotonic()

            stream = self._get_stream(message.channel_name)
            stream_id = self._next_id()

            msg_data = {
                "_stream_id": stream_id,
                "id": message.id,
                "operation": message.operation_name,
                "type": message.message_type,
                "payload": message.payload,
                "recipient": message.recipient,
                "correlation_id": message.correlation_id,
                "metadata": message.metadata,
            }

            async with self._get_lock():
                stream.append(msg_data)

                # Notify subscribers
                if message.channel_name in self._subscribers:
                    for callback in self._subscribers[message.channel_name]:
                        try:
                            await callback(msg_data.copy())
                        except Exception as e:
                            logger.error(f"Subscriber callback error: {e}")

            latency = (time.monotonic() - start) * 1000

            logger.info(f"Message sent to in-memory stream '{message.channel_name}': {stream_id}")

            return SendResult(
                status=SendStatus.SUCCESS,
                message_id=stream_id,
                latency_ms=latency,
                provider_response={
                    "stream": message.channel_name,
                    "stream_id": stream_id,
                    "stream_size": len(stream),
                },
            )

        except Exception as e:
            logger.error(f"In-memory stream send error: {e}")
            return SendResult(
                status=SendStatus.FAILED,
                error=str(e),
            )

    async def subscribe(
        self,
        group: str,
        consumer: str,
        callback: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        """Subscribe to in-memory stream.

        Args:
            group: Consumer group name (ignored for in-memory)
            consumer: Consumer name (ignored for in-memory)
            callback: Async callback for messages
        """
        stream_name = self.detection_result.metadata.get("stream_name", "default")

        async with self._get_lock():
            if stream_name not in self._subscribers:
                self._subscribers[stream_name] = []
            self._subscribers[stream_name].append(callback)

        logger.info(f"Subscribed to in-memory stream '{stream_name}'")

    async def unsubscribe(self) -> None:
        """Unsubscribe from all streams."""
        async with self._get_lock():
            # Clear all subscriptions (simple implementation)
            self._subscribers.clear()
        logger.info("Unsubscribed from all in-memory streams")

    async def health_check(self) -> bool:
        """In-memory stream is always healthy."""
        return True

    @classmethod
    def clear_all(cls) -> None:
        """Clear all streams (for testing)."""
        cls._streams.clear()
        cls._subscribers.clear()
        cls._counter = 0

    @classmethod
    def get_stream_size(cls, name: str) -> int:
        """Get size of a stream (for testing)."""
        if name in cls._streams:
            return len(cls._streams[name])
        return 0

    @classmethod
    def get_stream_messages(cls, name: str, count: int = 100) -> list[dict[str, Any]]:
        """Get recent messages from a stream (for testing)."""
        if name not in cls._streams:
            return []
        stream = cls._streams[name]
        return list(stream)[-count:]
