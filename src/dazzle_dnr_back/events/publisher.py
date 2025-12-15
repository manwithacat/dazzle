"""
Outbox Publisher Loop for Reliable Event Delivery.

The publisher loop is a background task that polls the outbox for pending
events and publishes them to the event bus. This decouples the transactional
write (to the outbox) from the actual publication (to the bus).

Features:
- Polling with configurable interval
- Exponential backoff on failures
- Batch processing for efficiency
- Lock-based concurrency control for multiple publishers
- Metrics/observability hooks

Rule 1: No dual writes - events are published only from the outbox
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import aiosqlite

from dazzle_dnr_back.events.bus import EventBus, PublishError
from dazzle_dnr_back.events.outbox import EventOutbox, OutboxEntry

logger = logging.getLogger(__name__)


@dataclass
class PublisherStats:
    """Statistics for the publisher loop."""

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    events_published: int = 0
    events_failed: int = 0
    batches_processed: int = 0
    last_publish_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None


@dataclass
class PublisherConfig:
    """Configuration for the publisher loop."""

    # Polling interval in seconds
    poll_interval: float = 1.0

    # Batch size for each poll
    batch_size: int = 100

    # Maximum retry attempts before giving up
    max_attempts: int = 5

    # Base backoff in seconds (doubles each attempt)
    backoff_base: float = 1.0

    # Maximum backoff in seconds
    backoff_max: float = 60.0

    # Lock duration in seconds
    lock_duration: int = 60

    # Unique identifier for this publisher instance
    publisher_id: str = field(default_factory=lambda: str(uuid4())[:8])


class OutboxPublisher:
    """
    Background publisher that drains the outbox to the event bus.

    Usage:
        publisher = OutboxPublisher(db_path, bus, outbox)
        await publisher.start()
        # ... application runs ...
        await publisher.stop()

    Or as context manager:
        async with OutboxPublisher(db_path, bus, outbox) as publisher:
            # Publisher runs in background
            pass
    """

    def __init__(
        self,
        db_path: str,
        bus: EventBus,
        outbox: EventOutbox | None = None,
        config: PublisherConfig | None = None,
    ) -> None:
        """
        Initialize the publisher.

        Args:
            db_path: Path to SQLite database
            bus: Event bus to publish to
            outbox: Outbox instance (creates default if None)
            config: Publisher configuration
        """
        self._db_path = db_path
        self._bus = bus
        self._outbox = outbox or EventOutbox()
        self._config = config or PublisherConfig()
        self._stats = PublisherStats()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._conn: aiosqlite.Connection | None = None

    @property
    def stats(self) -> PublisherStats:
        """Get current publisher statistics."""
        return self._stats

    @property
    def is_running(self) -> bool:
        """Check if the publisher is running."""
        return self._running

    async def start(self) -> None:
        """Start the publisher loop."""
        if self._running:
            return

        self._running = True
        self._conn = await aiosqlite.connect(self._db_path)
        self._task = asyncio.create_task(self._run_loop())

        logger.info(
            "Outbox publisher started",
            extra={
                "publisher_id": self._config.publisher_id,
                "poll_interval": self._config.poll_interval,
                "batch_size": self._config.batch_size,
            },
        )

    async def stop(self) -> None:
        """Stop the publisher loop."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._conn:
            await self._conn.close()
            self._conn = None

        logger.info(
            "Outbox publisher stopped",
            extra={
                "publisher_id": self._config.publisher_id,
                "events_published": self._stats.events_published,
                "events_failed": self._stats.events_failed,
            },
        )

    async def __aenter__(self) -> OutboxPublisher:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()

    async def _run_loop(self) -> None:
        """Main publisher loop."""
        while self._running:
            try:
                processed = await self._process_batch()

                if processed == 0:
                    # No events to process, sleep before next poll
                    await asyncio.sleep(self._config.poll_interval)
                else:
                    # Processed events, immediately check for more
                    self._stats.batches_processed += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(
                    "Error in publisher loop",
                    extra={"publisher_id": self._config.publisher_id},
                )
                self._stats.last_error = str(e)
                self._stats.last_error_at = datetime.now(UTC)
                await asyncio.sleep(self._config.backoff_base)

    async def _process_batch(self) -> int:
        """
        Process a batch of pending events.

        Returns:
            Number of events processed
        """
        if not self._conn:
            return 0

        # Fetch pending entries with lock
        entries = await self._outbox.fetch_pending(
            self._conn,
            limit=self._config.batch_size,
            lock_token=self._config.publisher_id,
            lock_duration_seconds=self._config.lock_duration,
        )

        if not entries:
            return 0

        processed = 0
        for entry in entries:
            try:
                await self._publish_entry(entry)
                processed += 1
            except Exception as e:
                logger.warning(
                    "Failed to publish event",
                    extra={
                        "event_id": str(entry.id),
                        "topic": entry.topic,
                        "error": str(e),
                    },
                )

        return processed

    async def _publish_entry(self, entry: OutboxEntry) -> None:
        """
        Publish a single outbox entry.

        Handles success/failure marking and backoff.
        """
        if not self._conn:
            return

        try:
            envelope = entry.envelope

            # Publish to bus
            await self._bus.publish(entry.topic, envelope)

            # Mark as published
            await self._outbox.mark_published(self._conn, entry.id)

            self._stats.events_published += 1
            self._stats.last_publish_at = datetime.now(UTC)

            logger.debug(
                "Published event",
                extra={
                    "event_id": str(entry.id),
                    "topic": entry.topic,
                    "event_type": entry.event_type,
                },
            )

        except PublishError as e:
            # Bus rejected the event
            should_retry = await self._outbox.mark_failed(
                self._conn,
                entry.id,
                str(e),
                max_attempts=self._config.max_attempts,
            )

            if not should_retry:
                self._stats.events_failed += 1
                logger.error(
                    "Event permanently failed after max attempts",
                    extra={
                        "event_id": str(entry.id),
                        "topic": entry.topic,
                        "attempts": self._config.max_attempts,
                    },
                )
            else:
                # Calculate backoff for next attempt
                backoff = min(
                    self._config.backoff_base * (2**entry.attempts),
                    self._config.backoff_max,
                )
                logger.warning(
                    "Event publish failed, will retry",
                    extra={
                        "event_id": str(entry.id),
                        "attempts": entry.attempts + 1,
                        "backoff": backoff,
                    },
                )

        except Exception as e:
            # Unexpected error
            await self._outbox.mark_failed(
                self._conn,
                entry.id,
                f"Unexpected error: {e}",
                max_attempts=self._config.max_attempts,
            )
            raise

    async def drain(self, *, timeout: float = 30.0) -> int:
        """
        Drain all pending events (for testing or shutdown).

        Processes events until the outbox is empty or timeout is reached.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            Total events drained
        """
        if not self._conn:
            self._conn = await aiosqlite.connect(self._db_path)

        start = datetime.now(UTC)
        total = 0

        while True:
            elapsed = (datetime.now(UTC) - start).total_seconds()
            if elapsed >= timeout:
                logger.warning(
                    "Drain timeout reached",
                    extra={"drained": total, "timeout": timeout},
                )
                break

            processed = await self._process_batch()
            total += processed

            if processed == 0:
                break

        return total

    async def get_status(self) -> dict[str, Any]:
        """Get detailed publisher status."""
        outbox_stats = {}
        if self._conn:
            outbox_stats = await self._outbox.get_stats(self._conn)

        return {
            "running": self._running,
            "publisher_id": self._config.publisher_id,
            "started_at": self._stats.started_at.isoformat(),
            "events_published": self._stats.events_published,
            "events_failed": self._stats.events_failed,
            "batches_processed": self._stats.batches_processed,
            "last_publish_at": (
                self._stats.last_publish_at.isoformat() if self._stats.last_publish_at else None
            ),
            "last_error": self._stats.last_error,
            "last_error_at": (
                self._stats.last_error_at.isoformat() if self._stats.last_error_at else None
            ),
            "outbox": outbox_stats,
        }
