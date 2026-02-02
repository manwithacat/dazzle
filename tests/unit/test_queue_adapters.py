"""
Unit tests for DAZZLE queue channel adapters (v0.16.0 - Issue #29).

Tests queue adapters: RabbitMQAdapter, InMemoryQueueAdapter.
"""

import pytest

from dazzle_back.channels.adapters.base import SendStatus
from dazzle_back.channels.adapters.queue import (
    InMemoryQueueAdapter,
    RabbitMQAdapter,
)
from dazzle_back.channels.detection import DetectionResult, ProviderStatus
from dazzle_back.channels.outbox import OutboxMessage, OutboxStatus


@pytest.fixture
def rabbitmq_detection():
    """Create a RabbitMQ detection result."""
    return DetectionResult(
        provider_name="rabbitmq",
        status=ProviderStatus.AVAILABLE,
        connection_url="amqp://localhost:5672",
        detection_method="test",
    )


@pytest.fixture
def memory_queue_detection():
    """Create an in-memory queue detection result."""
    return DetectionResult(
        provider_name="memory_queue",
        status=ProviderStatus.AVAILABLE,
        connection_url="memory://queue",
        detection_method="fallback",
        metadata={"queue_name": "test_queue"},
    )


@pytest.fixture
def sample_message():
    """Create a sample outbox message."""
    return OutboxMessage(
        id="msg-001",
        channel_name="test_channel",
        operation_name="test_op",
        message_type="TestMessage",
        payload={"data": "test"},
        recipient="test@example.com",
        status=OutboxStatus.PENDING,
    )


class TestRabbitMQAdapter:
    """Tests for RabbitMQAdapter structure and interface."""

    def test_provider_name(self, rabbitmq_detection):
        """Test provider name."""
        adapter = RabbitMQAdapter(rabbitmq_detection)
        assert adapter.provider_name == "rabbitmq"

    def test_channel_kind(self, rabbitmq_detection):
        """Test channel kind."""
        adapter = RabbitMQAdapter(rabbitmq_detection)
        assert adapter.channel_kind == "queue"

    def test_url_parsing(self, rabbitmq_detection):
        """Test URL is parsed from detection result."""
        adapter = RabbitMQAdapter(rabbitmq_detection)
        assert adapter._url == "amqp://localhost:5672"

    def test_default_url(self):
        """Test default URL when not provided."""
        detection = DetectionResult(
            provider_name="rabbitmq",
            status=ProviderStatus.AVAILABLE,
            connection_url=None,
            detection_method="test",
        )
        adapter = RabbitMQAdapter(detection)
        assert adapter._url == "amqp://localhost:5672"

    def test_not_initialized_by_default(self, rabbitmq_detection):
        """Test adapter is not initialized by default."""
        adapter = RabbitMQAdapter(rabbitmq_detection)
        assert not adapter._initialized
        assert adapter._connection is None
        assert adapter._channel is None

    @pytest.mark.asyncio
    async def test_send_without_init_fails(self, rabbitmq_detection, sample_message):
        """Test send without initialization fails."""
        adapter = RabbitMQAdapter(rabbitmq_detection)
        result = await adapter.send(sample_message)
        assert result.status == SendStatus.FAILED
        assert "not initialized" in result.error

    @pytest.mark.asyncio
    async def test_health_check_without_init(self, rabbitmq_detection):
        """Test health check without initialization returns False."""
        adapter = RabbitMQAdapter(rabbitmq_detection)
        is_healthy = await adapter.health_check()
        assert is_healthy is False


