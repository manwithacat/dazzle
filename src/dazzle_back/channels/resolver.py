"""
Channel resolver for DAZZLE messaging.

Resolves channel definitions to concrete providers, handling:
- Explicit provider configuration
- Environment variable overrides
- Auto-detection with health checks
- Fallback providers
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .detection import (
    DetectionResult,
    ProviderDetector,
    ProviderStatus,
    get_channel_env_var,
)
from .providers import (
    FileEmailDetector,
    InMemoryQueueDetector,
    InMemoryStreamDetector,
    MailpitDetector,
    RabbitMQDetector,
    RedisDetector,
    SendGridDetector,
)

if TYPE_CHECKING:
    from dazzle.core.ir import ChannelSpec

logger = logging.getLogger("dazzle.channels")


class ChannelConfigError(Exception):
    """Error in channel configuration."""

    pass


@dataclass
class ChannelResolution:
    """Result of resolving a channel to a provider.

    Attributes:
        channel_name: Name of the channel from DSL
        channel_kind: Kind of channel (email, queue, stream)
        provider: Detection result with provider info
        adapter_class_name: Name of adapter class to instantiate
    """

    channel_name: str
    channel_kind: str
    provider: DetectionResult
    adapter_class_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "channel_name": self.channel_name,
            "channel_kind": self.channel_kind,
            "provider": self.provider.to_dict(),
            "adapter_class_name": self.adapter_class_name,
        }


@dataclass
class ChannelResolver:
    """Resolves channel definitions to concrete providers.

    The resolver tries providers in order:
    1. Explicit provider from DSL (if not "auto")
    2. Channel-specific environment variable
    3. Auto-detection (by priority order)
    4. Fallback provider

    Example:
        resolver = ChannelResolver()
        resolution = await resolver.resolve(channel_spec)
        print(f"Channel {resolution.channel_name} using {resolution.provider.provider_name}")
    """

    _detectors: dict[str, list[ProviderDetector]] = field(default_factory=dict)
    _adapter_mapping: dict[str, str] = field(default_factory=dict)
    _cache: dict[str, ChannelResolution] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize detector registry."""
        if not self._detectors:
            self._detectors = {
                "email": [
                    MailpitDetector(),
                    SendGridDetector(),
                    FileEmailDetector(),
                ],
                "queue": [
                    RabbitMQDetector(),
                    InMemoryQueueDetector(),
                ],
                "stream": [
                    RedisDetector(),
                    InMemoryStreamDetector(),
                ],
            }

            # Sort by priority
            for kind in self._detectors:
                self._detectors[kind].sort(key=lambda d: d.priority)

        if not self._adapter_mapping:
            self._adapter_mapping = {
                # Email
                "mailpit": "MailpitAdapter",
                "sendgrid": "SendGridAdapter",
                "ses": "SESAdapter",
                "smtp": "SMTPAdapter",
                "file": "FileEmailAdapter",
                # Queue
                "rabbitmq": "RabbitMQAdapter",
                "sqs": "SQSAdapter",
                "memory_queue": "InMemoryQueueAdapter",
                # Stream
                "redis": "RedisStreamAdapter",
                "kafka": "KafkaAdapter",
                "memory_stream": "InMemoryStreamAdapter",
            }

    async def resolve(self, channel_spec: ChannelSpec) -> ChannelResolution:
        """Resolve a channel specification to a concrete provider.

        Args:
            channel_spec: Channel specification from DSL

        Returns:
            ChannelResolution with provider and adapter info

        Raises:
            ChannelConfigError: If explicit provider is not available
        """
        channel_name = channel_spec.name
        channel_kind = channel_spec.kind.value
        explicit_provider = channel_spec.provider

        # Check cache
        cache_key = f"{channel_name}:{channel_kind}:{explicit_provider}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 1. Check for explicit provider (not "auto")
        if explicit_provider and explicit_provider != "auto":
            result = await self._resolve_explicit(explicit_provider, channel_kind)
            if result:
                self._log_resolution(channel_name, result, "explicit")
                resolution = ChannelResolution(
                    channel_name=channel_name,
                    channel_kind=channel_kind,
                    provider=result,
                    adapter_class_name=self._adapter_mapping.get(result.provider_name, ""),
                )
                self._cache[cache_key] = resolution
                return resolution

            raise ChannelConfigError(
                f"Explicit provider '{explicit_provider}' not available for "
                f"channel '{channel_name}'. Check configuration and ensure "
                f"the provider service is running."
            )

        # 2. Check environment variable override
        env_provider = get_channel_env_var(channel_name, "PROVIDER")
        if env_provider:
            result = await self._resolve_explicit(env_provider, channel_kind)
            if result:
                self._log_resolution(channel_name, result, "environment")
                resolution = ChannelResolution(
                    channel_name=channel_name,
                    channel_kind=channel_kind,
                    provider=result,
                    adapter_class_name=self._adapter_mapping.get(result.provider_name, ""),
                )
                self._cache[cache_key] = resolution
                return resolution

        # 3. Auto-detect from available providers
        detectors = self._detectors.get(channel_kind, [])
        for detector in detectors:
            result = await detector.detect()
            if result and result.status == ProviderStatus.AVAILABLE:
                # Verify with health check
                if await detector.health_check(result):
                    self._log_resolution(channel_name, result, "auto-detect")
                    resolution = ChannelResolution(
                        channel_name=channel_name,
                        channel_kind=channel_kind,
                        provider=result,
                        adapter_class_name=self._adapter_mapping.get(result.provider_name, ""),
                    )
                    self._cache[cache_key] = resolution
                    return resolution

        # 4. Use fallback provider
        fallback = await self._get_fallback(channel_kind)
        self._log_resolution(channel_name, fallback, "fallback")
        resolution = ChannelResolution(
            channel_name=channel_name,
            channel_kind=channel_kind,
            provider=fallback,
            adapter_class_name=self._adapter_mapping.get(fallback.provider_name, ""),
        )
        self._cache[cache_key] = resolution
        return resolution

    async def _resolve_explicit(
        self, provider_name: str, channel_kind: str
    ) -> DetectionResult | None:
        """Resolve an explicitly named provider.

        Args:
            provider_name: Name of the provider (e.g., "mailpit", "sendgrid")
            channel_kind: Kind of channel (email, queue, stream)

        Returns:
            DetectionResult if provider found and healthy, None otherwise
        """
        detectors = self._detectors.get(channel_kind, [])
        for detector in detectors:
            if detector.provider_name == provider_name:
                result = await detector.detect()
                if result:
                    result.detection_method = "explicit"
                    return result
        return None

    async def _get_fallback(self, channel_kind: str) -> DetectionResult:
        """Get the fallback provider for a channel kind.

        Args:
            channel_kind: Kind of channel (email, queue, stream)

        Returns:
            DetectionResult for fallback provider
        """
        fallback_detectors = {
            "email": FileEmailDetector(),
            "queue": InMemoryQueueDetector(),
            "stream": InMemoryStreamDetector(),
        }

        detector = fallback_detectors.get(channel_kind)
        if detector:
            result = await detector.detect()
            if result:
                result.detection_method = "fallback"
                return result

        # This should never happen
        return DetectionResult(
            provider_name="unknown",
            status=ProviderStatus.UNAVAILABLE,
            detection_method="fallback",
            error=f"No fallback provider for {channel_kind}",
        )

    def _log_resolution(self, channel_name: str, result: DetectionResult, method: str) -> None:
        """Log resolution for console output and Dazzle logs.

        Args:
            channel_name: Name of the channel
            result: Detection result
            method: Resolution method used
        """
        logger.info(
            f"Channel '{channel_name}' resolved to {result.provider_name} via {method}",
            extra={
                "component": "Channels",
                "context": {
                    "channel": channel_name,
                    "provider": result.provider_name,
                    "method": method,
                    "connection_url": result.connection_url,
                    "management_url": result.management_url,
                },
            },
        )

    async def resolve_all(self, channel_specs: list[ChannelSpec]) -> list[ChannelResolution]:
        """Resolve multiple channels.

        Args:
            channel_specs: List of channel specifications

        Returns:
            List of channel resolutions
        """
        resolutions = []
        for spec in channel_specs:
            resolution = await self.resolve(spec)
            resolutions.append(resolution)
        return resolutions

    def clear_cache(self) -> None:
        """Clear the resolution cache."""
        self._cache.clear()

    def get_status_summary(self) -> list[dict[str, Any]]:
        """Get summary of all resolved channels.

        Returns:
            List of channel status dictionaries
        """
        return [resolution.to_dict() for resolution in self._cache.values()]
