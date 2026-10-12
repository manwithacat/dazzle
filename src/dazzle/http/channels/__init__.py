"""
Email delivery kernel for DAZZLE.

What remains of the messaging channels after the messaging DSL was parked
(DD-007): provider detection, the email adapters, the delivery outbox table
and the SES bounce/complaint webhook the auth subsystem registers.
"""

from .adapters import BaseChannelAdapter, FileEmailAdapter, MailpitAdapter, SendResult
from .detection import (
    DetectionResult,
    ProviderDetector,
    ProviderStatus,
)
from .outbox import (
    OutboxMessage,
    OutboxRepository,
    OutboxStatus,
    create_outbox_message,
)

__all__ = [
    # Detection
    "DetectionResult",
    "ProviderDetector",
    "ProviderStatus",
    # Outbox
    "OutboxMessage",
    "OutboxRepository",
    "OutboxStatus",
    "create_outbox_message",
    # Adapters
    "BaseChannelAdapter",
    "SendResult",
    "MailpitAdapter",
    "FileEmailAdapter",
]
