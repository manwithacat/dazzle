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

import click


@click.group()
def events() -> None:
    """Event system commands."""
    pass


@events.command("tail")
@click.argument("topic")
@click.option("--follow", "-f", is_flag=True, help="Follow new events")
@click.option("--limit", "-n", default=10, help="Number of events to show")
@click.option("--db", default="app.db", help="Database path")
def tail_events(topic: str, follow: bool, limit: int, db: str) -> None:
    """Tail events from a topic."""
    asyncio.run(_tail_events(topic, follow, limit, db))


async def _tail_events(topic: str, follow: bool, limit: int, db_path: str) -> None:
    """Async implementation of tail command."""
    from dazzle_dnr_back.events import DevBrokerSQLite

    async with DevBrokerSQLite(db_path) as bus:
        count = 0
        async for event in bus.replay(topic):
            if count >= limit and not follow:
                break

            click.echo(f"[{event.timestamp.isoformat()}] {event.event_type} (key={event.key})")
            click.echo(f"  payload: {json.dumps(event.payload, default=str)[:100]}")
            count += 1

        if follow:
            click.echo("(Following new events, Ctrl+C to stop)")
            # In a real implementation, would poll for new events


@events.command("status")
@click.option("--db", default="app.db", help="Database path")
def event_status(db: str) -> None:
    """Show event system status."""
    asyncio.run(_event_status(db))


async def _event_status(db_path: str) -> None:
    """Async implementation of status command."""
    from dazzle_dnr_back.events import DevBrokerSQLite

    if not Path(db_path).exists():
        click.echo(f"Database not found: {db_path}")
        return

    async with DevBrokerSQLite(db_path) as bus:
        topics = await bus.list_topics()

        click.echo("Event System Status")
        click.echo("=" * 40)
        click.echo(f"Topics: {len(topics)}")
        click.echo()

        for topic in topics:
            info = await bus.get_topic_info(topic)
            click.echo(f"Topic: {topic}")
            click.echo(f"  Events: {info['event_count']}")
            click.echo(f"  Consumers: {', '.join(info['consumer_groups']) or 'none'}")
            click.echo(f"  DLQ: {info['dlq_count']}")
            click.echo()


