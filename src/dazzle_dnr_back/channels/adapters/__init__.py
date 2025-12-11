"""
Channel adapters for DAZZLE messaging.

Adapters handle the actual sending/receiving of messages through providers.
Each provider has its own adapter implementation.
"""

from .base import BaseChannelAdapter, SendResult
from .email import FileEmailAdapter, MailpitAdapter

__all__ = [
    "BaseChannelAdapter",
    "SendResult",
    "FileEmailAdapter",
    "MailpitAdapter",
]
