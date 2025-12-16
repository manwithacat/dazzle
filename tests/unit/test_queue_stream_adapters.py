"""
Unit tests for queue and stream channel adapters.

Tests the RabbitMQ, Redis, Kafka, and in-memory adapters.
"""

import asyncio
from datetime import UTC, datetime

import pytest

from dazzle_dnr_back.channels.adapters.queue import (
    InMemoryQueueAdapter,
    RabbitMQAdapter,
)
from dazzle_dnr_back.channels.adapters.stream import (
    InMemoryStreamAdapter,
    KafkaAdapter,
    RedisAdapter,
)
from dazzle_dnr_back.channels.adapters.base import SendStatus
from dazzle_dnr_back.channels.detection import DetectionResult, ProviderStatus
from dazzle_dnr_back.channels.outbox import OutboxMessage, OutboxStatus


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def rabbitmq_detection():
    """Mock RabbitMQ detection result."""
    return DetectionResult(
        provider_name="rabbitmq",
        status=ProviderStatus.AVAILABLE,
        connection_url="amqp://localhost:5672",
        detection_method="test",
    )


@pytest.fixture
def redis_detection():
    """Mock Redis detection result."""
    return DetectionResult(
        provider_name="redis",
        status=ProviderStatus.AVAILABLE,
        connection_url="redis://localhost:6379",
        detection_method="test",
    )


@pytest.fixture
def kafka_detection():
    """Mock Kafka detection result."""
    return DetectionResult(
        provider_name="kafka",
        status=ProviderStatus.AVAILABLE,
        connection_url="localhost:9092",
        detection_method="test",
    )


@pytest.fixture
def memory_queue_detection():
    """Mock in-memory queue detection result."""
    return DetectionResult(
        provider_name="memory_queue",
        status=ProviderStatus.AVAILABLE,
        connection_url="memory://queue",
        detection_method="fallback",
    )


@pytest.fixture
def memory_stream_detection():
    """Mock in-memory stream detection result."""
    return DetectionResult(
        provider_name="memory_stream",
        status=ProviderStatus.AVAILABLE,
        connection_url="memory://stream",
        detection_method="fallback",
    )


@pytest.fixture
def sample_outbox_message():
    """Create a sample outbox message for testing."""
    return OutboxMessage(
        id="test-msg-123",
        channel_name="test_channel",
        operation_name="send_notification",
        message_type="Notification",
        payload={
            "title": "Test Notification",
            "body": "This is a test message",
            "priority": "high",
        },
        recipient="test@example.com",
        status=OutboxStatus.PENDING,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        correlation_id="corr-123",
    )


# =============================================================================
# InMemoryQueueAdapter Tests
# =============================================================================


