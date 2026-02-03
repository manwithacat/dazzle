"""
Metrics Collector - consumes metrics from Redis streams.

Runs as a background task, reading from the metrics stream
and aggregating into the time-series store.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis import Redis

from .metrics_store import MetricsStore

logger = logging.getLogger(__name__)


@dataclass
class CollectorConfig:
    """Configuration for the metrics collector."""

    redis_url: str
    stream_key: str = "dazzle:metrics:stream"
    consumer_group: str = "control-plane"
    consumer_name: str = "collector-1"
    batch_size: int = 100
    block_ms: int = 1000  # How long to block waiting for new messages


class MetricsCollector:
    """
    Consumes metrics from Redis streams and stores in time-series format.

    Uses Redis consumer groups for reliable delivery and
    horizontal scaling of collectors.
    """

    def __init__(self, config: CollectorConfig):
        self._config = config
        self._redis: Redis[Any] | None = None
        self._store: MetricsStore | None = None
        self._running = False

    def _get_redis(self) -> Redis[Any]:
        """Get or create Redis connection."""
        if self._redis is None:
            import redis

            # Handle Heroku/AWS Redis SSL
            ssl_cert_reqs = None if "amazonaws.com" in self._config.redis_url else "required"
            self._redis = redis.from_url(
                self._config.redis_url,
                decode_responses=True,
                ssl_cert_reqs=ssl_cert_reqs,
            )
            self._ensure_consumer_group()
        return self._redis

    def _ensure_consumer_group(self) -> None:
        """Ensure the consumer group exists."""
        redis_client = self._get_redis()
        try:
            redis_client.xgroup_create(
                self._config.stream_key,
                self._config.consumer_group,
                id="0",
                mkstream=True,
            )
            logger.info(f"Created consumer group: {self._config.consumer_group}")
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                raise
            logger.debug(f"Consumer group already exists: {self._config.consumer_group}")

    @classmethod
    def from_env(cls) -> MetricsCollector:
        """Create collector from environment variables."""
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        return cls(CollectorConfig(redis_url=redis_url))

    async def run(self) -> None:
        """Run the collector loop."""
        self._running = True
        # Initialize Redis and store
        redis_client = self._get_redis()
        self._store = MetricsStore(redis_client)
        logger.info("Metrics collector started")

        while self._running:
            try:
                await self._collect_batch()
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
                await asyncio.sleep(1)

        logger.info("Metrics collector stopped")

    def stop(self) -> None:
        """Stop the collector loop."""
        self._running = False

    async def _collect_batch(self) -> None:
        """Collect and process a batch of metrics."""
        loop = asyncio.get_event_loop()
        messages = await loop.run_in_executor(
            None,
            self._read_messages,
        )

        if not messages:
            return

        processed_ids = []
        metrics_batch = []

        for _stream_name, stream_messages in messages:
            for msg_id, fields in stream_messages:
                try:
                    metric = self._parse_metric(fields)
                    if metric:
                        metrics_batch.append(metric)
                    processed_ids.append(msg_id)
                except Exception as e:
                    logger.warning(f"Failed to parse metric {msg_id}: {e}")
                    processed_ids.append(msg_id)

        # Store metrics
        if metrics_batch and self._store:
            await loop.run_in_executor(
                None,
                self._store.record_batch,
                metrics_batch,
            )
            logger.debug(f"Stored {len(metrics_batch)} metrics")

        # Acknowledge processed messages
        if processed_ids:
            await loop.run_in_executor(
                None,
                self._ack_messages,
                processed_ids,
            )

    def _read_messages(self) -> list[Any]:
        """Read messages from the stream (blocking)."""
        redis_client = self._get_redis()
        result: Any = redis_client.xreadgroup(
            self._config.consumer_group,
            self._config.consumer_name,
            {self._config.stream_key: ">"},
            count=self._config.batch_size,
            block=self._config.block_ms,
        )
        return list(result) if result else []

    def _ack_messages(self, message_ids: list[str]) -> None:
        """Acknowledge messages as processed."""
        if message_ids:
            redis_client = self._get_redis()
            redis_client.xack(
                self._config.stream_key,
                self._config.consumer_group,
                *message_ids,
            )

    def _parse_metric(self, fields: dict[str, Any]) -> dict[str, Any] | None:
        """Parse a metric from stream fields."""
        name = fields.get("name")
        value = fields.get("value")

        if not name or value is None:
            return None

        try:
            return {
                "name": name,
                "value": float(value),
                "ts": float(fields.get("ts", 0)) or None,
                "tags": self._parse_tags(fields.get("tags")),
            }
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid metric value: {e}")
            return None

    def _parse_tags(self, tags_str: str | None) -> dict[str, str] | None:
        """Parse tags from JSON string."""
        if not tags_str:
            return None
        try:
            parsed: dict[str, str] = json.loads(tags_str)
            return parsed
        except (ValueError, TypeError):
            return None

    @property
    def store(self) -> MetricsStore | None:
        """Get the metrics store for querying."""
        return self._store
