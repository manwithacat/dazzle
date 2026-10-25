"""
Event Bus Tier Configuration and Factory.

Selects and builds the event bus for a deployment:

- Redis Streams — every production consumer (``REDIS_URL`` set).
- Null — no ``REDIS_URL``: bus publishes are accepted and dropped.
  ``EventFramework.publish`` delivers to in-process handlers instead (#1852).

The PostgreSQL and in-memory tiers were parked in flense ship AR, the Kafka tier
in flense ship F; both are recorded in DD-006.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from dazzle.http.events.bus import EventBus
from dazzle.http.events.null import NullBus

if TYPE_CHECKING:
    from dazzle.http.events.redis_bus import RedisBus

logger = logging.getLogger(__name__)


class EventTier(StrEnum):
    """Event bus tiers."""

    NULL = "null"
    """No transport: publish is a no-op and nothing is delivered."""

    REDIS = "redis"
    """Redis Streams. The production tier."""

    AUTO = "auto"
    """Redis when ``REDIS_URL`` is set, otherwise null."""


@dataclass
class TierConfig:
    """Configuration for event bus tier selection."""

    tier: EventTier = EventTier.AUTO
    """Which tier to use. AUTO detects from environment."""

    redis_url: str | None = None
    """Redis connection URL. Defaults to REDIS_URL env var."""

    redis_max_stream_length: int = 10000
    """Maximum entries per Redis stream."""

    max_retries: int = 3
    """Maximum retry attempts before moving to DLQ."""


def detect_tier() -> EventTier:
    """Redis when ``REDIS_URL`` is set, otherwise the null tier."""
    if os.getenv("REDIS_URL"):
        logger.info("Auto-detected tier: Redis (REDIS_URL set)")
        return EventTier.REDIS
    logger.info("Auto-detected tier: null (REDIS_URL not set; events are dropped)")
    return EventTier.NULL


def create_bus(config: TierConfig | None = None) -> EventBus:
    """
    Create an event bus based on configuration.

    Args:
        config: Tier configuration. If None, uses environment detection.

    Returns:
        Configured EventBus instance (not connected).

    Raises:
        ImportError: If the ``redis`` extra is missing for the Redis tier.
        ValueError: If the tier is unknown or Redis has no URL.
    """
    if config is None:
        config = TierConfig()

    tier = config.tier
    if tier == EventTier.AUTO:
        tier = detect_tier()

    if tier == EventTier.NULL:
        return NullBus()

    if tier == EventTier.REDIS:
        return _create_redis_bus(config)

    raise ValueError(f"Unknown tier: {tier}")


def _create_redis_bus(config: TierConfig) -> RedisBus:
    """Create the Redis Streams bus."""
    from dazzle.http.events.redis_bus import REDIS_AVAILABLE, RedisBus, RedisConfig

    if not REDIS_AVAILABLE:
        raise ImportError(
            "redis is required for Redis event bus. Install with: pip install dazzle-dsl[redis]"
        )

    url = config.redis_url or os.getenv("REDIS_URL")
    if not url:
        raise ValueError(
            "Redis URL not configured. Set REDIS_URL environment variable or redis_url in config."
        )

    redis_config = RedisConfig(
        url=url,
        max_stream_length=config.redis_max_stream_length,
        retry_count=config.max_retries,
    )

    logger.debug("Creating Redis Streams event bus")
    return RedisBus(redis_config)


def get_tier_info() -> dict[str, Any]:
    """
    Get information about available tiers and current configuration.

    Returns:
        Dict with available tiers and detected configuration.
    """
    from dazzle.http.events.redis_bus import REDIS_AVAILABLE

    detected = detect_tier()

    return {
        "detected_tier": detected.value,
        "available_tiers": {
            "null": {"available": True, "description": "No transport (REDIS_URL not set)"},
            "redis": {
                "available": REDIS_AVAILABLE,
                "description": "Redis Streams",
                "install": "pip install dazzle-dsl[redis]",
            },
        },
        "environment": {
            "REDIS_URL": bool(os.getenv("REDIS_URL")),
        },
    }
