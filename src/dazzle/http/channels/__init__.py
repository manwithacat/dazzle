"""
Email delivery kernel for DAZZLE.

What remains of the messaging channels after the messaging DSL was parked
(DD-007): provider detection, the email adapters with their message type, and the SES
bounce/complaint webhook the auth subsystem registers. The delivery outbox
repository and its table were removed in flense ship AR.
"""

from .adapters import BaseChannelAdapter, FileEmailAdapter, MailpitAdapter, SendResult
from .detection import (
    DetectionResult,
    ProviderDetector,
    ProviderStatus,
)
from .outbox import (
    OutboxMessage,
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
    "OutboxStatus",
    "create_outbox_message",
    # Adapters
    "BaseChannelAdapter",
    "SendResult",
    "MailpitAdapter",
    "FileEmailAdapter",
]
