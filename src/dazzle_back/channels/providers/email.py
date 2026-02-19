"""
Email provider detectors for DAZZLE messaging.

Supports:
- Mailpit (local development)
- SendGrid (production)
- File-based fallback (always available)
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from ..detection import (
    DetectionResult,
    ProviderDetector,
    ProviderStatus,
    check_docker_container,
    check_port,
    get_env_var,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("dazzle.channels.email")


class MailpitDetector(ProviderDetector):
    """Detect Mailpit for local email development.

    Detection order:
    1. Explicit env var DAZZLE_EMAIL_PROVIDER=mailpit
    2. Running Docker container with mailpit image
    3. Port 8025 (API) responding with Mailpit API
    """

    DEFAULT_SMTP_PORT = 1025
    DEFAULT_API_PORT = 8025

    @property
    def provider_name(self) -> str:
        return "mailpit"

    @property
    def channel_kind(self) -> str:
        return "email"

    @property
    def priority(self) -> int:
        return 10  # High priority for local development

    async def detect(self) -> DetectionResult | None:
        """Detect Mailpit instance."""
        # 1. Check explicit env var
        if get_env_var("DAZZLE_EMAIL_PROVIDER") == "mailpit":
            return await self._detect_explicit()

        # 2. Check for running Docker container
        docker_result = await self._detect_docker()
        if docker_result:
            return docker_result

        # 3. Check default ports
        port_result = await self._detect_ports()
        if port_result:
            return port_result

        return None

    async def _detect_explicit(self) -> DetectionResult:
        """Detect Mailpit via explicit configuration."""
        smtp_port = int(
            get_env_var("MAILPIT_SMTP_PORT", str(self.DEFAULT_SMTP_PORT)) or self.DEFAULT_SMTP_PORT
        )
        api_port = int(
            get_env_var("MAILPIT_API_PORT", str(self.DEFAULT_API_PORT)) or self.DEFAULT_API_PORT
        )
        host = get_env_var("MAILPIT_HOST", "localhost") or "localhost"

        result = DetectionResult(
            provider_name="mailpit",
            status=ProviderStatus.AVAILABLE,
            connection_url=f"smtp://{host}:{smtp_port}",
            api_url=f"http://{host}:{api_port}/api",
            management_url=f"http://{host}:{api_port}",
            detection_method="explicit",
            metadata={"host": str(host), "smtp_port": str(smtp_port), "api_port": str(api_port)},
        )

        # Verify it's actually reachable
        if not await self.health_check(result):
            result.status = ProviderStatus.UNAVAILABLE
            result.error = "Mailpit configured but not reachable"

        return result

    async def _detect_docker(self) -> DetectionResult | None:
        """Check for running Mailpit container."""
        container = await check_docker_container("mailpit")
        if not container:
            container = await check_docker_container("axllent/mailpit")

        if not container:
            return None

        # Extract ports from container info
        port_mappings = container.get("port_mappings", {})
        smtp_port = port_mappings.get(1025, self.DEFAULT_SMTP_PORT)
        api_port = port_mappings.get(8025, self.DEFAULT_API_PORT)

        result = DetectionResult(
            provider_name="mailpit",
            status=ProviderStatus.AVAILABLE,
            connection_url=f"smtp://localhost:{smtp_port}",
            api_url=f"http://localhost:{api_port}/api",
            management_url=f"http://localhost:{api_port}",
            detection_method="docker",
            metadata={
                "container": container.get("name", "unknown"),
                "image": container.get("image", "unknown"),
            },
        )

        # Verify health
        if await self.health_check(result):
            # Try to get version info
            await self._enrich_metadata(result)
            return result

        result.status = ProviderStatus.DEGRADED
        result.error = "Mailpit container found but not responding"
        return result

    async def _detect_ports(self) -> DetectionResult | None:
        """Check if Mailpit is running on default ports."""
        api_port = int(
            get_env_var("MAILPIT_API_PORT", str(self.DEFAULT_API_PORT)) or self.DEFAULT_API_PORT
        )
        smtp_port = int(
            get_env_var("MAILPIT_SMTP_PORT", str(self.DEFAULT_SMTP_PORT)) or self.DEFAULT_SMTP_PORT
        )

        # Check API port first (more reliable than SMTP)
        if not await check_port("localhost", api_port):
            return None

        result = DetectionResult(
            provider_name="mailpit",
            status=ProviderStatus.AVAILABLE,
            connection_url=f"smtp://localhost:{smtp_port}",
            api_url=f"http://localhost:{api_port}/api",
            management_url=f"http://localhost:{api_port}",
            detection_method="port",
        )

        # Verify it's actually Mailpit by checking API
        if await self.health_check(result):
            await self._enrich_metadata(result)
            return result

        return None

    async def _enrich_metadata(self, result: DetectionResult) -> None:
        """Fetch additional info from Mailpit API."""
        try:
            import aiohttp

            start = time.monotonic()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{result.api_url}/v1/info",
                    timeout=aiohttp.ClientTimeout(total=2),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result.latency_ms = (time.monotonic() - start) * 1000
                        result.metadata["version"] = data.get("Version", "unknown")
                        result.metadata["messages"] = str(data.get("Messages", 0))
                        result.metadata["database_size"] = data.get("DatabaseSize", "unknown")
        except Exception as e:
            logger.debug(f"Failed to enrich Mailpit metadata: {e}")

    async def health_check(self, result: DetectionResult) -> bool:
        """Verify Mailpit is working by checking API."""
        if not result.api_url:
            return False

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{result.api_url}/v1/info",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return bool(resp.status == 200)
        except ImportError:
            # aiohttp not available, try with urllib
            return await self._health_check_urllib(result)
        except Exception:
            return False

    async def _health_check_urllib(self, result: DetectionResult) -> bool:
        """Health check using urllib as fallback."""
        import urllib.request

        def _check() -> bool:
            try:
                req = urllib.request.Request(f"{result.api_url}/v1/info")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return bool(resp.status == 200)
            except Exception:
                return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _check)


class SendGridDetector(ProviderDetector):
    """Detect SendGrid for production email.

    Detection: SENDGRID_API_KEY environment variable.
    """

    @property
    def provider_name(self) -> str:
        return "sendgrid"

    @property
    def channel_kind(self) -> str:
        return "email"

    @property
    def priority(self) -> int:
        return 50  # Medium priority

    async def detect(self) -> DetectionResult | None:
        """Detect SendGrid via API key."""
        api_key = get_env_var("SENDGRID_API_KEY")
        if not api_key:
            return None

        # Mask API key for logging
        masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"

        return DetectionResult(
            provider_name="sendgrid",
            status=ProviderStatus.AVAILABLE,
            connection_url=None,  # SendGrid uses API, not SMTP
            api_url="https://api.sendgrid.com/v3",
            management_url="https://app.sendgrid.com",
            detection_method="env",
            metadata={"api_key_prefix": masked_key},
        )

    async def health_check(self, result: DetectionResult) -> bool:
        """Verify SendGrid API key is valid."""
        api_key = get_env_var("SENDGRID_API_KEY")
        if not api_key:
            return False

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.sendgrid.com/v3/user/profile",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return bool(resp.status == 200)
        except Exception as e:
            logger.debug(f"SendGrid health check failed: {e}")
            return False


class SESDetector(ProviderDetector):
    """Detect Amazon SES for production email.

    Detection order:
    1. Explicit env var DAZZLE_EMAIL_PROVIDER=ses
    2. AWS_SES_ENABLED=true or DAZZLE_SES_FROM_ADDRESS set
    3. Verify AWS credentials available
    """

    @property
    def provider_name(self) -> str:
        return "ses"

    @property
    def channel_kind(self) -> str:
        return "email"

    @property
    def priority(self) -> int:
        return 40  # Between Mailpit (10) and SendGrid (50)

    async def detect(self) -> DetectionResult | None:
        """Detect SES via environment variables."""
        # 1. Check explicit provider setting
        if get_env_var("DAZZLE_EMAIL_PROVIDER") == "ses":
            return await self._build_result("explicit")

        # 2. Check SES-specific env vars
        if (get_env_var("AWS_SES_ENABLED") or "").lower() == "true":
            return await self._build_result("env")

        from_address = get_env_var("DAZZLE_SES_FROM_ADDRESS")
        if from_address:
            return await self._build_result("env")

        return None

    async def _build_result(self, method: str) -> DetectionResult:
        """Build detection result with SES configuration."""
        from dazzle_back.runtime.aws_config import get_aws_config

        config = get_aws_config()
        ses_region = get_env_var("DAZZLE_SES_REGION") or config.region
        from_address = get_env_var("DAZZLE_SES_FROM_ADDRESS", "noreply@example.com")

        metadata: dict[str, str] = {
            "region": ses_region,
            "from_address": from_address or "noreply@example.com",
        }
        config_set = get_env_var("DAZZLE_SES_CONFIGURATION_SET")
        if config_set:
            metadata["configuration_set"] = config_set

        result = DetectionResult(
            provider_name="ses",
            status=ProviderStatus.AVAILABLE,
            connection_url=None,
            api_url=f"https://email.{ses_region}.amazonaws.com",
            management_url="https://console.aws.amazon.com/ses/",
            detection_method=method,
            metadata=metadata,
        )

        # Verify AWS credentials are available
        if not config.access_key_id:
            result.status = ProviderStatus.DEGRADED
            result.error = "AWS credentials not configured (may use IAM role)"

        return result

    async def health_check(self, result: DetectionResult) -> bool:
        """Verify SES access by calling get_account."""
        try:
            from dazzle_back.runtime.aws_config import get_aioboto3_session, get_aws_config

            config = get_aws_config()
            ses_region = get_env_var("DAZZLE_SES_REGION") or config.region
            session = get_aioboto3_session()

            kwargs = config.to_boto3_kwargs()
            kwargs["region_name"] = ses_region

            async with session.client("sesv2", **kwargs) as ses:
                response = await ses.get_account()
                # Check if sending is enabled
                send_quota = response.get("SendQuota", {})
                if send_quota.get("Max24HourSend", 0) == 0:
                    result.error = "SES sending quota is zero"
                    result.status = ProviderStatus.DEGRADED
                    return True  # Account exists but limited

                return True

        except ImportError:
            logger.debug("aioboto3 not installed, skipping SES health check")
            return True  # Assume available if deps not installed yet
        except Exception as e:
            logger.debug(f"SES health check failed: {e}")
            return False


class FileEmailDetector(ProviderDetector):
    """File-based email provider (fallback).

    Always available - saves emails to .dazzle/mail/ directory.
    """

    @property
    def provider_name(self) -> str:
        return "file"

    @property
    def channel_kind(self) -> str:
        return "email"

    @property
    def priority(self) -> int:
        return 999  # Lowest priority - fallback

    async def detect(self) -> DetectionResult | None:
        """File provider is always available."""
        mail_dir = Path.cwd() / ".dazzle" / "mail"

        return DetectionResult(
            provider_name="file",
            status=ProviderStatus.AVAILABLE,
            connection_url=f"file://{mail_dir}",
            api_url=None,
            management_url=None,
            detection_method="fallback",
            metadata={
                "directory": str(mail_dir),
                "note": "Emails saved locally, not sent",
            },
        )

    async def health_check(self, result: DetectionResult) -> bool:
        """File provider is always healthy."""
        return True