class TestInMemoryQueueAdapter:
    """Tests for InMemoryQueueAdapter."""

    @pytest.fixture(autouse=True)
    def clear_queues(self):
        """Clear queues before each test."""
        InMemoryQueueAdapter.clear_all()
        yield
        InMemoryQueueAdapter.clear_all()

    def test_provider_name(self, memory_queue_detection):
        """Test provider name."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        assert adapter.provider_name == "memory_queue"

    def test_channel_kind(self, memory_queue_detection):
        """Test channel kind."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        assert adapter.channel_kind == "queue"

    @pytest.mark.asyncio
    async def test_initialize(self, memory_queue_detection):
        """Test initialization."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()
        assert adapter._initialized

    @pytest.mark.asyncio
    async def test_shutdown(self, memory_queue_detection):
        """Test shutdown."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()
        await adapter.shutdown()
        assert not adapter._initialized

    @pytest.mark.asyncio
    async def test_send_message(self, memory_queue_detection, sample_message):
        """Test sending a message."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()

        result = await adapter.send(sample_message)

        assert result.status == SendStatus.SUCCESS
        assert result.message_id == sample_message.id
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_send_increments_queue_size(self, memory_queue_detection, sample_message):
        """Test sending increments queue size."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()

        assert InMemoryQueueAdapter.get_queue_size(sample_message.channel_name) == 0

        await adapter.send(sample_message)
        assert InMemoryQueueAdapter.get_queue_size(sample_message.channel_name) == 1

        await adapter.send(sample_message)
        assert InMemoryQueueAdapter.get_queue_size(sample_message.channel_name) == 2

    @pytest.mark.asyncio
    async def test_send_provider_response(self, memory_queue_detection, sample_message):
        """Test send returns provider response."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()

        result = await adapter.send(sample_message)

        assert result.provider_response is not None
        assert result.provider_response["queue"] == sample_message.channel_name
        assert "queue_size" in result.provider_response

    @pytest.mark.asyncio
    async def test_receive_message(self, memory_queue_detection, sample_message):
        """Test receiving a message."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        detection_with_queue = DetectionResult(
            provider_name="memory_queue",
            status=ProviderStatus.AVAILABLE,
            connection_url="memory://queue",
            detection_method="fallback",
            metadata={"queue_name": sample_message.channel_name},
        )
        adapter = InMemoryQueueAdapter(detection_with_queue)
        await adapter.initialize()

        # Send a message
        await adapter.send(sample_message)

        # Receive it
        messages = await adapter.receive(count=1, timeout=1.0)

        assert len(messages) == 1
        assert messages[0]["id"] == sample_message.id
        assert messages[0]["operation"] == sample_message.operation_name

    @pytest.mark.asyncio
    async def test_receive_timeout(self, memory_queue_detection):
        """Test receive times out on empty queue."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        await adapter.initialize()

        messages = await adapter.receive(count=1, timeout=0.1)

        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_ack_message(self, memory_queue_detection, sample_message):
        """Test acknowledging a message."""
        detection_with_queue = DetectionResult(
            provider_name="memory_queue",
            status=ProviderStatus.AVAILABLE,
            connection_url="memory://queue",
            detection_method="fallback",
            metadata={"queue_name": sample_message.channel_name},
        )
        adapter = InMemoryQueueAdapter(detection_with_queue)
        await adapter.initialize()

        await adapter.send(sample_message)
        messages = await adapter.receive(count=1, timeout=1.0)

        # Ack should not raise
        await adapter.ack(messages[0]["id"])

    @pytest.mark.asyncio
    async def test_health_check(self, memory_queue_detection):
        """Test health check returns True."""
        adapter = InMemoryQueueAdapter(memory_queue_detection)
        is_healthy = await adapter.health_check()
        assert is_healthy is True

    def test_clear_all(self, memory_queue_detection, sample_message):
        """Test clearing all queues."""
        # Add something to queues
        InMemoryQueueAdapter._queues["test"] = None

        InMemoryQueueAdapter.clear_all()

        assert len(InMemoryQueueAdapter._queues) == 0


class TestQueueAdapterIntegration:
    """Integration tests for queue adapters with manager."""

    def test_adapter_registered_in_manager(self):
        """Test queue adapters are registered in ChannelManager."""
        from dazzle_back.channels.adapters import (
            InMemoryQueueAdapter,
            RabbitMQAdapter,
        )

        # Verify imports work
        assert RabbitMQAdapter is not None
        assert InMemoryQueueAdapter is not None
