"""Flense ship AR (ADR-0057): drop the channel delivery outbox whose repository is gone.

* ``_dazzle_outbox`` — the channel delivery outbox (``http/channels/outbox.py``
  ``OutboxRepository``). The repository was never constructed by the runtime: no
  framework path, consumer or script wrote a row, and ``ensure_framework_schema`` was
  its only creator. On a consumer database the table is empty.

The rest of the event-transport residue parked with this ship (the PostgreSQL and
in-memory buses, the ``/_dazzle/events/*`` explorer and the ``/_ops/sse/events`` live
push) is recorded in ``docs/decisions/DD-006-events-dsl.md``. ``_dazzle_event_inbox``
is **not** dropped: ``IdempotentConsumer`` deduplicates every handler registered with
``EventFramework.register_handler`` through it on the Redis path (cyfuture's
``auth.user.registered`` provisioning handler). ``_dazzle_event_outbox`` stays with the
outbox publisher. Operator sign-off for the drop: 2026-10-16 (flense plan §10.4 item 1).

``downgrade`` recreates the table with the DDL the removed ``ensure_outbox_table`` used
so a rollback to ``0024`` is schema-complete; the dropped rows are not restored.

Revision ID: 0025_flense_park_event_transport
Revises:     0024_flense_park_two_factor
"""

from alembic import op

revision = "0025_flense_park_event_transport"
down_revision = "0024_flense_park_two_factor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS _dazzle_outbox")


def downgrade() -> None:
    # The DDL the removed runtime used (channels/outbox.ensure_outbox_table at 5bba9833f).
    op.execute("""
        CREATE TABLE IF NOT EXISTS _dazzle_outbox (
            id TEXT PRIMARY KEY,
            channel_name TEXT NOT NULL,
            operation_name TEXT NOT NULL,
            message_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            recipient TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            scheduled_for TEXT,
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            last_error TEXT,
            correlation_id TEXT,
            build_id TEXT,
            metadata TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx__dazzle_outbox_status ON _dazzle_outbox(status)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx__dazzle_outbox_channel ON _dazzle_outbox(channel_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx__dazzle_outbox_scheduled ON _dazzle_outbox(scheduled_for)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx__dazzle_outbox_recipient "
        "ON _dazzle_outbox(recipient, channel_name)"
    )
