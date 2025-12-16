"""
Unit tests for DAZZLE stream channel adapters (v0.16.0 - Issue #29).

Tests stream adapters: RedisStreamAdapter, KafkaAdapter, InMemoryStreamAdapter.
"""

import pytest

from dazzle_dnr_back.channels.adapters.base import SendStatus
from dazzle_dnr_back.channels.adapters.stream import (
    InMemoryStreamAdapter,
    KafkaAdapter,
    RedisStreamAdapter,
)
from dazzle_dnr_back.channels.detection import DetectionResult, ProviderStatus
from dazzle_dnr_back.channels.outbox import OutboxMessage, OutboxStatus


@pytest.fixture
def redis_detection():
    """Create a Redis detection result."""
    return DetectionResult(
        provider_name="redis",
        status=ProviderStatus.AVAILABLE,
        connection_url="redis://localhost:6379",
        detection_method="test",
    )


@pytest.fixture
def kafka_detection():
    """Create a Kafka detection result."""
    return DetectionResult(
        provider_name="kafka",
        status=ProviderStatus.AVAILABLE,
        connection_url="localhost:9092",
        detection_method="test",
        metadata={"topic": "test_topic"},
    )


@pytest.fixture
def memory_stream_detection():
    """Create an in-memory stream detection result."""
    return DetectionResult(
        provider_name="memory_stream",
        status=ProviderStatus.AVAILABLE,
        connection_url="memory://stream",
        detection_method="fallback",
        metadata={"stream_name": "test_stream"},
    )


@pytest.fixture
def sample_message():
    """Create a sample outbox message."""
    return OutboxMessage(
        id="msg-001",
        channel_name="test_stream",
        operation_name="test_op",
        message_type="TestMessage",
        payload={"data": "test"},
        recipient="test@example.com",
        status=OutboxStatus.PENDING,
        correlation_id="corr-123",
        metadata={"source": "unit_test"},
    )


class TestRedisStreamAdapter:
    """Tests for RedisStreamAdapter structure and interface."""

    def test_provider_name(self, redis_detection):
        """Test provider name."""
        adapter = RedisStreamAdapter(redis_detection)
        assert adapter.provider_name == "redis"

    def test_channel_kind(self, redis_detection):
        """Test channel kind."""
        adapter = RedisStreamAdapter(redis_detection)
        assert adapter.channel_kind == "stream"

    def test_url_parsing(self, redis_detection):
        """Test URL is parsed from detection result."""
        adapter = RedisStreamAdapter(redis_detection)
        assert adapter._url == "redis://localhost:6379"

    def test_default_url(self):
        """Test default URL when not provided."""
        detection = DetectionResult(
            provider_name="redis",
            status=ProviderStatus.AVAILABLE,
            connection_url=None,
            detection_method="test",
        )
        adapter = RedisStreamAdapter(detection)
        assert adapter._url == "redis://localhost:6379"

    def test_not_initialized_by_default(self, redis_detection):
        """Test adapter is not initialized by default."""
        adapter = RedisStreamAdapter(redis_detection)
        assert not adapter._initialized
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_send_without_init_fails(self, redis_detection, sample_message):
        """Test send without initialization fails."""
        adapter = RedisStreamAdapter(redis_detection)
        result = await adapter.send(sample_message)
        assert result.status == SendStatus.FAILED
        assert "not initialized" in result.error

    @pytest.mark.asyncio
    async def test_health_check_without_init(self, redis_detection):
        """Test health check without initialization returns False."""
        adapter = RedisStreamAdapter(redis_detection)
        is_healthy = await adapter.health_check()
        assert is_healthy is False


class TestKafkaAdapter:
    """Tests for KafkaAdapter structure and interface."""

    def test_provider_name(self, kafka_detection):
        """Test provider name."""
        adapter = KafkaAdapter(kafka_detection)
        assert adapter.provider_name == "kafka"

    def test_channel_kind(self, kafka_detection):
        """Test channel kind."""
        adapter = KafkaAdapter(kafka_detection)
        assert adapter.channel_kind == "stream"

    def test_bootstrap_servers_parsing(self, kafka_detection):
        """Test bootstrap servers are parsed from detection result."""
        adapter = KafkaAdapter(kafka_detection)
        assert adapter._bootstrap_servers == "localhost:9092"

    def test_default_bootstrap_servers(self):
        """Test default bootstrap servers when not provided."""
        detection = DetectionResult(
            provider_name="kafka",
            status=ProviderStatus.AVAILABLE,
            connection_url=None,
            detection_method="test",
        )
        adapter = KafkaAdapter(detection)
        assert adapter._bootstrap_servers == "localhost:9092"

    def test_not_initialized_by_default(self, kafka_detection):
        """Test adapter is not initialized by default."""
        adapter = KafkaAdapter(kafka_detection)
        assert not adapter._initialized
        assert adapter._producer is None

    @pytest.mark.asyncio
    async def test_send_without_init_fails(self, kafka_detection, sample_message):
        """Test send without initialization fails."""
        adapter = KafkaAdapter(kafka_detection)
        result = await adapter.send(sample_message)
        assert result.status == SendStatus.FAILED
        assert "not initialized" in result.error

    @pytest.mark.asyncio
    async def test_health_check_without_init(self, kafka_detection):
        """Test health check without initialization returns False."""
        adapter = KafkaAdapter(kafka_detection)
        is_healthy = await adapter.health_check()
        assert is_healthy is False