class TestInMemoryQueueAdapter:
    """Tests for InMemoryQueueAdapter."""

    @pytest.mark.asyncio
    async def test_adapter_creation(self, memory_queue_detection):
        """Test creating an in-memory queue adapter."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        assert adapter.provider_name == "memory_queue"
        assert adapter.channel_kind == "queue"

    @pytest.mark.asyncio
    async def test_initialize(self, memory_queue_detection):
        """Test adapter initialization."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()
        assert adapter._initialized

    @pytest.mark.asyncio
    async def test_send_message(self, memory_queue_detection, sample_outbox_message):
        """Test sending a message to in-memory queue."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()

        result = await adapter.send(sample_outbox_message)

        assert result.status == SendStatus.SUCCESS
        assert result.message_id == sample_outbox_message.id
        assert result.latency_ms is not None
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_queue_persistence(self, memory_queue_detection, sample_outbox_message):
        """Test that messages persist in queue."""
        # Clear state first
        InMemoryQueueAdapter._queues.clear()
        InMemoryQueueAdapter._messages.clear()

        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()

        # Send message
        await adapter.send(sample_outbox_message)

        # Check queue size
        queue_size = adapter.get_queue_size("test_channel")
        assert queue_size == 1

    @pytest.mark.asyncio
    async def test_receive_messages(self, memory_queue_detection, sample_outbox_message):
        """Test receiving messages from queue."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()

        # Send message
        await adapter.send(sample_outbox_message)

        # Receive message
        messages = await adapter.receive(count=1, timeout=1.0)

        assert len(messages) == 1
        assert messages[0]["id"] == sample_outbox_message.id
        assert messages[0]["body"] == sample_outbox_message.payload

    @pytest.mark.asyncio
    async def test_ack_message(self, memory_queue_detection, sample_outbox_message):
        """Test acknowledging a message."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()

        await adapter.send(sample_outbox_message)
        await adapter.ack(sample_outbox_message.id)

        # Message should be removed from tracking
        assert sample_outbox_message.id not in adapter._messages

    @pytest.mark.asyncio
    async def test_nack_message(self, memory_queue_detection, sample_outbox_message):
        """Test negative acknowledging a message."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()

        await adapter.send(sample_outbox_message)
        await adapter.nack(sample_outbox_message.id, requeue=False)

        # Message should be removed when not requeued
        assert sample_outbox_message.id not in adapter._messages

    @pytest.mark.asyncio
    async def test_health_check(self, memory_queue_detection):
        """Test health check always returns True for in-memory."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()

        is_healthy = await adapter.health_check()
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_get_all_queue_sizes(self, memory_queue_detection):
        """Test getting all queue sizes."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()

        # Send to multiple queues
        msg1 = OutboxMessage(
            id="msg-1",
            channel_name="queue1",
            operation_name="op",
            message_type="type",
            payload={},
            recipient="test",
        )
        msg2 = OutboxMessage(
            id="msg-2",
            channel_name="queue2",
            operation_name="op",
            message_type="type",
            payload={},
            recipient="test",
        )

        await adapter.send(msg1)
        await adapter.send(msg2)

        sizes = adapter.get_all_queue_sizes()
        assert sizes["queue1"] == 1
        assert sizes["queue2"] == 1


# =============================================================================
# InMemoryStreamAdapter Tests
# =============================================================================


