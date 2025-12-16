"""
Channel adapters for DAZZLE messaging.

Adapters handle the actual sending/receiving of messages through providers.
Each provider has its own adapter implementation.

Adapters by channel kind:
- Email: MailpitAdapter, FileEmailAdapter
- Queue: RabbitMQAdapter, InMemoryQueueAdapter
- Stream: RedisStreamAdapter, KafkaAdapter, InMemoryStreamAdapter
"""

from .base import BaseChannelAdapter, QueueAdapter, SendResult, StreamAdapter
from .email import FileEmailAdapter, MailpitAdapter
from .queue import InMemoryQueueAdapter, RabbitMQAdapter
from .stream import InMemoryStreamAdapter, KafkaAdapter, RedisStreamAdapter

__all__ = [
    # Base classes
    "BaseChannelAdapter",
    "QueueAdapter",
    "StreamAdapter",
    "SendResult",
    # Email adapters
    "FileEmailAdapter",
    "MailpitAdapter",
    # Queue adapters
    "RabbitMQAdapter",
    "InMemoryQueueAdapter",
    # Stream adapters
    "RedisStreamAdapter",
    "KafkaAdapter",
    "InMemoryStreamAdapter",
]
