"""
Kafka-Backed Event Bus for Production.

KafkaBus provides a production-grade implementation of the EventBus
interface using Apache Kafka via the aiokafka library.

Features:
- High throughput, low latency event streaming
- Durable event storage with configurable retention
- Consumer group coordination with automatic rebalancing
- At-least-once delivery with manual offset commits
- Dead letter queue support via dedicated DLQ topics

Requirements:
- Apache Kafka cluster (local or cloud-hosted)
- aiokafka library: pip install aiokafka

Configuration via environment variables:
- KAFKA_BOOTSTRAP_SERVERS: Comma-separated list of brokers (default: localhost:9092)
- KAFKA_SECURITY_PROTOCOL: PLAINTEXT, SSL, SASL_PLAINTEXT, SASL_SSL (default: PLAINTEXT)
- KAFKA_SASL_MECHANISM: PLAIN, SCRAM-SHA-256, SCRAM-SHA-512 (optional)
- KAFKA_SASL_USERNAME: SASL username (optional)
- KAFKA_SASL_PASSWORD: SASL password (optional)
- KAFKA_SSL_CAFILE: Path to CA certificate file (optional)
- KAFKA_SSL_CERTFILE: Path to client certificate file (optional)
- KAFKA_SSL_KEYFILE: Path to client key file (optional)
- KAFKA_DLQ_SUFFIX: Suffix for DLQ topics (default: .dlq)

Part of v0.18.0 Event-First Architecture (Issue #25, Phase I).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from dazzle_dnr_back.events.bus import (
    ConsumerNotFoundError,
    ConsumerStatus,
    EventBus,
    EventBusError,
    EventHandler,
    NackReason,
    PublishError,
    SubscriptionError,
    SubscriptionInfo,
    TopicNotFoundError,
)
from dazzle_dnr_back.events.envelope import EventEnvelope

# Optional import for aiokafka
KAFKA_AVAILABLE = False
try:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
    from aiokafka.admin import AIOKafkaAdminClient, NewTopic
    from aiokafka.errors import KafkaError, TopicAlreadyExistsError
    from aiokafka.structs import TopicPartition

    KAFKA_AVAILABLE = True
except ImportError:
    pass  # Kafka functionality will raise error when used

logger = logging.getLogger("dazzle.events.kafka")


def _check_kafka_available() -> None:
    """Raise an error if aiokafka is not installed."""
    if not KAFKA_AVAILABLE:
        raise ImportError("KafkaBus requires aiokafka. Install it with: pip install aiokafka")


@dataclass
class KafkaConfig:
    """Configuration for Kafka connection."""

    bootstrap_servers: str = "localhost:9092"
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: str | None = None
    sasl_username: str | None = None
    sasl_password: str | None = None
    ssl_cafile: str | None = None
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None
    client_id: str = "dazzle"
    dlq_suffix: str = ".dlq"
    default_partitions: int = 3
    default_replication_factor: int = 1
    consumer_timeout_ms: int = 1000
    max_poll_records: int = 100

    @classmethod
    def from_env(cls) -> KafkaConfig:
        """Load configuration from environment variables."""
        return cls(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            security_protocol=os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
            sasl_mechanism=os.getenv("KAFKA_SASL_MECHANISM"),
            sasl_username=os.getenv("KAFKA_SASL_USERNAME"),
            sasl_password=os.getenv("KAFKA_SASL_PASSWORD"),
            ssl_cafile=os.getenv("KAFKA_SSL_CAFILE"),
            ssl_certfile=os.getenv("KAFKA_SSL_CERTFILE"),
            ssl_keyfile=os.getenv("KAFKA_SSL_KEYFILE"),
            client_id=os.getenv("KAFKA_CLIENT_ID", "dazzle"),
            dlq_suffix=os.getenv("KAFKA_DLQ_SUFFIX", ".dlq"),
            default_partitions=int(os.getenv("KAFKA_DEFAULT_PARTITIONS", "3")),
            default_replication_factor=int(os.getenv("KAFKA_DEFAULT_REPLICATION_FACTOR", "1")),
        )

    def get_common_config(self) -> dict[str, Any]:
        """Get common Kafka configuration for producer/consumer."""
        config: dict[str, Any] = {
            "bootstrap_servers": self.bootstrap_servers,
            "security_protocol": self.security_protocol,
            "client_id": self.client_id,
        }

        if self.sasl_mechanism:
            config["sasl_mechanism"] = self.sasl_mechanism
        if self.sasl_username:
            config["sasl_plain_username"] = self.sasl_username
        if self.sasl_password:
            config["sasl_plain_password"] = self.sasl_password
        if self.ssl_cafile:
            config["ssl_context"] = self._create_ssl_context()

        return config

    def _create_ssl_context(self) -> Any:
        """Create SSL context for Kafka connection."""
        import ssl

        ctx = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH,
            cafile=self.ssl_cafile,
        )
        if self.ssl_certfile and self.ssl_keyfile:
            ctx.load_cert_chain(
                certfile=self.ssl_certfile,
                keyfile=self.ssl_keyfile,
            )
        return ctx


@dataclass
class ActiveSubscription:
    """An active subscription in the broker."""

    topic: str
    group_id: str
    handler: EventHandler
    consumer: Any  # AIOKafkaConsumer
    task: asyncio.Task[None] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class KafkaBus(EventBus):
    """
    Kafka-backed EventBus implementation for production.

    Uses aiokafka for async Kafka access. Connects to an existing
    Kafka cluster specified via configuration.

    Example:
        config = KafkaConfig.from_env()
        async with KafkaBus(config) as bus:
            await bus.publish("app.Order", envelope)

            async def handler(event):
                print(f"Received: {event.event_type}")

            await bus.subscribe("app.Order", "my-consumer", handler)
    """

    def __init__(
        self,
        config: KafkaConfig | None = None,
    ) -> None:
        """
        Initialize the Kafka bus.

        Args:
            config: Kafka configuration. If None, loads from environment.
        """
        _check_kafka_available()

        self._config = config or KafkaConfig.from_env()
        self._producer: AIOKafkaProducer | None = None
        self._admin: AIOKafkaAdminClient | None = None
        self._subscriptions: dict[tuple[str, str], ActiveSubscription] = {}
        self._lock = asyncio.Lock()
        self._started = False

        # Track pending acks for manual offset commit
        self._pending_offsets: dict[tuple[str, str], dict[int, int]] = {}

    async def start(self) -> None:
        """Start the Kafka bus (connect producer and admin client)."""
        if self._started:
            return

        common_config = self._config.get_common_config()

        # Start producer
        self._producer = AIOKafkaProducer(
            **common_config,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",  # Wait for all replicas
            enable_idempotence=True,  # Exactly-once semantics for producer
        )
        await self._producer.start()

        # Start admin client for topic management
        self._admin = AIOKafkaAdminClient(**common_config)
        await self._admin.start()

        self._started = True
        logger.info(f"KafkaBus started, connected to {self._config.bootstrap_servers}")

    async def stop(self) -> None:
        """Stop the Kafka bus (disconnect all clients)."""
        if not self._started:
            return

        # Stop all subscriptions
        for key in list(self._subscriptions.keys()):
            topic, group_id = key
            await self.unsubscribe(topic, group_id)

        # Stop producer
        if self._producer:
            await self._producer.stop()
            self._producer = None

        # Stop admin client
        if self._admin:
            await self._admin.close()
            self._admin = None

        self._started = False
        logger.info("KafkaBus stopped")

    async def __aenter__(self) -> KafkaBus:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.stop()

    def _ensure_started(self) -> None:
        """Ensure the bus is started."""
        if not self._started:
            raise EventBusError("KafkaBus not started. Call start() first.")

    async def _ensure_topic_exists(self, topic: str) -> None:
        """Ensure a topic exists, creating it if necessary."""
        if not self._admin:
            return

        try:
            new_topic = NewTopic(
                name=topic,
                num_partitions=self._config.default_partitions,
                replication_factor=self._config.default_replication_factor,
            )
            await self._admin.create_topics([new_topic])
            logger.info(f"Created topic: {topic}")
        except TopicAlreadyExistsError:
            pass  # Topic already exists
        except Exception as e:
            logger.warning(f"Could not create topic {topic}: {e}")

    def _dlq_topic(self, topic: str) -> str:
        """Get the DLQ topic name for a topic."""
        return f"{topic}{self._config.dlq_suffix}"

    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope,
        *,
        transactional: bool = False,
    ) -> None:
        """Publish an event to a topic."""
        self._ensure_started()

        if transactional:
            # For transactional publishing, use the outbox pattern
            # This should be handled by the OutboxPublisher
            raise NotImplementedError(
                "Transactional publishing via outbox is handled by OutboxPublisher"
            )

        if not self._producer:
            raise PublishError(topic, "Producer not initialized")

        # Ensure topic exists
        await self._ensure_topic_exists(topic)

        try:
            # Serialize envelope to JSON
            message = {
                "event_id": str(envelope.event_id),
                "event_type": envelope.event_type,
                "event_version": envelope.event_version,
                "key": envelope.key,
                "payload": envelope.payload,
                "headers": envelope.headers,
                "correlation_id": envelope.correlation_id,
                "causation_id": envelope.causation_id,
                "timestamp": envelope.timestamp.isoformat(),
                "producer": envelope.producer,
            }

            await self._producer.send_and_wait(
                topic=topic,
                key=envelope.key,
                value=message,
            )

            logger.debug(f"Published event {envelope.event_id} to {topic}")

        except KafkaError as e:
            raise PublishError(topic, str(e)) from e

    async def subscribe(
        self,
        topic: str,
        group_id: str,
        handler: EventHandler,
    ) -> SubscriptionInfo:
        """Subscribe to events from a topic."""
        self._ensure_started()

        key = (topic, group_id)
        async with self._lock:
            if key in self._subscriptions:
                raise SubscriptionError(topic, group_id, "Subscription already exists")

            # Ensure topic exists
            await self._ensure_topic_exists(topic)

            # Create consumer
            common_config = self._config.get_common_config()
            consumer = AIOKafkaConsumer(
                topic,
                **common_config,
                group_id=group_id,
                enable_auto_commit=False,  # Manual commit for at-least-once
                auto_offset_reset="earliest",
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                max_poll_records=self._config.max_poll_records,
            )
            await consumer.start()

            # Create subscription record
            sub = ActiveSubscription(
                topic=topic,
                group_id=group_id,
                handler=handler,
                consumer=consumer,
            )

            # Start consumer task
            sub.task = asyncio.create_task(
                self._consume_loop(sub),
                name=f"kafka-consumer-{topic}-{group_id}",
            )

            self._subscriptions[key] = sub
            self._pending_offsets[key] = {}

            logger.info(f"Subscribed to {topic} as group {group_id}")

            return SubscriptionInfo(
                topic=topic,
                group_id=group_id,
                handler=handler,
                created_at=sub.created_at,
            )

    async def _consume_loop(self, sub: ActiveSubscription) -> None:
        """Consumer loop for a subscription."""
        consumer = sub.consumer
        key = (sub.topic, sub.group_id)

        try:
            async for msg in consumer:
                try:
                    # Parse envelope from message
                    data = msg.value
                    envelope = EventEnvelope(
                        event_id=UUID(data["event_id"]),
                        event_type=data["event_type"],
                        event_version=data.get("event_version", "1.0"),
                        key=data["key"],
                        payload=data["payload"],
                        headers=data.get("headers", {}),
                        correlation_id=data.get("correlation_id"),
                        causation_id=data.get("causation_id"),
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        producer=data.get("producer", "unknown"),
                    )

                    # Track offset for later commit
                    self._pending_offsets[key][msg.partition] = msg.offset

                    # Call handler
                    await sub.handler(envelope)

                    # Handler succeeded, ack the message
                    await self.ack(sub.topic, sub.group_id, envelope.event_id)

                except Exception as e:
                    logger.error(f"Error processing message in {sub.topic}/{sub.group_id}: {e}")
                    # Nack with retryable error
                    try:
                        envelope_id = UUID(msg.value.get("event_id", ""))
                        await self.nack(
                            sub.topic,
                            sub.group_id,
                            envelope_id,
                            NackReason.handler_error(str(e)),
                        )
                    except Exception:
                        pass  # Best effort nack

        except asyncio.CancelledError:
            logger.info(f"Consumer loop cancelled for {sub.topic}/{sub.group_id}")
        except Exception as e:
            logger.error(f"Consumer loop error for {sub.topic}/{sub.group_id}: {e}")

    async def unsubscribe(
        self,
        topic: str,
        group_id: str,
    ) -> None:
        """Unsubscribe a consumer group from a topic."""
        key = (topic, group_id)

        async with self._lock:
            if key not in self._subscriptions:
                raise ConsumerNotFoundError(topic, group_id)

            sub = self._subscriptions[key]

            # Cancel consumer task
            if sub.task:
                sub.task.cancel()
                try:
                    await sub.task
                except asyncio.CancelledError:
                    pass

            # Stop consumer
            await sub.consumer.stop()

            # Remove subscription
            del self._subscriptions[key]
            if key in self._pending_offsets:
                del self._pending_offsets[key]

            logger.info(f"Unsubscribed {group_id} from {topic}")

    async def ack(
        self,
        topic: str,
        group_id: str,
        event_id: UUID,
    ) -> None:
        """Acknowledge successful processing of an event."""
        key = (topic, group_id)

        if key not in self._subscriptions:
            raise ConsumerNotFoundError(topic, group_id)

        sub = self._subscriptions[key]
        consumer = sub.consumer

        # Commit offsets for all partitions
        if key in self._pending_offsets and self._pending_offsets[key]:
            offsets = {
                TopicPartition(topic, partition): offset + 1
                for partition, offset in self._pending_offsets[key].items()
            }
            await consumer.commit(offsets)
            self._pending_offsets[key].clear()

    async def nack(
        self,
        topic: str,
        group_id: str,
        event_id: UUID,
        reason: NackReason,
    ) -> None:
        """Reject an event, moving it to DLQ if not retryable."""
        key = (topic, group_id)

        if key not in self._subscriptions:
            raise ConsumerNotFoundError(topic, group_id)

        if not reason.retryable:
            # Move to DLQ
            dlq_topic = self._dlq_topic(topic)
            await self._ensure_topic_exists(dlq_topic)

            if self._producer:
                dlq_message = {
                    "event_id": str(event_id),
                    "original_topic": topic,
                    "group_id": group_id,
                    "reason_code": reason.code,
                    "reason_message": reason.message,
                    "reason_metadata": reason.metadata,
                    "timestamp": datetime.now(UTC).isoformat(),
                }

                await self._producer.send_and_wait(
                    topic=dlq_topic,
                    key=str(event_id),
                    value=dlq_message,
                )

                logger.warning(f"Moved event {event_id} to DLQ: {reason.message}")

            # Still commit offset to avoid reprocessing
            await self.ack(topic, group_id, event_id)
        else:
            # For retryable errors, don't commit - will be redelivered
            logger.warning(f"Event {event_id} will be retried: {reason.message}")

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
        """Replay events from a topic."""
        self._ensure_started()

        common_config = self._config.get_common_config()

        # Create a temporary consumer for replay
        consumer = AIOKafkaConsumer(
            topic,
            **common_config,
            group_id=None,  # No group - manual assignment
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )
        await consumer.start()

        try:
            # Get partitions for topic
            partitions = consumer.partitions_for_topic(topic)
            if not partitions:
                return

            # Assign all partitions
            tps = [TopicPartition(topic, p) for p in partitions]
            consumer.assign(tps)

            # Seek to start position
            if from_offset is not None:
                for tp in tps:
                    consumer.seek(tp, from_offset)
            elif from_timestamp is not None:
                # Seek to timestamp
                offsets = await consumer.offsets_for_times(
                    {tp: int(from_timestamp.timestamp() * 1000) for tp in tps}
                )
                for tp, offset_time in offsets.items():
                    if offset_time:
                        consumer.seek(tp, offset_time.offset)
            else:
                # Seek to beginning
                await consumer.seek_to_beginning(*tps)

            # Consume and yield events
            async for msg in consumer:
                # Check end condition
                if to_offset is not None and msg.offset >= to_offset:
                    break
                if to_timestamp is not None:
                    msg_time = datetime.fromtimestamp(msg.timestamp / 1000, tz=UTC)
                    if msg_time >= to_timestamp:
                        break

                # Parse envelope
                data = msg.value
                envelope = EventEnvelope(
                    event_id=UUID(data["event_id"]),
                    event_type=data["event_type"],
                    event_version=data.get("event_version", "1.0"),
                    key=data["key"],
                    payload=data["payload"],
                    headers=data.get("headers", {}),
                    correlation_id=data.get("correlation_id"),
                    causation_id=data.get("causation_id"),
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    producer=data.get("producer", "unknown"),
                )

                # Apply key filter
                if key_filter and envelope.key != key_filter:
                    continue

                yield envelope

        finally:
            await consumer.stop()

    async def get_consumer_status(
        self,
        topic: str,
        group_id: str,
    ) -> ConsumerStatus:
        """Get status information for a consumer group."""
        key = (topic, group_id)

        if key not in self._subscriptions:
            raise ConsumerNotFoundError(topic, group_id)

        sub = self._subscriptions[key]
        consumer = sub.consumer

        # Get lag info
        partitions = consumer.partitions_for_topic(topic) or set()
        total_lag = 0

        for partition in partitions:
            tp = TopicPartition(topic, partition)
            position = await consumer.position(tp)
            end_offsets = await consumer.end_offsets([tp])
            end_offset = end_offsets.get(tp, position)
            total_lag += max(0, end_offset - position)

        # Get current position (approximate)
        current_offset = 0
        for partition in partitions:
            tp = TopicPartition(topic, partition)
            pos = await consumer.position(tp)
            current_offset = max(current_offset, pos)

        return ConsumerStatus(
            topic=topic,
            group_id=group_id,
            last_offset=current_offset,
            pending_count=total_lag,
            last_processed_at=sub.created_at,  # Approximate
        )

    async def list_topics(self) -> list[str]:
        """List all topics in the bus."""
        self._ensure_started()

        if not self._admin:
            return []

        topics = await self._admin.list_topics()

        # Filter out internal topics
        return [t for t in topics if not t.startswith("_") and not t.startswith("__")]

    async def list_consumer_groups(self, topic: str) -> list[str]:
        """List all consumer groups for a topic."""
        self._ensure_started()

        if not self._admin:
            return []

        # Get consumer groups from admin
        groups = await self._admin.list_consumer_groups()

        # Filter to groups subscribed to this topic
        result = []
        for group in groups:
            group_id = group.group_id
            try:
                offsets = await self._admin.list_consumer_group_offsets(group_id)
                for tp in offsets.keys():
                    if tp.topic == topic:
                        result.append(group_id)
                        break
            except Exception:
                pass

        return result

    async def get_topic_info(self, topic: str) -> dict[str, Any]:
        """Get information about a topic."""
        self._ensure_started()

        if not self._admin:
            return {"error": "Admin client not available"}

        try:
            # Get topic metadata
            metadata = await self._admin.describe_topics([topic])
            topic_metadata = metadata.get(topic)

            if not topic_metadata:
                raise TopicNotFoundError(topic)

            partitions = len(topic_metadata.partitions)

            # Get consumer groups
            groups = await self.list_consumer_groups(topic)

            return {
                "topic": topic,
                "partitions": partitions,
                "consumer_groups": groups,
                "dlq_topic": self._dlq_topic(topic),
            }

        except Exception as e:
            return {"error": str(e)}


# Factory function for creating KafkaBus from environment
def create_kafka_bus() -> KafkaBus:
    """Create a KafkaBus instance from environment configuration."""
    config = KafkaConfig.from_env()
    return KafkaBus(config)
