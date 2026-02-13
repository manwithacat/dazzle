"""
Redis Streams Event Bus for Dazzle (Tier 2).

Provides a high-throughput event bus using Redis Streams with:
- Consumer groups for competing consumers
- XREADGROUP for efficient blocking reads
- XACK for acknowledgment
- Automatic pending message recovery

Ideal for Heroku deployments needing higher throughput than PostgreSQL.

Features:
- Sub-second latency
- ~10k events/sec throughput
- Consumer group coordination
- Configurable stream retention
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from dazzle_back.events.bus import (
    ConsumerNotFoundError,
    ConsumerStatus,
    EventBus,
    EventHandler,
    NackReason,
    SubscriptionInfo,
)
from dazzle_back.events.envelope import EventEnvelope

# Conditional import for redis
try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    if TYPE_CHECKING:
        import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Key prefixes
STREAM_PREFIX = "dazzle:stream:"
DLQ_PREFIX = "dazzle:dlq:"
OFFSET_PREFIX = "dazzle:offset:"
METADATA_PREFIX = "dazzle:meta:"


@dataclass
class RedisConfig:
    """Configuration for Redis Streams event bus."""

    url: str
    """Redis connection URL (REDIS_URL)."""

    max_stream_length: int = 10000
    """Maximum entries per stream (XTRIM MAXLEN ~)."""

    consumer_timeout_ms: int = 300000
    """Milliseconds before pending messages are reclaimed (5 minutes)."""

    block_ms: int = 5000
    """Milliseconds to block on XREADGROUP."""

    batch_size: int = 10
    """Events per batch."""

    retry_count: int = 3
    """Maximum retry attempts before moving to DLQ."""


@dataclass
class ActiveSubscription:
    """An active subscription in the broker."""

    topic: str
    group_id: str
    handler: EventHandler
    consumer_name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class RedisBus(EventBus):
    """
    Redis Streams EventBus implementation.

    Uses Redis Streams for high-throughput event streaming with:
    - XADD for publishing
    - XREADGROUP for consuming with consumer groups
    - XACK for acknowledgment
    - XCLAIM for recovering pending messages

    Example:
        config = RedisConfig(url=os.environ["REDIS_URL"])
        async with RedisBus(config) as bus:
            await bus.publish("app.Order", envelope)

            async def handler(event):
                print(f"Received: {event.event_type}")

            await bus.subscribe("app.Order", "my-consumer", handler)
            await bus.start_consumer_loop()
    """

    def __init__(self, config: RedisConfig) -> None:
        """
        Initialize the Redis Streams bus.

        Args:
            config: Redis configuration
        """
        if not REDIS_AVAILABLE:
            raise ImportError("redis is required for RedisBus. Install with: pip install redis")

        self._config = config
        self._redis: aioredis.Redis | None = None
        self._subscriptions: dict[tuple[str, str], ActiveSubscription] = {}
        self._lock = asyncio.Lock()
        self._consumer_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._running = False

    def _stream_key(self, topic: str) -> str:
        """Get Redis key for a stream."""
        return f"{STREAM_PREFIX}{topic}"

    def _dlq_key(self, topic: str) -> str:
        """Get Redis key for DLQ stream."""
        return f"{DLQ_PREFIX}{topic}"

    def _offset_key(self, topic: str, group_id: str) -> str:
        """Get Redis key for consumer offset metadata."""
        return f"{OFFSET_PREFIX}{topic}:{group_id}"

    async def connect(self) -> None:
        """Connect to Redis."""
        self._redis = aioredis.from_url(
            self._config.url,
            decode_responses=False,  # We handle encoding ourselves
        )
        # Test connection
        await self._redis.ping()

    async def close(self) -> None:
        """Close the Redis connection and stop consumers."""
        self._running = False

        # Cancel consumer tasks
        for task in self._consumer_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._consumer_tasks.clear()

        # Close Redis connection
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def __aenter__(self) -> RedisBus:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _get_redis(self) -> aioredis.Redis:
        """Get Redis connection with error handling."""
        if self._redis is None:
            raise RuntimeError("RedisBus not connected. Call connect() first.")
        return self._redis

    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope,
        *,
        transactional: bool = False,
    ) -> None:
        """
        Publish an event to a topic.

        Events are added to a Redis Stream using XADD.
        Note: transactional=True is ignored (Redis doesn't support cross-DB transactions).
        """
        redis = self._get_redis()
        stream_key = self._stream_key(topic)

        # Serialize envelope to Redis hash fields
        fields = {
            b"id": str(envelope.event_id).encode(),
            b"event_type": envelope.event_type.encode(),
            b"event_version": envelope.event_version.encode(),
            b"key": envelope.key.encode(),
            b"payload": json.dumps(envelope.payload).encode(),
            b"headers": json.dumps(envelope.headers).encode(),
            b"correlation_id": (
                str(envelope.correlation_id).encode() if envelope.correlation_id else b""
            ),
            b"causation_id": (
                str(envelope.causation_id).encode() if envelope.causation_id else b""
            ),
            b"timestamp": envelope.timestamp.isoformat().encode(),
            b"producer": envelope.producer.encode(),
        }

        # Add to stream with approximate maxlen trimming
        await redis.xadd(
            stream_key,
            fields,
            maxlen=self._config.max_stream_length,
            approximate=True,
        )

    async def subscribe(
        self,
        topic: str,
        group_id: str,
        handler: EventHandler,
    ) -> SubscriptionInfo:
        """Subscribe to events from a topic using a consumer group."""
        async with self._lock:
            key = (topic, group_id)
            redis = self._get_redis()
            stream_key = self._stream_key(topic)

            # Create consumer group if it doesn't exist
            try:
                await redis.xgroup_create(
                    stream_key,
                    group_id,
                    id="0",  # Start from beginning
                    mkstream=True,  # Create stream if doesn't exist
                )
            except aioredis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

            # Generate unique consumer name
            consumer_name = f"{group_id}-{uuid4().hex[:8]}"

            # Create subscription record
            sub = ActiveSubscription(
                topic=topic,
                group_id=group_id,
                handler=handler,
                consumer_name=consumer_name,
            )
            self._subscriptions[key] = sub

            return SubscriptionInfo(
                topic=topic,
                group_id=group_id,
                handler=handler,
            )

    async def unsubscribe(
        self,
        topic: str,
        group_id: str,
    ) -> None:
        """Unsubscribe a consumer group from a topic."""
        async with self._lock:
            key = (topic, group_id)
            if key not in self._subscriptions:
                raise ConsumerNotFoundError(topic, group_id)

            # Stop consumer task if running
            if key in self._consumer_tasks:
                self._consumer_tasks[key].cancel()
                try:
                    await self._consumer_tasks[key]
                except asyncio.CancelledError:
                    pass
                del self._consumer_tasks[key]

            del self._subscriptions[key]

    async def ack(
        self,
        topic: str,
        group_id: str,
        event_id: UUID,
    ) -> None:
        """Acknowledge successful processing of an event."""
        redis = self._get_redis()
        stream_key = self._stream_key(topic)

        # We need the message ID, not the event ID
        # Store mapping when consuming, or search for it
        # For now, we'll track this in metadata
        offset_key = self._offset_key(topic, group_id)
        msg_id = await redis.hget(offset_key, f"msg:{event_id}")

        if msg_id:
            await redis.xack(stream_key, group_id, msg_id)
            await redis.hdel(offset_key, f"msg:{event_id}")

            # Update last processed timestamp
            await redis.hset(offset_key, "last_processed_at", datetime.now(UTC).isoformat())

    async def nack(
        self,
        topic: str,
        group_id: str,
        event_id: UUID,
        reason: NackReason,
    ) -> None:
        """Reject an event, indicating processing failed."""
        redis = self._get_redis()
        stream_key = self._stream_key(topic)
        dlq_key = self._dlq_key(topic)
        offset_key = self._offset_key(topic, group_id)

        # Get message ID
        msg_id = await redis.hget(offset_key, f"msg:{event_id}")
        if not msg_id:
            return

        # Get retry count
        retry_key = f"retry:{event_id}"
        retry_count = await redis.hget(offset_key, retry_key)
        retry_count = int(retry_count) if retry_count else 0

        if not reason.retryable or retry_count >= self._config.retry_count:
            # Move to DLQ
            # First get the message data
            messages = await redis.xrange(stream_key, msg_id, msg_id)
            if messages:
                _, fields = messages[0]
                # Add to DLQ with reason
                dlq_fields = dict(fields)
                dlq_fields[b"reason_code"] = reason.code.encode()
                dlq_fields[b"reason_message"] = reason.message.encode()
                dlq_fields[b"reason_metadata"] = json.dumps(reason.metadata).encode()
                dlq_fields[b"attempts"] = str(retry_count + 1).encode()
                dlq_fields[b"group_id"] = group_id.encode()
                dlq_fields[b"dlq_at"] = datetime.now(UTC).isoformat().encode()

                await redis.xadd(dlq_key, dlq_fields)

            # Acknowledge to remove from pending
            await redis.xack(stream_key, group_id, msg_id)
            await redis.hdel(offset_key, f"msg:{event_id}", retry_key)
        else:
            # Increment retry count - message will be redelivered
            await redis.hset(offset_key, retry_key, str(retry_count + 1))

    async def replay(
        self,
        topic: str,
        *,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        from_offset: int | None = None,
        to_offset: int | None = None,
        key_filter: str | None = None,
    ) -> AsyncIterator[EventEnvelope]:
        """
        Replay events from a topic.

        Note: Redis Streams use message IDs (timestamp-sequence), not offsets.
        from_offset/to_offset are interpreted as message ID prefixes.
        """
        redis = self._get_redis()
        stream_key = self._stream_key(topic)

        # Convert timestamp to Redis stream ID format (milliseconds-0)
        start = "-"
        end = "+"

        if from_timestamp:
            start = f"{int(from_timestamp.timestamp() * 1000)}-0"
        elif from_offset is not None:
            start = str(from_offset)

        if to_timestamp:
            end = f"{int(to_timestamp.timestamp() * 1000)}-0"
        elif to_offset is not None:
            end = str(to_offset)

        # Use XRANGE for replay
        messages = await redis.xrange(stream_key, start, end)

        for _msg_id, fields in messages:
            envelope = self._fields_to_envelope(fields)

            # Apply key filter if specified
            if key_filter and envelope.key != key_filter:
                continue

            yield envelope

    async def get_consumer_status(
        self,
        topic: str,
        group_id: str,
    ) -> ConsumerStatus:
        """Get status information for a consumer group."""
        redis = self._get_redis()
        stream_key = self._stream_key(topic)
        offset_key = self._offset_key(topic, group_id)

        # Get group info
        try:
            groups = await redis.xinfo_groups(stream_key)
        except aioredis.ResponseError:
            raise ConsumerNotFoundError(topic, group_id)

        group_info = None
        for g in groups:
            if g.get(b"name", g.get("name")) == group_id.encode():
                group_info = g
                break

        if not group_info:
            raise ConsumerNotFoundError(topic, group_id)

        # Get pending count
        pending = group_info.get(b"pending", group_info.get("pending", 0))

        # Get last entry ID
        last_id = group_info.get(b"last-delivered-id", group_info.get("last-delivered-id", b"0-0"))
        if isinstance(last_id, bytes):
            last_id = last_id.decode()

        # Parse offset from last_id (format: timestamp-sequence)
        try:
            last_offset = int(last_id.split("-")[0])
        except (ValueError, IndexError):
            last_offset = 0

        # Get last processed timestamp
        last_processed = await redis.hget(offset_key, "last_processed_at")
        last_processed_at = None
        if last_processed:
            try:
                last_processed_at = datetime.fromisoformat(last_processed.decode())
            except (ValueError, AttributeError):
                pass

        return ConsumerStatus(
            topic=topic,
            group_id=group_id,
            last_offset=last_offset,
            pending_count=pending,
            last_processed_at=last_processed_at,
        )

    async def list_topics(self) -> list[str]:
        """List all topics in the bus."""
        redis = self._get_redis()

        # Scan for stream keys
        topics = []
        async for key in redis.scan_iter(f"{STREAM_PREFIX}*"):
            if isinstance(key, bytes):
                key = key.decode()
            topic = key[len(STREAM_PREFIX) :]
            topics.append(topic)

        return sorted(topics)

    async def list_consumer_groups(self, topic: str) -> list[str]:
        """List all consumer groups for a topic."""
        redis = self._get_redis()
        stream_key = self._stream_key(topic)

        try:
            groups = await redis.xinfo_groups(stream_key)
            return [
                (g.get(b"name") or g.get("name")).decode()
                if isinstance(g.get(b"name") or g.get("name"), bytes)
                else (g.get(b"name") or g.get("name"))
                for g in groups
            ]
        except aioredis.ResponseError:
            return []

    async def get_topic_info(self, topic: str) -> dict[str, Any]:
        """Get information about a topic."""
        redis = self._get_redis()
        stream_key = self._stream_key(topic)
        dlq_key = self._dlq_key(topic)

        try:
            info = await redis.xinfo_stream(stream_key)
        except aioredis.ResponseError:
            return {
                "topic": topic,
                "event_count": 0,
                "oldest_event": None,
                "newest_event": None,
                "consumer_groups": [],
                "dlq_count": 0,
            }

        # Get stream length
        length = info.get(b"length", info.get("length", 0))

        # Get first/last entry timestamps
        first_entry = info.get(b"first-entry", info.get("first-entry"))
        last_entry = info.get(b"last-entry", info.get("last-entry"))

        oldest_event = None
        newest_event = None

        if first_entry:
            msg_id = first_entry[0]
            if isinstance(msg_id, bytes):
                msg_id = msg_id.decode()
            try:
                oldest_event = datetime.fromtimestamp(
                    int(msg_id.split("-")[0]) / 1000, UTC
                ).isoformat()
            except (ValueError, IndexError):
                pass

        if last_entry:
            msg_id = last_entry[0]
            if isinstance(msg_id, bytes):
                msg_id = msg_id.decode()
            try:
                newest_event = datetime.fromtimestamp(
                    int(msg_id.split("-")[0]) / 1000, UTC
                ).isoformat()
            except (ValueError, IndexError):
                pass

        # Get consumer groups
        groups = await self.list_consumer_groups(topic)

        # Get DLQ count
        try:
            dlq_count = await redis.xlen(dlq_key)
        except aioredis.ResponseError:
            dlq_count = 0

        return {
            "topic": topic,
            "event_count": length,
            "oldest_event": oldest_event,
            "newest_event": newest_event,
            "consumer_groups": groups,
            "dlq_count": dlq_count,
        }

    def _fields_to_envelope(self, fields: dict[bytes, bytes]) -> EventEnvelope:
        """Convert Redis stream fields to an EventEnvelope."""

        def get_str(key: bytes) -> str:
            val = fields.get(key, b"")
            return val.decode() if isinstance(val, bytes) else val

        def get_uuid(key: bytes) -> UUID | None:
            val = get_str(key)
            return UUID(val) if val else None

        payload_str = get_str(b"payload")
        headers_str = get_str(b"headers")

        return EventEnvelope(
            event_id=UUID(get_str(b"id")),
            event_type=get_str(b"event_type"),
            event_version=get_str(b"event_version") or "1.0",
            key=get_str(b"key"),
            payload=json.loads(payload_str) if payload_str else {},
            headers=json.loads(headers_str) if headers_str else {},
            correlation_id=get_uuid(b"correlation_id"),
            causation_id=get_uuid(b"causation_id"),
            timestamp=datetime.fromisoformat(get_str(b"timestamp")),
            producer=get_str(b"producer") or "dazzle",
        )

    # Consumer loop methods

    async def start_consumer_loop(self) -> None:
        """
        Start consumer loops for all subscriptions.

        This runs until stop_consumer_loop() is called or the bus is closed.
        """
        self._running = True

        for key, sub in self._subscriptions.items():
            if key not in self._consumer_tasks:
                task = asyncio.create_task(
                    self._consumer_loop(sub.topic, sub.group_id, sub.consumer_name)
                )
                self._consumer_tasks[key] = task

    async def stop_consumer_loop(self) -> None:
        """Stop all consumer loops."""
        self._running = False
        for task in self._consumer_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._consumer_tasks.clear()

    async def _consumer_loop(
        self,
        topic: str,
        group_id: str,
        consumer_name: str,
    ) -> None:
        """Main consumer loop for a subscription."""
        redis = self._get_redis()
        stream_key = self._stream_key(topic)
        offset_key = self._offset_key(topic, group_id)

        while self._running:
            try:
                # First, try to recover any pending messages that timed out
                await self._recover_pending(topic, group_id, consumer_name)

                # Read new messages
                messages = await redis.xreadgroup(
                    group_id,
                    consumer_name,
                    {stream_key: ">"},  # Only new messages
                    count=self._config.batch_size,
                    block=self._config.block_ms,
                )

                if not messages:
                    continue

                key = (topic, group_id)
                if key not in self._subscriptions:
                    break

                handler = self._subscriptions[key].handler

                for _stream_name, stream_messages in messages:
                    for msg_id, fields in stream_messages:
                        envelope = self._fields_to_envelope(fields)

                        # Store message ID mapping for ack/nack
                        await redis.hset(offset_key, f"msg:{envelope.event_id}", msg_id)

                        try:
                            await handler(envelope)
                            await self.ack(topic, group_id, envelope.event_id)
                        except Exception as e:
                            await self.nack(
                                topic,
                                group_id,
                                envelope.event_id,
                                NackReason.handler_error(str(e)),
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consumer loop error for {topic}/{group_id}: {e}")
                await asyncio.sleep(1)

    async def _recover_pending(
        self,
        topic: str,
        group_id: str,
        consumer_name: str,
    ) -> None:
        """Recover pending messages from dead consumers."""
        redis = self._get_redis()
        stream_key = self._stream_key(topic)

        try:
            # Get pending messages older than timeout
            pending = await redis.xpending_range(
                stream_key,
                group_id,
                min="-",
                max="+",
                count=10,
            )

            for entry in pending:
                # entry format varies by redis-py version
                if isinstance(entry, dict):
                    msg_id = entry.get("message_id", entry.get(b"message_id"))
                    idle_time = entry.get("time_since_delivered", entry.get(b"time"))
                else:
                    # Tuple format: (message_id, consumer, idle_time, delivery_count)
                    msg_id, _, idle_time, _ = entry

                if isinstance(msg_id, bytes):
                    msg_id = msg_id.decode()

                # Claim if idle longer than timeout
                if idle_time and idle_time > self._config.consumer_timeout_ms:
                    claimed = await redis.xclaim(
                        stream_key,
                        group_id,
                        consumer_name,
                        min_idle_time=self._config.consumer_timeout_ms,
                        message_ids=[msg_id],
                    )
                    if claimed:
                        logger.info(f"Claimed pending message {msg_id} for {topic}")

        except Exception as e:
            logger.debug(f"Error recovering pending messages: {e}")

    # DLQ methods

    async def get_dlq_events(
        self,
        topic: str | None = None,
        group_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get events from the dead letter queue."""
        redis = self._get_redis()
        results = []

        if topic:
            topics = [topic]
        else:
            # Get all DLQ streams
            topics = []
            async for key in redis.scan_iter(f"{DLQ_PREFIX}*"):
                if isinstance(key, bytes):
                    key = key.decode()
                topics.append(key[len(DLQ_PREFIX) :])

        for t in topics:
            dlq_key = self._dlq_key(t)
            messages = await redis.xrevrange(dlq_key, count=limit)

            for msg_id, fields in messages:
                if group_id:
                    msg_group = fields.get(b"group_id", b"").decode()
                    if msg_group != group_id:
                        continue

                envelope = self._fields_to_envelope(fields)

                results.append(
                    {
                        "event_id": str(envelope.event_id),
                        "topic": t,
                        "group_id": fields.get(b"group_id", b"").decode(),
                        "envelope": envelope,
                        "reason_code": fields.get(b"reason_code", b"").decode(),
                        "reason_message": fields.get(b"reason_message", b"").decode(),
                        "attempts": int(fields.get(b"attempts", b"1").decode()),
                        "created_at": fields.get(b"dlq_at", b"").decode(),
                        "msg_id": msg_id.decode() if isinstance(msg_id, bytes) else msg_id,
                    }
                )

                if len(results) >= limit:
                    break

        return results[:limit]

    async def get_dlq_count(self, topic: str | None = None) -> int:
        """Get count of events in dead letter queue."""
        redis = self._get_redis()

        if topic:
            try:
                result = await redis.xlen(self._dlq_key(topic))
                return int(result) if result else 0
            except aioredis.ResponseError:
                return 0

        # Sum all DLQ streams
        total = 0
        async for key in redis.scan_iter(f"{DLQ_PREFIX}*"):
            try:
                total += await redis.xlen(key)
            except aioredis.ResponseError:
                pass
        return total

    async def replay_dlq_event(
        self,
        event_id: str,
        group_id: str,
    ) -> bool:
        """
        Replay a single event from the DLQ.

        Returns:
            True if event was found and replayed successfully
        """
        redis = self._get_redis()

        # Find the event in DLQ
        dlq_events = await self.get_dlq_events(group_id=group_id, limit=1000)
        target = None
        for ev in dlq_events:
            if ev["event_id"] == event_id:
                target = ev
                break

        if not target:
            return False

        topic = target["topic"]
        envelope = target["envelope"]
        msg_id = target.get("msg_id")

        # Process through handler
        key = (topic, group_id)
        if key not in self._subscriptions:
            raise ConsumerNotFoundError(topic, group_id)

        handler = self._subscriptions[key].handler

        try:
            await handler(envelope)
            # Remove from DLQ on success
            if msg_id:
                await redis.xdel(self._dlq_key(topic), msg_id)
            return True
        except Exception:
            raise

    async def clear_dlq(
        self,
        topic: str | None = None,
        group_id: str | None = None,
    ) -> int:
        """
        Clear events from the dead letter queue.

        Returns:
            Number of events cleared
        """
        redis = self._get_redis()
        count = 0

        if topic:
            topics = [topic]
        else:
            topics = []
            async for key in redis.scan_iter(f"{DLQ_PREFIX}*"):
                if isinstance(key, bytes):
                    key = key.decode()
                topics.append(key[len(DLQ_PREFIX) :])

        for t in topics:
            dlq_key = self._dlq_key(t)

            if group_id:
                # Delete only events for this group
                messages = await redis.xrange(dlq_key)
                for msg_id, fields in messages:
                    msg_group = fields.get(b"group_id", b"").decode()
                    if msg_group == group_id:
                        await redis.xdel(dlq_key, msg_id)
                        count += 1
            else:
                # Delete entire stream
                try:
                    stream_len = await redis.xlen(dlq_key)
                    await redis.delete(dlq_key)
                    count += stream_len
                except aioredis.ResponseError:
                    pass

        return count
