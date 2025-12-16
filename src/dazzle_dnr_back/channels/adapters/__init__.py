"""
Channel adapters for DAZZLE messaging.

Adapters handle the actual sending/receiving of messages through providers.
Each provider has its own adapter implementation.
"""

from .base import BaseChannelAdapter, SendResult
from .email import FileEmailAdapter, MailpitAdapter
from .queue import InMemoryQueueAdapter, RabbitMQAdapter
from .stream import InMemoryStreamAdapter, KafkaAdapter, RedisAdapter

__all__ = [
    "BaseChannelAdapter",
    "SendResult",
    "FileEmailAdapter",
    "MailpitAdapter",
    "RabbitMQAdapter",
    "InMemoryQueueAdapter",
    "RedisAdapter",
    "KafkaAdapter",
    "InMemoryStreamAdapter",
]
