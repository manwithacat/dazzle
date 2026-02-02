"""
CLI commands for event system operations.

Provides commands to inspect, replay, and manage events in a Dazzle application.

Commands:
- dazzle events tail <topic>: Tail events from a topic
- dazzle events status: Show event system status
- dazzle events replay <topic>: Replay events from a topic
- dazzle dlq list: List dead letter queue events
- dazzle dlq replay <event_id>: Replay a single DLQ event
- dazzle outbox status: Show outbox status
- dazzle outbox drain: Drain pending outbox events
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

# =============================================================================
# Events App
# =============================================================================

events_app = typer.Typer(help="Event system commands.")


@events_app.command("tail")
def tail_events(
    topic: Annotated[str, typer.Argument(help="Topic to tail events from")],
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Follow new events")] = False,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of events to show")] = 10,
    db: Annotated[str, typer.Option("--db", help="Database path")] = "app.db",
) -> None:
    """Tail events from a topic."""
    asyncio.run(_tail_events(topic, follow, limit, db))


async def _tail_events(topic: str, follow: bool, limit: int, db_path: str) -> None:
    """Async implementation of tail command."""
    from dazzle_back.events import DevBrokerSQLite

    async with DevBrokerSQLite(db_path) as bus:
        count = 0
        async for event in bus.replay(topic):
            if count >= limit and not follow:
                break

            typer.echo(f"[{event.timestamp.isoformat()}] {event.event_type} (key={event.key})")
            typer.echo(f"  payload: {json.dumps(event.payload, default=str)[:100]}")
            count += 1

        if follow:
            typer.echo("(Following new events, Ctrl+C to stop)")
            # In a real implementation, would poll for new events


@events_app.command("status")
def event_status(
    db: Annotated[str, typer.Option("--db", help="Database path")] = "app.db",
) -> None:
    """Show event system status."""
    asyncio.run(_event_status(db))


async def _event_status(db_path: str) -> None:
    """Async implementation of status command."""
    from dazzle_back.events import DevBrokerSQLite

    if not Path(db_path).exists():
        typer.echo(f"Database not found: {db_path}")
        return

    async with DevBrokerSQLite(db_path) as bus:
        topics = await bus.list_topics()

        typer.echo("Event System Status")
        typer.echo("=" * 40)
        typer.echo(f"Topics: {len(topics)}")
        typer.echo()

        for topic in topics:
            info = await bus.get_topic_info(topic)
            typer.echo(f"Topic: {topic}")
            typer.echo(f"  Events: {info['event_count']}")
            typer.echo(f"  Consumers: {', '.join(info['consumer_groups']) or 'none'}")
            typer.echo(f"  DLQ: {info['dlq_count']}")
            typer.echo()


@events_app.command("replay")
def replay_events(
    topic: Annotated[str, typer.Argument(help="Topic to replay events from")],
    from_time: Annotated[
        str | None, typer.Option("--from", help="Start timestamp (ISO format)")
    ] = None,
    to_time: Annotated[str | None, typer.Option("--to", help="End timestamp (ISO format)")] = None,
    key: Annotated[str | None, typer.Option("--key", help="Filter by partition key")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show events without processing")
    ] = False,
    db: Annotated[str, typer.Option("--db", help="Database path")] = "app.db",
) -> None:
    """Replay events from a topic."""
    asyncio.run(_replay_events(topic, from_time, to_time, key, dry_run, db))


async def _replay_events(
    topic: str,
    from_time: str | None,
    to_time: str | None,
    key: str | None,
    dry_run: bool,
    db_path: str,
) -> None:
    """Async implementation of replay command."""
    from dazzle_back.events import DevBrokerSQLite

    from_ts = datetime.fromisoformat(from_time) if from_time else None
    to_ts = datetime.fromisoformat(to_time) if to_time else None

    async with DevBrokerSQLite(db_path) as bus:
        count = 0
        async for event in bus.replay(
            topic,
            from_timestamp=from_ts,
            to_timestamp=to_ts,
            key_filter=key,
        ):
            count += 1
            if dry_run:
                typer.echo(f"Would replay: {event.event_type} ({event.event_id})")
            else:
                typer.echo(f"Replayed: {event.event_type} ({event.event_id})")

        typer.echo(f"\nTotal: {count} events")


# =============================================================================
# DLQ (Dead Letter Queue) App
# =============================================================================

dlq_app = typer.Typer(help="Dead letter queue commands.")


@dlq_app.command("list")
def dlq_list(
    topic: Annotated[str | None, typer.Option("--topic", help="Filter by topic")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of events to show")] = 20,
    db: Annotated[str, typer.Option("--db", help="Database path")] = "app.db",
) -> None:
    """List dead letter queue events."""
    asyncio.run(_dlq_list(topic, limit, db))


async def _dlq_list(topic: str | None, limit: int, db_path: str) -> None:
    """Async implementation of dlq list command."""
    from dazzle_back.events import DevBrokerSQLite

    async with DevBrokerSQLite(db_path) as bus:
        events = await bus.get_dlq_events(topic=topic, limit=limit)

        if not events:
            typer.echo("No events in dead letter queue")
            return

        typer.echo("Dead Letter Queue Events")
        typer.echo("=" * 60)

        for entry in events:
            typer.echo(f"Event ID: {entry['event_id']}")
            typer.echo(f"  Topic: {entry['topic']}")
            typer.echo(f"  Consumer: {entry['group_id']}")
            typer.echo(f"  Reason: {entry['reason_code']} - {entry['reason_message']}")
            typer.echo(f"  Attempts: {entry['attempts']}")
            typer.echo(f"  Added: {entry['created_at']}")
            typer.echo()


@dlq_app.command("replay")
def dlq_replay(
    event_id: Annotated[str, typer.Argument(help="Event ID to replay")],
    group: Annotated[str, typer.Option("--group", help="Consumer group ID")],
    db: Annotated[str, typer.Option("--db", help="Database path")] = "app.db",
) -> None:
    """Replay a single event from the DLQ."""
    asyncio.run(_dlq_replay(event_id, group, db))


async def _dlq_replay(event_id: str, group: str, db_path: str) -> None:
    """Async implementation of dlq replay command."""
    from dazzle_back.events import DevBrokerSQLite

    async with DevBrokerSQLite(db_path) as bus:
        try:
            success = await bus.replay_dlq_event(event_id, group)
            if success:
                typer.echo(f"Successfully replayed event {event_id}")
            else:
                typer.echo(f"Event not found in DLQ: {event_id}")
        except Exception as e:
            typer.echo(f"Failed to replay event: {e}")


@dlq_app.command("clear")
def dlq_clear(
    topic: Annotated[
        str | None, typer.Option("--topic", help="Clear only events for this topic")
    ] = None,
    confirm: Annotated[bool, typer.Option("--confirm", help="Confirm deletion")] = False,
    db: Annotated[str, typer.Option("--db", help="Database path")] = "app.db",
) -> None:
    """Clear events from the dead letter queue."""
    if not confirm:
        typer.echo("Use --confirm to actually delete events")
        return

    asyncio.run(_dlq_clear(topic, db))


async def _dlq_clear(topic: str | None, db_path: str) -> None:
    """Async implementation of dlq clear command."""
    from dazzle_back.events import DevBrokerSQLite

    async with DevBrokerSQLite(db_path) as bus:
        count = await bus.clear_dlq(topic=topic)
        typer.echo(f"Cleared {count} events from DLQ")


# =============================================================================
# Outbox App
# =============================================================================

outbox_app = typer.Typer(help="Event outbox commands.")


@outbox_app.command("status")
def outbox_status(
    db: Annotated[str, typer.Option("--db", help="Database path")] = "app.db",
) -> None:
    """Show outbox status."""
    asyncio.run(_outbox_status(db))


async def _outbox_status(db_path: str) -> None:
    """Async implementation of outbox status command."""
    import aiosqlite

    from dazzle_back.events import EventOutbox

    outbox = EventOutbox()

    async with aiosqlite.connect(db_path) as conn:
        await outbox.create_table(conn)
        stats = await outbox.get_stats(conn)

        typer.echo("Outbox Status")
        typer.echo("=" * 40)
        typer.echo(f"Pending: {stats.get('pending', 0)}")
        typer.echo(f"Publishing: {stats.get('publishing', 0)}")
        typer.echo(f"Published: {stats.get('published', 0)}")
        typer.echo(f"Failed: {stats.get('failed', 0)}")

        if stats.get("oldest_pending"):
            typer.echo(f"Oldest pending: {stats['oldest_pending']}")


@outbox_app.command("drain")
def outbox_drain(
    timeout: Annotated[int, typer.Option("--timeout", help="Timeout in seconds")] = 30,
    db: Annotated[str, typer.Option("--db", help="Database path")] = "app.db",
) -> None:
    """Drain pending events from the outbox."""
    asyncio.run(_outbox_drain(timeout, db))


async def _outbox_drain(timeout: int, db_path: str) -> None:
    """Async implementation of outbox drain command."""
    from dazzle_back.events import (
        DevBrokerSQLite,
        EventOutbox,
        OutboxPublisher,
    )

    outbox = EventOutbox()

    async with DevBrokerSQLite(db_path) as bus:
        publisher = OutboxPublisher(db_path, bus, outbox)
        count = await publisher.drain(timeout=float(timeout))
        typer.echo(f"Drained {count} events from outbox")


@outbox_app.command("failed")
def outbox_failed(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of entries to show")] = 20,
    db: Annotated[str, typer.Option("--db", help="Database path")] = "app.db",
) -> None:
    """List failed outbox entries."""
    asyncio.run(_outbox_failed(limit, db))


async def _outbox_failed(limit: int, db_path: str) -> None:
    """Async implementation of outbox failed command."""
    import aiosqlite

    from dazzle_back.events import EventOutbox

    outbox = EventOutbox()

    async with aiosqlite.connect(db_path) as conn:
        entries = await outbox.get_failed_entries(conn, limit=limit)

        if not entries:
            typer.echo("No failed entries in outbox")
            return

        typer.echo("Failed Outbox Entries")
        typer.echo("=" * 60)

        for entry in entries:
            typer.echo(f"ID: {entry.id}")
            typer.echo(f"  Topic: {entry.topic}")
            typer.echo(f"  Type: {entry.event_type}")
            typer.echo(f"  Attempts: {entry.attempts}")
            typer.echo(f"  Error: {entry.last_error}")
            typer.echo(f"  Created: {entry.created_at}")
            typer.echo()
