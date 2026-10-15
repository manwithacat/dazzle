"""The outbound message the email adapters send (``http/channels/outbox.py``).

The delivery outbox repository and its ``_dazzle_outbox`` table were removed in
flense ship AR; only the message shape and its factory remain.
"""

from datetime import UTC, datetime, timedelta

from dazzle.http.channels.outbox import OutboxStatus, create_outbox_message


def test_create_outbox_message() -> None:
    scheduled = datetime.now(UTC) + timedelta(hours=1)
    msg = create_outbox_message(
        channel_name="notifications",
        operation_name="welcome",
        message_type="WelcomeEmail",
        payload={"to": "user@example.com", "subject": "Welcome!"},
        recipient="user@example.com",
        scheduled_for=scheduled,
    )

    assert msg.channel_name == "notifications"
    assert msg.operation_name == "welcome"
    assert msg.message_type == "WelcomeEmail"
    assert msg.recipient == "user@example.com"
    assert msg.status == OutboxStatus.PENDING
    assert msg.attempts == 0
    assert msg.scheduled_for == scheduled
    assert msg.metadata == {}
    assert msg.id
