"""
Provider detection framework for DAZZLE messaging channels.

This module provides the base classes and utilities for auto-detecting
messaging providers (Mailpit, SendGrid, RabbitMQ, Kafka, etc.).

Detection priority:
1. Explicit DSL (provider: sendgrid)
2. Environment variable (DAZZLE_CHANNEL_<NAME>_PROVIDER=sendgrid)
3. Docker detection (running container with known image)
4. Port scan (well-known ports responding)
5. Fallback (development-safe default)
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger("dazzle.channels")


class ProviderStatus(Enum):
    """Status of a detected provider."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


@dataclass
class DetectionResult:
    """Result of provider detection attempt.

    Attributes:
        provider_name: Unique provider identifier (e.g., "mailpit", "sendgrid")
        status: Current provider status
        connection_url: Connection URL for the provider (e.g., smtp://localhost:1025)
        api_url: API URL if provider has one (e.g., http://localhost:8025/api)
        management_url: Management UI URL if available
        detection_method: How the provider was detected
        latency_ms: Detection latency in milliseconds
        error: Error message if detection partially failed
        metadata: Provider-specific metadata (version, message count, etc.)
    """

    provider_name: str
    status: ProviderStatus
    connection_url: str | None = None
    api_url: str | None = None
    management_url: str | None = None
    detection_method: str = "unknown"  # "explicit", "env", "docker", "port", "fallback"
    latency_ms: float | None = None
    error: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "provider_name": self.provider_name,
            "status": self.status.value,
            "connection_url": self.connection_url,
            "api_url": self.api_url,
            "management_url": self.management_url,
            "detection_method": self.detection_method,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "metadata": self.metadata,
        }


class ProviderDetector(ABC):
    """Base class for provider detection.

    Subclasses implement detection logic for specific providers
    (Mailpit, SendGrid, RabbitMQ, etc.).

    Example:
        class MailpitDetector(ProviderDetector):
            @property
            def provider_name(self) -> str:
                return "mailpit"

            @property
            def channel_kind(self) -> str:
                return "email"

            async def detect(self) -> DetectionResult | None:
                # Check docker, ports, etc.
                ...
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier."""
        ...

    @property
    @abstractmethod
    def channel_kind(self) -> str:
        """Channel kind this provider supports: email, queue, stream."""
        ...

    @property
    def priority(self) -> int:
        """Detection priority (lower = higher priority).

        Override to customize detection order. Defaults to 100.
        """
        return 100

    @abstractmethod
    async def detect(self) -> DetectionResult | None:
        """Attempt to detect this provider.

        Returns:
            DetectionResult if found, None if not detected.
        """
        ...

    @abstractmethod
    async def health_check(self, result: DetectionResult) -> bool:
        """Verify the detected provider is actually working.

        Args:
            result: Detection result to verify

        Returns:
            True if provider is healthy
        """
        ...


# =============================================================================
# Detection Utilities
# =============================================================================


async def check_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a port is open and accepting connections.

    Args:
        host: Hostname to check
        port: Port number
        timeout: Connection timeout in seconds

    Returns:
        True if port is open
    """

    def _check() -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            result = sock.connect_ex((host, port))
            return result == 0
        except (OSError, TimeoutError):
            return False
        finally:
            sock.close()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _check)


async def check_docker_container(image_pattern: str) -> dict[str, Any] | None:
    """Check if a Docker container matching the pattern is running.

    Args:
        image_pattern: Pattern to match against container images (case-insensitive)

    Returns:
        Dict with container info if found, None otherwise
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "ps",
            "--format",
            "{{.Image}}\t{{.Ports}}\t{{.Names}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)

        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                image = parts[0]
                ports = parts[1] if len(parts) > 1 else ""
                name = parts[2] if len(parts) > 2 else ""

                if image_pattern.lower() in image.lower():
                    return {
                        "image": image,
                        "ports": ports,
                        "name": name,
                        "port_mappings": _parse_port_mappings(ports),
                    }

    except FileNotFoundError:
        # Docker not installed
        pass
    except TimeoutError:
        logger.debug("Docker check timed out")
    except Exception as e:
        logger.debug(f"Docker check failed: {e}")

    return None


def _parse_port_mappings(ports_str: str) -> dict[int, int]:
    """Parse Docker port mapping string.

    Example: "0.0.0.0:1025->1025/tcp, 0.0.0.0:8025->8025/tcp"
    Returns: {1025: 1025, 8025: 8025}
    """
    mappings = {}
    for part in ports_str.split(","):
        part = part.strip()
        if "->" in part:
            try:
                # Format: 0.0.0.0:host_port->container_port/tcp
                host_part, container_part = part.split("->")
                host_port = int(host_part.split(":")[-1])
                container_port = int(container_part.split("/")[0])
                mappings[container_port] = host_port
            except (ValueError, IndexError):
                continue
    return mappings


def get_env_var(name: str, default: str | None = None) -> str | None:
    """Get environment variable with optional default.

    Args:
        name: Environment variable name
        default: Default value if not set

    Returns:
        Environment variable value or default
    """
    return os.environ.get(name, default)


def get_channel_env_var(channel_name: str, suffix: str) -> str | None:
    """Get channel-specific environment variable.

    Args:
        channel_name: Channel name from DSL
        suffix: Variable suffix (e.g., "PROVIDER", "HOST")

    Returns:
        Environment variable value if set
    """
    var_name = f"DAZZLE_CHANNEL_{channel_name.upper()}_{suffix}"
    return os.environ.get(var_name)
