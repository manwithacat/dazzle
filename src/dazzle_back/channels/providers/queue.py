"""
Queue provider detectors for DAZZLE messaging.

Supports:
- RabbitMQ (production)
- In-memory queue (fallback)
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger("dazzle.channels.queue")


class RabbitMQDetector(ProviderDetector):
    """Detect RabbitMQ for production queue.

    Detection order:
    1. RABBITMQ_URL environment variable
    2. Running Docker container with rabbitmq image
    3. Port 5672 responding
    """

    DEFAULT_AMQP_PORT = 5672
    DEFAULT_MANAGEMENT_PORT = 15672

    @property
    def provider_name(self) -> str:
        return "rabbitmq"

    @property
    def channel_kind(self) -> str:
        return "queue"

    @property
    def priority(self) -> int:
        return 20  # High priority for production queues

    async def detect(self) -> DetectionResult | None:
        """Detect RabbitMQ instance."""
        # 1. Check explicit URL
        url = get_env_var("RABBITMQ_URL")
        if url:
            return DetectionResult(
                provider_name="rabbitmq",
                status=ProviderStatus.AVAILABLE,
                connection_url=url,
                api_url=None,
                management_url=get_env_var("RABBITMQ_MANAGEMENT_URL"),
                detection_method="env",
            )

        # 2. Check for running Docker container
        docker_result = await self._detect_docker()
        if docker_result:
            return docker_result

        # 3. Check default ports
        if await check_port("localhost", self.DEFAULT_AMQP_PORT):
            has_management = await check_port("localhost", self.DEFAULT_MANAGEMENT_PORT)
            return DetectionResult(
                provider_name="rabbitmq",
                status=ProviderStatus.AVAILABLE,
                connection_url=f"amqp://localhost:{self.DEFAULT_AMQP_PORT}",
                api_url=None,
                management_url=(
                    f"http://localhost:{self.DEFAULT_MANAGEMENT_PORT}" if has_management else None
                ),
                detection_method="port",
            )

        return None

    async def _detect_docker(self) -> DetectionResult | None:
        """Check for running RabbitMQ container."""
        container = await check_docker_container("rabbitmq")
        if not container:
            return None

        port_mappings = container.get("port_mappings", {})
        amqp_port = port_mappings.get(5672, self.DEFAULT_AMQP_PORT)
        management_port = port_mappings.get(15672, self.DEFAULT_MANAGEMENT_PORT)

        has_management = 15672 in port_mappings or await check_port("localhost", management_port)

        return DetectionResult(
            provider_name="rabbitmq",
            status=ProviderStatus.AVAILABLE,
            connection_url=f"amqp://localhost:{amqp_port}",
            api_url=None,
            management_url=(f"http://localhost:{management_port}" if has_management else None),
            detection_method="docker",
            metadata={
                "container": container.get("name", "unknown"),
                "image": container.get("image", "unknown"),
            },
        )

    async def health_check(self, result: DetectionResult) -> bool:
        """Verify RabbitMQ is accessible."""
        if not result.connection_url:
            return False

        # Try management API if available
        if result.management_url:
            try:
                import aiohttp

                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{result.management_url}/api/overview",
                        auth=aiohttp.BasicAuth("guest", "guest"),
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        return bool(resp.status == 200)
            except Exception:
                pass

        # Fall back to port check
        try:
            # Parse port from connection URL
            url = result.connection_url
            if ":" in url:
                port = int(url.split(":")[-1].split("/")[0])
                return await check_port("localhost", port)
        except (ValueError, IndexError):
            pass

        return False


class InMemoryQueueDetector(ProviderDetector):
    """In-memory queue provider (fallback).

    Always available - queues stored in memory, lost on restart.
    """

    @property
    def provider_name(self) -> str:
        return "memory_queue"

    @property
    def channel_kind(self) -> str:
        return "queue"

    @property
    def priority(self) -> int:
        return 999  # Lowest priority - fallback

    async def detect(self) -> DetectionResult | None:
        """Memory queue is always available."""
        return DetectionResult(
            provider_name="memory_queue",
            status=ProviderStatus.AVAILABLE,
            connection_url="memory://queue",
            api_url=None,
            management_url=None,
            detection_method="fallback",
            metadata={
                "note": "In-memory queue, data lost on restart",
                "persistent": "false",
            },
        )

    async def health_check(self, result: DetectionResult) -> bool:
        """Memory queue is always healthy."""
        return True
