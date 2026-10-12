"""
Email channel adapters.

Adapters deliver outbox messages through an email provider:
MailpitAdapter (dev), SESAdapter (production), FileEmailAdapter (fallback).
"""

from .base import BaseChannelAdapter, EmailAdapter, SendResult
from .email import FileEmailAdapter, MailpitAdapter, SESAdapter

__all__ = [
    "BaseChannelAdapter",
    "EmailAdapter",
    "SendResult",
    "FileEmailAdapter",
    "MailpitAdapter",
    "SESAdapter",
]