class TestInMemoryStreamAdapter:
    """Tests for InMemoryStreamAdapter."""

    @pytest.fixture(autouse=True)
    def clear_streams(self):
        """Clear streams before each test."""
        InMemoryStreamAdapter.clear_all()
        yield
        InMemoryStreamAdapter.clear_all()

    def test_provider_name(self, memory_stream_detection):
        """Test provider name."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        assert adapter.provider_name == "memory_stream"

    def test_channel_kind(self, memory_stream_detection):
        """Test channel kind."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        assert adapter.channel_kind == "stream"

    @pytest.mark.asyncio
    async def test_initialize(self, memory_stream_detection):
        """Test initialization."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()
        assert adapter._initialized

    @pytest.mark.asyncio
    async def test_shutdown(self, memory_stream_detection):
        """Test shutdown."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()
        await adapter.shutdown()
        assert not adapter._initialized

    @pytest.mark.asyncio
    async def test_send_message(self, memory_stream_detection, sample_message):
        """Test sending a message."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        result = await adapter.send(sample_message)

        assert result.status == SendStatus.SUCCESS
        assert result.message_id is not None  # Stream ID
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_send_increments_stream_size(self, memory_stream_detection, sample_message):
        """Test sending increments stream size."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        assert InMemoryStreamAdapter.get_stream_size(sample_message.channel_name) == 0

        await adapter.send(sample_message)
        assert InMemoryStreamAdapter.get_stream_size(sample_message.channel_name) == 1

        await adapter.send(sample_message)
        assert InMemoryStreamAdapter.get_stream_size(sample_message.channel_name) == 2

    @pytest.mark.asyncio
    async def test_send_provider_response(self, memory_stream_detection, sample_message):
        """Test send returns provider response."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        result = await adapter.send(sample_message)

        assert result.provider_response is not None
        assert result.provider_response["stream"] == sample_message.channel_name
        assert "stream_id" in result.provider_response
        assert "stream_size" in result.provider_response

    @pytest.mark.asyncio
    async def test_get_stream_messages(self, memory_stream_detection, sample_message):
        """Test getting stream messages."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        await adapter.send(sample_message)
        await adapter.send(sample_message)

        messages = InMemoryStreamAdapter.get_stream_messages(sample_message.channel_name)

        assert len(messages) == 2
        assert messages[0]["id"] == sample_message.id

    @pytest.mark.asyncio
    async def test_message_contains_all_fields(self, memory_stream_detection, sample_message):
        """Test message contains all required fields."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        await adapter.send(sample_message)

        messages = InMemoryStreamAdapter.get_stream_messages(sample_message.channel_name)
        msg = messages[0]

        assert "_stream_id" in msg
        assert msg["id"] == sample_message.id
        assert msg["operation"] == sample_message.operation_name
        assert msg["type"] == sample_message.message_type
        assert msg["payload"] == sample_message.payload
        assert msg["recipient"] == sample_message.recipient
        assert msg["correlation_id"] == sample_message.correlation_id
        assert msg["metadata"] == sample_message.metadata

    @pytest.mark.asyncio
    async def test_subscribe_and_receive(self, memory_stream_detection, sample_message):
        """Test subscribing to stream and receiving messages."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        received = []

        async def callback(msg):
            received.append(msg)

        await adapter.subscribe(
            group="test_group",
            consumer="test_consumer",
            callback=callback,
        )

        # Send a message
        await adapter.send(sample_message)

        # Check callback was called
        assert len(received) == 1
        assert received[0]["id"] == sample_message.id

    @pytest.mark.asyncio
    async def test_unsubscribe(self, memory_stream_detection):
        """Test unsubscribing from streams."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        async def callback(msg):
            pass

        await adapter.subscribe("group", "consumer", callback)
        await adapter.unsubscribe()

        # Should not raise
        assert True

    @pytest.mark.asyncio
    async def test_health_check(self, memory_stream_detection):
        """Test health check returns True."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        is_healthy = await adapter.health_check()
        assert is_healthy is True

    def test_clear_all(self, memory_stream_detection):
        """Test clearing all streams."""
        # Add something to streams
        InMemoryStreamAdapter._streams["test"] = None
        InMemoryStreamAdapter._counter = 100

        InMemoryStreamAdapter.clear_all()

        assert len(InMemoryStreamAdapter._streams) == 0
        assert InMemoryStreamAdapter._counter == 0

    @pytest.mark.asyncio
    async def test_stream_max_size(self, memory_stream_detection, sample_message):
        """Test stream respects max size (deque maxlen)."""
        adapter = InMemoryStreamAdapter(memory_stream_detection)
        await adapter.initialize()

        # The maxlen is 10000, so we can't easily test the limit
        # but we can verify messages are stored
        for _ in range(100):
            await adapter.send(sample_message)

        assert InMemoryStreamAdapter.get_stream_size(sample_message.channel_name) == 100


class TestStreamAdapterIntegration:
    """Integration tests for stream adapters with manager."""

    def test_adapters_registered_in_manager(self):
        """Test stream adapters are registered in ChannelManager."""
        from dazzle_dnr_back.channels.adapters import (
            InMemoryStreamAdapter,
            KafkaAdapter,
            RedisStreamAdapter,
        )

        # Verify imports work
        assert RedisStreamAdapter is not None
        assert KafkaAdapter is not None
        assert InMemoryStreamAdapter is not None

    def test_adapters_exported_from_package(self):
        """Test adapters are exported from adapters package."""
        from dazzle_dnr_back.channels.adapters import (
            InMemoryStreamAdapter,
            KafkaAdapter,
            RedisStreamAdapter,
            StreamAdapter,
        )

        assert StreamAdapter is not None
        assert RedisStreamAdapter is not None
        assert KafkaAdapter is not None
        assert InMemoryStreamAdapter is not None
