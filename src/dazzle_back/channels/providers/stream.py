"""
Stream provider detectors for DAZZLE messaging.

Supports:
- Redis Streams (production)
- Kafka (production)
- In-memory stream (fallback)
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

logger = logging.getLogger("dazzle.channels.stream")


class RedisDetector(ProviderDetector):
    """Detect Redis for stream provider.

    Detection order:
    1. REDIS_URL environment variable
    2. Running Docker container with redis image
    3. Port 6379 responding
    """

    DEFAULT_PORT = 6379

    @property
    def provider_name(self) -> str:
        return "redis"

    @property
    def channel_kind(self) -> str:
        return "stream"

    @property
    def priority(self) -> int:
        return 20  # High priority for production streams

    async def detect(self) -> DetectionResult | None:
        """Detect Redis instance."""
        # 1. Check explicit URL
        url = get_env_var("REDIS_URL")
        if url:
            return DetectionResult(
                provider_name="redis",
                status=ProviderStatus.AVAILABLE,
                connection_url=url,
                api_url=None,
                management_url=None,
                detection_method="env",
            )

        # 2. Check for running Docker container
        docker_result = await self._detect_docker()
        if docker_result:
            return docker_result

        # 3. Check default port
        if await check_port("localhost", self.DEFAULT_PORT):
            return DetectionResult(
                provider_name="redis",
                status=ProviderStatus.AVAILABLE,
                connection_url=f"redis://localhost:{self.DEFAULT_PORT}",
                api_url=None,
                management_url=None,
                detection_method="port",
            )

        return None

    async def _detect_docker(self) -> DetectionResult | None:
        """Check for running Redis container."""
        container = await check_docker_container("redis")
        if not container:
            return None

        port_mappings = container.get("port_mappings", {})
        port = port_mappings.get(6379, self.DEFAULT_PORT)

        return DetectionResult(
            provider_name="redis",
            status=ProviderStatus.AVAILABLE,
            connection_url=f"redis://localhost:{port}",
            api_url=None,
            management_url=None,
            detection_method="docker",
            metadata={
                "container": container.get("name", "unknown"),
                "image": container.get("image", "unknown"),
            },
        )

    async def health_check(self, result: DetectionResult) -> bool:
        """Verify Redis is accessible."""
        if not result.connection_url:
            return False

        try:
            # Try redis-py if available
            import redis.asyncio as redis

            client = redis.from_url(result.connection_url)
            try:
                await client.ping()
                return True
            finally:
                await client.close()
        except ImportError:
            # Fall back to port check
            try:
                url = result.connection_url
                if ":" in url:
                    port = int(url.split(":")[-1].split("/")[0])
                    return await check_port("localhost", port)
            except (ValueError, IndexError):
                pass
        except Exception as e:
            logger.debug(f"Redis health check failed: {e}")

        return False


class KafkaDetector(ProviderDetector):
    """Detect Kafka for stream provider.

    Detection order:
    1. KAFKA_BOOTSTRAP_SERVERS environment variable
    2. Running Docker container with kafka image
    3. Port 9092 responding
    """

    DEFAULT_PORT = 9092

    @property
    def provider_name(self) -> str:
        return "kafka"

    @property
    def channel_kind(self) -> str:
        return "stream"

    @property
    def priority(self) -> int:
        return 30  # Medium-high priority

    async def detect(self) -> DetectionResult | None:
        """Detect Kafka instance."""
        # 1. Check explicit bootstrap servers
        servers = get_env_var("KAFKA_BOOTSTRAP_SERVERS")
        if servers:
            return DetectionResult(
                provider_name="kafka",
                status=ProviderStatus.AVAILABLE,
                connection_url=servers,
                api_url=None,
                management_url=None,
                detection_method="env",
                metadata={"bootstrap_servers": servers},
            )

        # 2. Check for running Docker container
        docker_result = await self._detect_docker()
        if docker_result:
            return docker_result

        # 3. Check default port
        if await check_port("localhost", self.DEFAULT_PORT):
            return DetectionResult(
                provider_name="kafka",
                status=ProviderStatus.AVAILABLE,
                connection_url=f"localhost:{self.DEFAULT_PORT}",
                api_url=None,
                management_url=None,
                detection_method="port",
            )

        return None

    async def _detect_docker(self) -> DetectionResult | None:
        """Check for running Kafka container."""
        container = await check_docker_container("kafka")
        if not container:
            # Try common image patterns
            container = await check_docker_container("confluentinc/cp-kafka")
        if not container:
            container = await check_docker_container("bitnami/kafka")

        if not container:
            return None

        port_mappings = container.get("port_mappings", {})
        port = port_mappings.get(9092, self.DEFAULT_PORT)

        return DetectionResult(
            provider_name="kafka",
            status=ProviderStatus.AVAILABLE,
            connection_url=f"localhost:{port}",
            api_url=None,
            management_url=None,
            detection_method="docker",
            metadata={
                "container": container.get("name", "unknown"),
                "image": container.get("image", "unknown"),
            },
        )

    async def health_check(self, result: DetectionResult) -> bool:
        """Verify Kafka is accessible."""
        if not result.connection_url:
            return False

        # Just do a port check - proper Kafka health check requires client
        try:
            servers = result.connection_url
            host_port = servers.split(",")[0]
            if ":" in host_port:
                host, port_str = host_port.rsplit(":", 1)
                return await check_port(host, int(port_str))
        except (ValueError, IndexError):
            pass

        return False


class InMemoryStreamDetector(ProviderDetector):
    """In-memory stream provider (fallback).

    Always available - streams stored in memory, lost on restart.
    """

    @property
    def provider_name(self) -> str:
        return "memory_stream"

    @property
    def channel_kind(self) -> str:
        return "stream"

    @property
    def priority(self) -> int:
        return 999  # Lowest priority - fallback

    async def detect(self) -> DetectionResult | None:
        """Memory stream is always available."""
        return DetectionResult(
            provider_name="memory_stream",
            status=ProviderStatus.AVAILABLE,
            connection_url="memory://stream",
            api_url=None,
            management_url=None,
            detection_method="fallback",
            metadata={
                "note": "In-memory stream, data lost on restart",
                "persistent": "false",
            },
        )

    async def health_check(self, result: DetectionResult) -> bool:
        """Memory stream is always healthy."""
        return True
