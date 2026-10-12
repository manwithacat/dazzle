"""
Unit tests for email provider detection (the email kernel kept by DD-007).
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

from dazzle.http.channels import (
    DetectionResult,
    ProviderStatus,
)
from dazzle.http.channels.providers import (
    FileEmailDetector,
    MailpitDetector,
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
            detection_method="port",
            latency_ms=5.2,
            metadata={"version": "1.12.1"},
        )

        assert result.provider_name == "mailpit"
        assert result.status == ProviderStatus.AVAILABLE
        assert result.connection_url == "smtp://localhost:1025"
        assert result.detection_method == "port"
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
    async def test_mailpit_detect_via_port(self):
        """Test Mailpit detection via port scan."""
        detector = MailpitDetector()

        with patch(
            "dazzle.http.channels.providers.email.check_port",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch.object(detector, "health_check", new_callable=AsyncMock, return_value=True):
                result = await detector.detect()

        assert result is not None
        assert result.provider_name == "mailpit"
        assert result.detection_method == "port"

    @pytest.mark.asyncio
    async def test_mailpit_not_detected(self):
        """Test when Mailpit is not found."""
        detector = MailpitDetector()

        with patch(
            "dazzle.http.channels.providers.email.check_port",
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
