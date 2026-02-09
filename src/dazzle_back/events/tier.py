"""
Event Bus Tier Configuration and Factory.

Provides a unified way to configure and instantiate the appropriate event bus
based on deployment environment. Supports automatic tier detection and explicit
configuration.

Tiers:
- Tier 0: In-memory (testing)
- Tier 0.5: SQLite (local development)
- Tier 1: PostgreSQL (Heroku pilots)
- Tier 2: Redis Streams (Heroku growth)
- Tier 3: EventBridge (AWS serverless) - future
- Tier 4: Kafka (production scale)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle_back.events.bus import EventBus
from dazzle_back.events.dev_memory import DevBusMemory
from dazzle_back.events.dev_sqlite import DevBrokerSQLite

if TYPE_CHECKING:
    from dazzle_back.events.kafka_bus import KafkaBus
    from dazzle_back.events.postgres_bus import PostgresBus
    from dazzle_back.events.redis_bus import RedisBus

logger = logging.getLogger(__name__)


class EventTier(StrEnum):
    """Event bus tiers in order of increasing capability/complexity."""

    MEMORY = "memory"
    """Tier 0: In-memory, no durability. For testing only."""

    SQLITE = "sqlite"
    """Tier 0.5: SQLite-backed, durable. For local development."""

    POSTGRES = "postgres"
    """Tier 1: PostgreSQL-backed. For Heroku pilots with existing Postgres."""

    REDIS = "redis"
    """Tier 2: Redis Streams. For higher throughput on Heroku."""

    EVENTBRIDGE = "eventbridge"
    """Tier 3: AWS EventBridge. For serverless/AWS deployments."""

    KAFKA = "kafka"
    """Tier 4: Apache Kafka. For production scale."""

    AUTO = "auto"
    """Auto-detect based on available environment variables."""


@dataclass
class TierConfig:
    """Configuration for event bus tier selection."""

    tier: EventTier = EventTier.AUTO
    """Which tier to use. AUTO detects from environment."""

    # SQLite config
    sqlite_db_path: str | None = None
    """Path to SQLite database. Defaults to 'data/events.db'."""

    # PostgreSQL config
    postgres_url: str | None = None
    """PostgreSQL connection URL. Defaults to DATABASE_URL env var."""

    postgres_table_prefix: str = "_dazzle_"
    """Prefix for PostgreSQL event tables."""

    # Redis config
    redis_url: str | None = None
    """Redis connection URL. Defaults to REDIS_URL env var."""

    redis_max_stream_length: int = 100000
    """Maximum entries per Redis stream."""

    # Kafka config
    kafka_bootstrap_servers: list[str] = field(default_factory=list)
    """Kafka bootstrap servers. Defaults to KAFKA_BOOTSTRAP_SERVERS env var."""

    kafka_security_protocol: str = "PLAINTEXT"
    """Kafka security protocol."""

    # General config
    max_retries: int = 3
    """Maximum retry attempts before moving to DLQ."""

    poll_interval: float = 0.5
    """Seconds between polls when no events available."""


def detect_tier() -> EventTier:
    """
    Auto-detect the appropriate tier based on environment.

    Detection order:
    1. EVENT_BACKEND explicitly set -> use that tier
    2. KAFKA_BOOTSTRAP_SERVERS -> Kafka
    3. REDIS_URL -> Redis (no longer requires EVENT_BACKEND=redis)
    4. DATABASE_URL starting with postgres -> PostgreSQL
    5. Default -> Memory (test-only)
    """
    # Explicit override via EVENT_BACKEND
    explicit = os.getenv("EVENT_BACKEND", "").lower()
    if explicit:
        tier_map = {
            "memory": EventTier.MEMORY,
            "sqlite": EventTier.SQLITE,
            "postgres": EventTier.POSTGRES,
            "redis": EventTier.REDIS,
            "kafka": EventTier.KAFKA,
        }
        if explicit in tier_map:
            logger.info(f"Using explicit tier: {explicit} (EVENT_BACKEND={explicit})")
            return tier_map[explicit]

    # Check for Kafka
    if os.getenv("KAFKA_BOOTSTRAP_SERVERS"):
        logger.info("Auto-detected tier: Kafka (KAFKA_BOOTSTRAP_SERVERS set)")
        return EventTier.KAFKA

    # Check for Redis — auto-select when REDIS_URL is set
    if os.getenv("REDIS_URL"):
        logger.info("Auto-detected tier: Redis (REDIS_URL set)")
        return EventTier.REDIS

    # Check for PostgreSQL
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("postgres"):
        logger.info("Auto-detected tier: PostgreSQL (DATABASE_URL is postgres)")
        return EventTier.POSTGRES

    # Default to in-memory (test-only)
    logger.info("Auto-detected tier: Memory (no external backends configured)")
    return EventTier.MEMORY


def create_bus(config: TierConfig | None = None) -> EventBus:
    """
    Create an event bus based on configuration.

    Args:
        config: Tier configuration. If None, uses environment detection.

    Returns:
        Configured EventBus instance (not connected).

    Raises:
        ImportError: If required dependencies for the tier are not installed.
        ValueError: If tier is not supported.

    Example:
        # Auto-detect tier
        bus = create_bus()
        async with bus:
            await bus.publish("app.Order", envelope)

        # Explicit tier
        config = TierConfig(tier=EventTier.POSTGRES)
        bus = create_bus(config)
    """
    if config is None:
        config = TierConfig()

    tier = config.tier
    if tier == EventTier.AUTO:
        tier = detect_tier()

    if tier == EventTier.MEMORY:
        return _create_memory_bus()

    if tier == EventTier.SQLITE:
        return _create_sqlite_bus(config)

    if tier == EventTier.POSTGRES:
        return _create_postgres_bus(config)

    if tier == EventTier.REDIS:
        return _create_redis_bus(config)

    if tier == EventTier.KAFKA:
        return _create_kafka_bus(config)

    if tier == EventTier.EVENTBRIDGE:
        raise NotImplementedError(
            "EventBridge tier is not yet implemented. "
            "Use AWS SQS/EventBridge via dazzle deploy stacks."
        )

    raise ValueError(f"Unknown tier: {tier}")


def _create_memory_bus() -> DevBusMemory:
    """Create in-memory bus for testing."""
    logger.debug("Creating in-memory event bus (Tier 0)")
    return DevBusMemory()


def _create_sqlite_bus(config: TierConfig) -> DevBrokerSQLite:
    """Create SQLite-backed bus for local development."""
    import warnings

    warnings.warn(
        "SQLite event bus is deprecated. Use PostgreSQL or Redis.",
        DeprecationWarning,
        stacklevel=3,
    )
    db_path = config.sqlite_db_path
    if not db_path:
        # Default to data/events.db relative to working directory
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        db_path = str(data_dir / "events.db")

    logger.debug(f"Creating SQLite event bus (Tier 0.5) at {db_path}")
    return DevBrokerSQLite(db_path)


def _create_postgres_bus(config: TierConfig) -> PostgresBus:
    """Create PostgreSQL-backed bus for Heroku pilots."""
    from dazzle_back.events.postgres_bus import (
        ASYNCPG_AVAILABLE,
        PostgresBus,
        PostgresConfig,
    )

    if not ASYNCPG_AVAILABLE:
        raise ImportError(
            "psycopg is required for PostgreSQL event bus. "
            "Install with: pip install dazzle[postgres]"
        )

    dsn = config.postgres_url or os.getenv("DATABASE_URL")
    if not dsn:
        raise ValueError(
            "PostgreSQL URL not configured. "
            "Set DATABASE_URL environment variable or postgres_url in config."
        )

    pg_config = PostgresConfig(
        dsn=dsn,
        table_prefix=config.postgres_table_prefix,
        max_retries=config.max_retries,
        poll_interval=config.poll_interval,
    )

    logger.debug("Creating PostgreSQL event bus (Tier 1)")
    return PostgresBus(pg_config)


def _create_redis_bus(config: TierConfig) -> RedisBus:
    """Create Redis Streams bus for higher throughput."""
    from dazzle_back.events.redis_bus import REDIS_AVAILABLE, RedisBus, RedisConfig

    if not REDIS_AVAILABLE:
        raise ImportError(
            "redis is required for Redis event bus. Install with: pip install dazzle[redis]"
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

    logger.debug("Creating Redis Streams event bus (Tier 2)")
    return RedisBus(redis_config)


def _create_kafka_bus(config: TierConfig) -> KafkaBus:
    """Create Kafka bus for production scale."""
    from dazzle_back.events.kafka_bus import KAFKA_AVAILABLE, KafkaBus, KafkaConfig

    if not KAFKA_AVAILABLE:
        raise ImportError(
            "aiokafka is required for Kafka event bus. Install with: pip install dazzle[kafka]"
        )

    servers = config.kafka_bootstrap_servers
    if not servers:
        servers_env = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "")
        servers = [s.strip() for s in servers_env.split(",") if s.strip()]

    if not servers:
        raise ValueError(
            "Kafka bootstrap servers not configured. "
            "Set KAFKA_BOOTSTRAP_SERVERS environment variable."
        )

    # KafkaConfig expects comma-separated string, not list
    servers_str = ",".join(servers)

    kafka_config = KafkaConfig(
        bootstrap_servers=servers_str,
        security_protocol=config.kafka_security_protocol,
    )

    logger.debug("Creating Kafka event bus (Tier 4)")
    return KafkaBus(kafka_config)


def get_tier_info() -> dict[str, Any]:
    """
    Get information about available tiers and current configuration.

    Returns:
        Dict with available tiers and detected configuration.
    """
    from dazzle_back.events.kafka_bus import KAFKA_AVAILABLE
    from dazzle_back.events.postgres_bus import ASYNCPG_AVAILABLE
    from dazzle_back.events.redis_bus import REDIS_AVAILABLE

    detected = detect_tier()

    return {
        "detected_tier": detected.value,
        "available_tiers": {
            "memory": {"available": True, "description": "In-memory (testing)"},
            "sqlite": {"available": True, "description": "SQLite (local dev)"},
            "postgres": {
                "available": ASYNCPG_AVAILABLE,
                "description": "PostgreSQL (Heroku pilots)",
                "install": "pip install dazzle[postgres]",
            },
            "redis": {
                "available": REDIS_AVAILABLE,
                "description": "Redis Streams (Heroku growth)",
                "install": "pip install dazzle[redis]",
            },
            "kafka": {
                "available": KAFKA_AVAILABLE,
                "description": "Apache Kafka (production)",
                "install": "pip install dazzle[kafka]",
            },
        },
        "environment": {
            "DATABASE_URL": bool(os.getenv("DATABASE_URL")),
            "REDIS_URL": bool(os.getenv("REDIS_URL")),
            "KAFKA_BOOTSTRAP_SERVERS": bool(os.getenv("KAFKA_BOOTSTRAP_SERVERS")),
            "EVENT_BACKEND": os.getenv("EVENT_BACKEND"),
        },
    }