@events.command("replay")
@click.argument("topic")
@click.option("--from", "from_time", help="Start timestamp (ISO format)")
@click.option("--to", "to_time", help="End timestamp (ISO format)")
@click.option("--key", help="Filter by partition key")
@click.option("--dry-run", is_flag=True, help="Show events without processing")
@click.option("--db", default="app.db", help="Database path")
def replay_events(
    topic: str,
    from_time: str | None,
    to_time: str | None,
    key: str | None,
    dry_run: bool,
    db: str,
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
    from dazzle_dnr_back.events import DevBrokerSQLite

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
                click.echo(f"Would replay: {event.event_type} ({event.event_id})")
            else:
                click.echo(f"Replayed: {event.event_type} ({event.event_id})")

        click.echo(f"\nTotal: {count} events")


@click.group()
def dlq() -> None:
    """Dead letter queue commands."""
    pass


@dlq.command("list")
@click.option("--topic", help="Filter by topic")
@click.option("--limit", "-n", default=20, help="Number of events to show")
@click.option("--db", default="app.db", help="Database path")
def dlq_list(topic: str | None, limit: int, db: str) -> None:
    """List dead letter queue events."""
    asyncio.run(_dlq_list(topic, limit, db))


async def _dlq_list(topic: str | None, limit: int, db_path: str) -> None:
    """Async implementation of dlq list command."""
    from dazzle_dnr_back.events import DevBrokerSQLite

    async with DevBrokerSQLite(db_path) as bus:
        events = await bus.get_dlq_events(topic=topic, limit=limit)

        if not events:
            click.echo("No events in dead letter queue")
            return

        click.echo("Dead Letter Queue Events")
        click.echo("=" * 60)

        for entry in events:
            click.echo(f"Event ID: {entry['event_id']}")
            click.echo(f"  Topic: {entry['topic']}")
            click.echo(f"  Consumer: {entry['group_id']}")
            click.echo(f"  Reason: {entry['reason_code']} - {entry['reason_message']}")
            click.echo(f"  Attempts: {entry['attempts']}")
            click.echo(f"  Added: {entry['created_at']}")
            click.echo()


@dlq.command("replay")
@click.argument("event_id")
@click.option("--group", required=True, help="Consumer group ID")
@click.option("--db", default="app.db", help="Database path")
def dlq_replay(event_id: str, group: str, db: str) -> None:
    """Replay a single event from the DLQ."""
    asyncio.run(_dlq_replay(event_id, group, db))


async def _dlq_replay(event_id: str, group: str, db_path: str) -> None:
    """Async implementation of dlq replay command."""
    from dazzle_dnr_back.events import DevBrokerSQLite

    async with DevBrokerSQLite(db_path) as bus:
        try:
            success = await bus.replay_dlq_event(event_id, group)
            if success:
                click.echo(f"Successfully replayed event {event_id}")
            else:
                click.echo(f"Event not found in DLQ: {event_id}")
        except Exception as e:
            click.echo(f"Failed to replay event: {e}")


@dlq.command("clear")
@click.option("--topic", help="Clear only events for this topic")
@click.option("--confirm", is_flag=True, help="Confirm deletion")
@click.option("--db", default="app.db", help="Database path")
def dlq_clear(topic: str | None, confirm: bool, db: str) -> None:
    """Clear events from the dead letter queue."""
    if not confirm:
        click.echo("Use --confirm to actually delete events")
        return

    asyncio.run(_dlq_clear(topic, db))


async def _dlq_clear(topic: str | None, db_path: str) -> None:
    """Async implementation of dlq clear command."""
    from dazzle_dnr_back.events import DevBrokerSQLite

    async with DevBrokerSQLite(db_path) as bus:
        count = await bus.clear_dlq(topic=topic)
        click.echo(f"Cleared {count} events from DLQ")


@click.group()
def outbox() -> None:
    """Event outbox commands."""
    pass


@outbox.command("status")
@click.option("--db", default="app.db", help="Database path")
def outbox_status(db: str) -> None:
    """Show outbox status."""
    asyncio.run(_outbox_status(db))


async def _outbox_status(db_path: str) -> None:
    """Async implementation of outbox status command."""
    import aiosqlite

    from dazzle_dnr_back.events import EventOutbox

    outbox = EventOutbox()

    async with aiosqlite.connect(db_path) as conn:
        await outbox.create_table(conn)
        stats = await outbox.get_stats(conn)

        click.echo("Outbox Status")
        click.echo("=" * 40)
        click.echo(f"Pending: {stats.get('pending', 0)}")
        click.echo(f"Publishing: {stats.get('publishing', 0)}")
        click.echo(f"Published: {stats.get('published', 0)}")
        click.echo(f"Failed: {stats.get('failed', 0)}")

        if stats.get("oldest_pending"):
            click.echo(f"Oldest pending: {stats['oldest_pending']}")


@outbox.command("drain")
@click.option("--timeout", default=30, help="Timeout in seconds")
@click.option("--db", default="app.db", help="Database path")
def outbox_drain(timeout: int, db: str) -> None:
    """Drain pending events from the outbox."""
    asyncio.run(_outbox_drain(timeout, db))


async def _outbox_drain(timeout: int, db_path: str) -> None:
    """Async implementation of outbox drain command."""
    from dazzle_dnr_back.events import (
        DevBrokerSQLite,
        EventOutbox,
        OutboxPublisher,
    )

    outbox = EventOutbox()

    async with DevBrokerSQLite(db_path) as bus:
        publisher = OutboxPublisher(db_path, bus, outbox)
        count = await publisher.drain(timeout=float(timeout))
        click.echo(f"Drained {count} events from outbox")


@outbox.command("failed")
@click.option("--limit", "-n", default=20, help="Number of entries to show")
@click.option("--db", default="app.db", help="Database path")
def outbox_failed(limit: int, db: str) -> None:
    """List failed outbox entries."""
    asyncio.run(_outbox_failed(limit, db))


async def _outbox_failed(limit: int, db_path: str) -> None:
    """Async implementation of outbox failed command."""
    import aiosqlite

    from dazzle_dnr_back.events import EventOutbox

    outbox = EventOutbox()

    async with aiosqlite.connect(db_path) as conn:
        entries = await outbox.get_failed_entries(conn, limit=limit)

        if not entries:
            click.echo("No failed entries in outbox")
            return

        click.echo("Failed Outbox Entries")
        click.echo("=" * 60)

        for entry in entries:
            click.echo(f"ID: {entry.id}")
            click.echo(f"  Topic: {entry.topic}")
            click.echo(f"  Type: {entry.event_type}")
            click.echo(f"  Attempts: {entry.attempts}")
            click.echo(f"  Error: {entry.last_error}")
            click.echo(f"  Created: {entry.created_at}")
            click.echo()