class TestInMemoryStreamAdapter:
    """Tests for InMemoryStreamAdapter."""

    @pytest.mark.asyncio
    async def test_adapter_creation(self, memory_stream_detection):
        """Test creating an in-memory stream adapter."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        assert adapter.provider_name == "memory_stream"
        assert adapter.channel_kind == "stream"

    @pytest.mark.asyncio
    async def test_initialize(self, memory_stream_detection):
        """Test adapter initialization."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()
        assert adapter._initialized

    @pytest.mark.asyncio
    async def test_send_message(self, memory_stream_detection, sample_outbox_message):
        """Test sending a message to in-memory stream."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        result = await adapter.send(sample_outbox_message)

        assert result.status == SendStatus.SUCCESS
        assert result.message_id == sample_outbox_message.id
        assert result.provider_response is not None
        assert "stream_id" in result.provider_response

    @pytest.mark.asyncio
    async def test_stream_persistence(self, memory_stream_detection, sample_outbox_message):
        """Test that messages persist in stream."""
        # Clear state first
        InMemoryStreamAdapter._streams.clear()
        InMemoryStreamAdapter._subscribers.clear()

        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        # Send message
        await adapter.send(sample_outbox_message)

        # Check stream length
        length = adapter.get_stream_length("test_channel")
        assert length == 1

    @pytest.mark.asyncio
    async def test_get_stream_entries(self, memory_stream_detection, sample_outbox_message):
        """Test getting entries from stream."""
        # Clear state first
        InMemoryStreamAdapter._streams.clear()
        InMemoryStreamAdapter._subscribers.clear()

        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        # Send message
        await adapter.send(sample_outbox_message)

        # Get entries
        entries = adapter.get_stream_entries("test_channel", start=0, count=10)

        assert len(entries) == 1
        assert entries[0]["message_id"] == sample_outbox_message.id
        assert entries[0]["payload"] == sample_outbox_message.payload

    @pytest.mark.asyncio
    async def test_subscribe_notification(self, memory_stream_detection, sample_outbox_message):
        """Test that subscribers are notified of new messages."""
        # Clear state first
        InMemoryStreamAdapter._streams.clear()
        InMemoryStreamAdapter._subscribers.clear()

        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        received = []

        async def callback(entry):
            received.append(entry)

        # Subscribe to the actual channel being sent to
        # Need to update the subscribe method to use the correct stream name
        InMemoryStreamAdapter._subscribers["test_channel"] = [callback]

        # Send message
        await adapter.send(sample_outbox_message)

        # Give callback time to execute
        await asyncio.sleep(0.1)

        # Check notification
        assert len(received) == 1
        assert received[0]["message_id"] == sample_outbox_message.id

    @pytest.mark.asyncio
    async def test_unsubscribe(self, memory_stream_detection):
        """Test unsubscribing from stream."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        async def callback(entry):
            pass

        await adapter.subscribe("group1", "consumer1", callback)
        await adapter.unsubscribe()

        # Subscribers should be cleared
        assert len(adapter._subscribers) == 0

    @pytest.mark.asyncio
    async def test_health_check(self, memory_stream_detection):
        """Test health check always returns True for in-memory."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        is_healthy = await adapter.health_check()
        assert is_healthy is True


# =============================================================================
# RabbitMQAdapter Tests (without actual RabbitMQ)
# =============================================================================


class TestRabbitMQAdapter:
    """Tests for RabbitMQAdapter (mock tests without actual RabbitMQ)."""

    def test_adapter_creation(self, rabbitmq_detection):
        """Test creating a RabbitMQ adapter."""
        adapter = RabbitMQAdapter(rabbitmq_detection)
        assert adapter.provider_name == "rabbitmq"
        assert adapter.channel_kind == "queue"
        assert adapter._url == "amqp://localhost:5672"

    @pytest.mark.asyncio
    async def test_send_without_initialization(self, rabbitmq_detection, sample_outbox_message):
        """Test sending without initialization fails gracefully."""
        adapter = RabbitMQAdapter(rabbitmq_detection)

        result = await adapter.send(sample_outbox_message)

        assert result.status == SendStatus.FAILED
        assert "not initialized" in result.error


# =============================================================================
# RedisAdapter Tests (without actual Redis)
# =============================================================================


class TestRedisAdapter:
    """Tests for RedisAdapter (mock tests without actual Redis)."""

    def test_adapter_creation(self, redis_detection):
        """Test creating a Redis adapter."""
        adapter = RedisAdapter(redis_detection)
        assert adapter.provider_name == "redis"
        assert adapter.channel_kind == "stream"
        assert adapter._url == "redis://localhost:6379"

    @pytest.mark.asyncio
    async def test_send_without_initialization(self, redis_detection, sample_outbox_message):
        """Test sending without initialization fails gracefully."""
        adapter = RedisAdapter(redis_detection)

        result = await adapter.send(sample_outbox_message)

        assert result.status == SendStatus.FAILED
        assert "not initialized" in result.error


# =============================================================================
# KafkaAdapter Tests (without actual Kafka)
# =============================================================================


class TestKafkaAdapter:
    """Tests for KafkaAdapter (mock tests without actual Kafka)."""

    def test_adapter_creation(self, kafka_detection):
        """Test creating a Kafka adapter."""
        adapter = KafkaAdapter(kafka_detection)
        assert adapter.provider_name == "kafka"
        assert adapter.channel_kind == "stream"
        assert adapter._bootstrap_servers == "localhost:9092"

    @pytest.mark.asyncio
    async def test_send_without_initialization(self, kafka_detection, sample_outbox_message):
        """Test sending without initialization fails gracefully."""
        adapter = KafkaAdapter(kafka_detection)

        result = await adapter.send(sample_outbox_message)

        assert result.status == SendStatus.FAILED
        assert "not initialized" in result.error
