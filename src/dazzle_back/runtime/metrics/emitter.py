"""
Metrics Emitter - fire-and-forget metrics to Redis streams.

Designed for minimal overhead on the main application:
- Buffers metrics in memory
- Flushes to Redis in background thread
- Non-blocking, fire-and-forget semantics
- Graceful degradation if Redis unavailable
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Global emitter instance
_emitter: MetricsEmitter | None = None


@dataclass
class MetricEvent:
    """A single metric event to be emitted."""

    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: dict[str, str] = field(default_factory=dict)


class MetricsEmitter:
    """
    Fire-and-forget metrics emitter.

    Metrics are buffered in memory and flushed to Redis streams
    in a background thread. If Redis is unavailable, metrics are
    silently dropped to avoid impacting the main application.
    """

    def __init__(
        self,
        redis_url: str,
        stream_key: str = "dazzle:metrics:stream",
        buffer_size: int = 100,
        flush_interval: float = 1.0,
        max_stream_len: int = 10000,
    ):
        """
        Initialize the metrics emitter.

        Args:
            redis_url: Redis connection URL
            stream_key: Redis stream key for metrics
            buffer_size: Flush when buffer reaches this size
            flush_interval: Maximum seconds between flushes
            max_stream_len: Max stream length (MAXLEN for XADD)
        """
        self._redis_url = redis_url
        self._stream_key = stream_key
        self._buffer_size = buffer_size
        self._flush_interval = flush_interval
        self._max_stream_len = max_stream_len

        # Queue for thread-safe buffering
        self._queue: queue.Queue[MetricEvent] = queue.Queue(maxsize=10000)

        # Background flush thread
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

        # Redis client (lazy initialized)
        self._redis: Any = None

        # Track dyno/instance for tagging
        self._instance = os.environ.get("DYNO", os.environ.get("HOSTNAME", "local"))

        logger.info(f"MetricsEmitter initialized (instance={self._instance})")

    def _get_redis(self) -> Any:
        """Lazy initialize Redis connection."""
        if self._redis is None:
            try:
                import redis

                # Handle Heroku/AWS Redis SSL
                ssl_cert_reqs = None if "amazonaws.com" in self._redis_url else "required"
                self._redis = redis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    ssl_cert_reqs=ssl_cert_reqs,
                )
                # Test connection
                self._redis.ping()
                logger.info("MetricsEmitter connected to Redis")
            except Exception as e:
                logger.warning(f"MetricsEmitter failed to connect to Redis: {e}")
                self._redis = None
        return self._redis

    def emit(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """
        Emit a metric (fire-and-forget).

        This method is non-blocking and will not raise exceptions.
        Metrics are buffered and flushed asynchronously.

        Args:
            name: Metric name (e.g., "http_requests_total")
            value: Metric value
            tags: Optional tags for filtering/grouping
        """
        try:
            event = MetricEvent(
                name=name,
                value=value,
                tags={**(tags or {}), "instance": self._instance},
            )
            # Non-blocking put
            self._queue.put_nowait(event)
        except queue.Full:
            # Buffer full, drop metric
            logger.debug(f"Metrics buffer full, dropping: {name}")
        except Exception as e:
            # Never fail the caller
            logger.debug(f"Failed to buffer metric: {e}")

    def increment(self, name: str, tags: dict[str, str] | None = None) -> None:
        """Increment a counter by 1."""
        self.emit(name, 1.0, tags)

    def timing(self, name: str, duration_ms: float, tags: dict[str, str] | None = None) -> None:
        """Record a timing metric in milliseconds."""
        self.emit(name, duration_ms, tags)

    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a gauge metric."""
        self.emit(name, value, tags)

    def _flush_loop(self) -> None:
        """Background thread that flushes metrics to Redis."""
        buffer: list[MetricEvent] = []
        last_flush = time.time()

        while self._running:
            try:
                # Collect from queue with timeout
                try:
                    event = self._queue.get(timeout=0.1)
                    buffer.append(event)
                except queue.Empty:
                    pass

                # Check if we should flush
                should_flush = len(buffer) >= self._buffer_size or (
                    buffer and time.time() - last_flush >= self._flush_interval
                )

                if should_flush and buffer:
                    self._flush_to_redis(buffer)
                    buffer = []
                    last_flush = time.time()

            except Exception as e:
                logger.warning(f"Error in metrics flush loop: {e}")
                time.sleep(1)

        # Final flush on shutdown
        if buffer:
            self._flush_to_redis(buffer)

    def _flush_to_redis(self, events: list[MetricEvent]) -> None:
        """Flush buffered events to Redis stream."""
        redis_client = self._get_redis()
        if not redis_client:
            return

        try:
            pipe = redis_client.pipeline()
            for event in events:
                fields = {
                    "name": event.name,
                    "value": str(event.value),
                    "ts": str(event.timestamp),
                    "tags": json.dumps(event.tags) if event.tags else "",
                }
                pipe.xadd(
                    self._stream_key,
                    fields,
                    maxlen=self._max_stream_len,
                )
            pipe.execute()
            logger.debug(f"Flushed {len(events)} metrics to Redis")
        except Exception as e:
            logger.warning(f"Failed to flush metrics to Redis: {e}")
            # Reset connection on error
            self._redis = None

    def shutdown(self) -> None:
        """Gracefully shutdown the emitter."""
        self._running = False
        if self._flush_thread.is_alive():
            self._flush_thread.join(timeout=5.0)


def get_emitter() -> MetricsEmitter | None:
    """Get the global metrics emitter instance."""
    global _emitter
    if _emitter is None:
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            max_len = int(os.environ.get("DAZZLE_METRICS_MAXLEN", "10000"))
            _emitter = MetricsEmitter(redis_url, max_stream_len=max_len)
            atexit.register(_emitter.shutdown)
        else:
            logger.debug("REDIS_URL not set, metrics disabled")
    return _emitter


def emit(name: str, value: float, tags: dict[str, str] | None = None) -> None:
    """Convenience function to emit a metric."""
    emitter = get_emitter()
    if emitter:
        emitter.emit(name, value, tags)
