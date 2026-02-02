"""
Unit tests for channel provider detection framework (v0.9.0).

Tests provider detection, resolver logic, and fallback behavior.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

from dazzle.core.ir import ChannelKind, ChannelSpec
from dazzle_back.channels import (
    ChannelConfigError,
    ChannelResolution,
    ChannelResolver,
    DetectionResult,
    ProviderStatus,
)
from dazzle_back.channels.providers import (
    FileEmailDetector,
    InMemoryQueueDetector,
    InMemoryStreamDetector,
    MailpitDetector,
    RabbitMQDetector,
    RedisDetector,
    SendGridDetector,
)


class TestDetectionResult:
    """Tests for DetectionResult dataclass."""

    def test_detection_result_creation(self):
        """Test creating a detection result."""
        result = DetectionResult(
            provider_name="mailpit",
            status=ProviderStatus.AVAILABLE,
            connection_url="smtp://localhost:1025",
            api_url="http://localhost:8025/api",
            management_url="http://localhost:8025",
            detection_method="docker",
            latency_ms=5.2,
            metadata={"version": "1.12.1"},
        )

        assert result.provider_name == "mailpit"
        assert result.status == ProviderStatus.AVAILABLE
        assert result.connection_url == "smtp://localhost:1025"
        assert result.detection_method == "docker"
        assert result.latency_ms == 5.2
        assert result.metadata["version"] == "1.12.1"

    def test_detection_result_to_dict(self):
        """Test conversion to dictionary."""
        result = DetectionResult(
            provider_name="mailpit",
            status=ProviderStatus.AVAILABLE,
            connection_url="smtp://localhost:1025",
        )

        d = result.to_dict()
        assert d["provider_name"] == "mailpit"
        assert d["status"] == "available"
        assert d["connection_url"] == "smtp://localhost:1025"


class TestMailpitDetector:
    """Tests for Mailpit detector."""

    @pytest.mark.asyncio
    async def test_mailpit_properties(self):
        """Test Mailpit detector properties."""
        detector = MailpitDetector()
        assert detector.provider_name == "mailpit"
        assert detector.channel_kind == "email"
        assert detector.priority == 10

    @pytest.mark.asyncio
    async def test_mailpit_detect_via_env(self):
        """Test Mailpit detection via environment variable."""
        detector = MailpitDetector()

        with patch.dict(os.environ, {"DAZZLE_EMAIL_PROVIDER": "mailpit"}):
            with patch.object(detector, "health_check", new_callable=AsyncMock, return_value=True):
                result = await detector.detect()

        assert result is not None
        assert result.provider_name == "mailpit"
        assert result.detection_method == "explicit"

    @pytest.mark.asyncio
    async def test_mailpit_detect_via_docker(self):
        """Test Mailpit detection via Docker."""
        detector = MailpitDetector()

        mock_container = {
            "image": "axllent/mailpit:latest",
            "name": "mailpit",
            "ports": "0.0.0.0:1025->1025/tcp, 0.0.0.0:8025->8025/tcp",
            "port_mappings": {1025: 1025, 8025: 8025},
        }

        with patch(
            "dazzle_back.channels.providers.email.check_docker_container",
            new_callable=AsyncMock,
            return_value=mock_container,
        ):
            with patch.object(detector, "health_check", new_callable=AsyncMock, return_value=True):
                result = await detector.detect()

        assert result is not None
        assert result.provider_name == "mailpit"
        assert result.detection_method == "docker"
        assert "container" in result.metadata

    @pytest.mark.asyncio
    async def test_mailpit_detect_via_port(self):
        """Test Mailpit detection via port scan."""
        detector = MailpitDetector()

        with patch(
            "dazzle_back.channels.providers.email.check_docker_container",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "dazzle_back.channels.providers.email.check_port",
                new_callable=AsyncMock,
                return_value=True,
            ):
                with patch.object(
                    detector, "health_check", new_callable=AsyncMock, return_value=True
                ):
                    result = await detector.detect()

        assert result is not None
        assert result.provider_name == "mailpit"
        assert result.detection_method == "port"

    @pytest.mark.asyncio
    async def test_mailpit_not_detected(self):
        """Test when Mailpit is not found."""
        detector = MailpitDetector()

        with patch(
            "dazzle_back.channels.providers.email.check_docker_container",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "dazzle_back.channels.providers.email.check_port",
                new_callable=AsyncMock,
                return_value=False,
            ):
                result = await detector.detect()

        assert result is None


class TestSendGridDetector:
    """Tests for SendGrid detector."""

    @pytest.mark.asyncio
    async def test_sendgrid_properties(self):
        """Test SendGrid detector properties."""
        detector = SendGridDetector()
        assert detector.provider_name == "sendgrid"
        assert detector.channel_kind == "email"
        assert detector.priority == 50

    @pytest.mark.asyncio
    async def test_sendgrid_detect_with_api_key(self):
        """Test SendGrid detection with API key."""
        detector = SendGridDetector()

        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test_key_1234567890"}):
            result = await detector.detect()

        assert result is not None
        assert result.provider_name == "sendgrid"
        assert result.detection_method == "env"
        assert result.api_url == "https://api.sendgrid.com/v3"

    @pytest.mark.asyncio
    async def test_sendgrid_not_detected_without_key(self):
        """Test SendGrid not detected without API key."""
        detector = SendGridDetector()

        with patch.dict(os.environ, {}, clear=True):
            # Ensure SENDGRID_API_KEY is not set
            os.environ.pop("SENDGRID_API_KEY", None)
            result = await detector.detect()

        assert result is None


class TestFileEmailDetector:
    """Tests for file-based email detector."""

    @pytest.mark.asyncio
    async def test_file_detector_always_available(self):
        """Test file detector is always available."""
        detector = FileEmailDetector()
        result = await detector.detect()

        assert result is not None
        assert result.provider_name == "file"
        assert result.status == ProviderStatus.AVAILABLE
        assert result.detection_method == "fallback"
        assert "directory" in result.metadata

    @pytest.mark.asyncio
    async def test_file_detector_health_check(self):
        """Test file detector health check always passes."""
        detector = FileEmailDetector()
        result = await detector.detect()

        healthy = await detector.health_check(result)
        assert healthy is True


class TestRabbitMQDetector:
    """Tests for RabbitMQ detector."""

    @pytest.mark.asyncio
    async def test_rabbitmq_properties(self):
        """Test RabbitMQ detector properties."""
        detector = RabbitMQDetector()
        assert detector.provider_name == "rabbitmq"
        assert detector.channel_kind == "queue"

    @pytest.mark.asyncio
    async def test_rabbitmq_detect_via_url(self):
        """Test RabbitMQ detection via URL."""
        detector = RabbitMQDetector()

        with patch.dict(os.environ, {"RABBITMQ_URL": "amqp://guest:guest@localhost:5672"}):
            result = await detector.detect()

        assert result is not None
        assert result.provider_name == "rabbitmq"
        assert result.detection_method == "env"


class TestRedisDetector:
    """Tests for Redis detector."""

    @pytest.mark.asyncio
    async def test_redis_properties(self):
        """Test Redis detector properties."""
        detector = RedisDetector()
        assert detector.provider_name == "redis"
        assert detector.channel_kind == "stream"

    @pytest.mark.asyncio
    async def test_redis_detect_via_url(self):
        """Test Redis detection via URL."""
        detector = RedisDetector()

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            result = await detector.detect()

        assert result is not None
        assert result.provider_name == "redis"
        assert result.detection_method == "env"


class TestInMemoryDetectors:
    """Tests for in-memory fallback detectors."""

    @pytest.mark.asyncio
    async def test_memory_queue_always_available(self):
        """Test memory queue is always available."""
        detector = InMemoryQueueDetector()
        result = await detector.detect()

        assert result is not None
        assert result.provider_name == "memory_queue"
        assert result.status == ProviderStatus.AVAILABLE
        assert result.detection_method == "fallback"

    @pytest.mark.asyncio
    async def test_memory_stream_always_available(self):
        """Test memory stream is always available."""
        detector = InMemoryStreamDetector()
        result = await detector.detect()

        assert result is not None
        assert result.provider_name == "memory_stream"
        assert result.status == ProviderStatus.AVAILABLE
        assert result.detection_method == "fallback"


class TestChannelResolver:
    """Tests for channel resolver."""

    @pytest.fixture
    def resolver(self):
        """Create a resolver instance."""
        return ChannelResolver()

    @pytest.fixture
    def email_channel_spec(self):
        """Create an email channel spec."""
        return ChannelSpec(
            name="notifications",
            kind=ChannelKind.EMAIL,
            provider="auto",
        )

    @pytest.fixture
    def queue_channel_spec(self):
        """Create a queue channel spec."""
        return ChannelSpec(
            name="tasks",
            kind=ChannelKind.QUEUE,
            provider="auto",
        )

    @pytest.mark.asyncio
    async def test_resolver_returns_fallback_for_email(self, resolver, email_channel_spec):
        """Test resolver returns file fallback for email when nothing else available."""
        # Mock all detectors to return None or fail health check
        for detector in resolver._detectors["email"]:
            if detector.provider_name != "file":
                detector.detect = AsyncMock(return_value=None)

        resolution = await resolver.resolve(email_channel_spec)

        assert resolution is not None
        assert resolution.channel_name == "notifications"
        assert resolution.channel_kind == "email"
        assert resolution.provider.provider_name == "file"
        assert resolution.provider.detection_method == "fallback"

    @pytest.mark.asyncio
    async def test_resolver_returns_fallback_for_queue(self, resolver, queue_channel_spec):
        """Test resolver returns memory fallback for queue when nothing else available."""
        # Mock RabbitMQ detector to return None
        for detector in resolver._detectors["queue"]:
            if detector.provider_name != "memory_queue":
                detector.detect = AsyncMock(return_value=None)

        resolution = await resolver.resolve(queue_channel_spec)

        assert resolution is not None
        assert resolution.channel_name == "tasks"
        assert resolution.channel_kind == "queue"
        assert resolution.provider.provider_name == "memory_queue"

    @pytest.mark.asyncio
    async def test_resolver_explicit_provider_not_found(self, resolver):
        """Test resolver raises error for unavailable explicit provider."""
        spec = ChannelSpec(
            name="notifications",
            kind=ChannelKind.EMAIL,
            provider="nonexistent_provider",
        )

        with pytest.raises(ChannelConfigError) as exc_info:
            await resolver.resolve(spec)

        assert "nonexistent_provider" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_resolver_caching(self, resolver, email_channel_spec):
        """Test resolver caches resolutions."""
        # First resolution
        resolution1 = await resolver.resolve(email_channel_spec)

        # Second resolution should be cached
        resolution2 = await resolver.resolve(email_channel_spec)

        assert resolution1 is resolution2
        assert len(resolver._cache) == 1

    @pytest.mark.asyncio
    async def test_resolver_clear_cache(self, resolver, email_channel_spec):
        """Test clearing resolver cache."""
        await resolver.resolve(email_channel_spec)
        assert len(resolver._cache) == 1

        resolver.clear_cache()
        assert len(resolver._cache) == 0

    @pytest.mark.asyncio
    async def test_resolver_resolve_all(self, resolver):
        """Test resolving multiple channels."""
        specs = [
            ChannelSpec(name="emails", kind=ChannelKind.EMAIL, provider="auto"),
            ChannelSpec(name="tasks", kind=ChannelKind.QUEUE, provider="auto"),
            ChannelSpec(name="events", kind=ChannelKind.STREAM, provider="auto"),
        ]

        # Mock detectors to return fallbacks
        for kind in resolver._detectors:
            for detector in resolver._detectors[kind]:
                if "memory" not in detector.provider_name and detector.provider_name != "file":
                    detector.detect = AsyncMock(return_value=None)

        resolutions = await resolver.resolve_all(specs)

        assert len(resolutions) == 3
        assert resolutions[0].channel_name == "emails"
        assert resolutions[1].channel_name == "tasks"
        assert resolutions[2].channel_name == "events"

    @pytest.mark.asyncio
    async def test_resolver_status_summary(self, resolver, email_channel_spec):
        """Test getting status summary."""
        await resolver.resolve(email_channel_spec)

        summary = resolver.get_status_summary()
        assert len(summary) == 1
        assert summary[0]["channel_name"] == "notifications"
        assert "provider" in summary[0]


class TestChannelResolution:
    """Tests for ChannelResolution dataclass."""

    def test_channel_resolution_creation(self):
        """Test creating a channel resolution."""
        result = DetectionResult(
            provider_name="mailpit",
            status=ProviderStatus.AVAILABLE,
            connection_url="smtp://localhost:1025",
        )

        resolution = ChannelResolution(
            channel_name="notifications",
            channel_kind="email",
            provider=result,
            adapter_class_name="MailpitAdapter",
        )

        assert resolution.channel_name == "notifications"
        assert resolution.channel_kind == "email"
        assert resolution.provider.provider_name == "mailpit"
        assert resolution.adapter_class_name == "MailpitAdapter"

    def test_channel_resolution_to_dict(self):
        """Test conversion to dictionary."""
        result = DetectionResult(
            provider_name="mailpit",
            status=ProviderStatus.AVAILABLE,
        )

        resolution = ChannelResolution(
            channel_name="notifications",
            channel_kind="email",
            provider=result,
        )

        d = resolution.to_dict()
        assert d["channel_name"] == "notifications"
        assert d["channel_kind"] == "email"
        assert d["provider"]["provider_name"] == "mailpit"
