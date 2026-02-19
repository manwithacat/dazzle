"""
Channel provider implementations for DAZZLE messaging.

This module contains detectors and adapters for:
- Email: Mailpit, SendGrid, SES, SMTP, file fallback
- Queue: RabbitMQ, SQS, memory fallback
- Stream: Redis, Kafka, memory fallback
"""

from .email import (
    FileEmailDetector,
    MailpitDetector,
    SendGridDetector,
    SESDetector,
)
from .queue import (
    InMemoryQueueDetector,
    RabbitMQDetector,
)
from .stream import (
    InMemoryStreamDetector,
    RedisDetector,
)

__all__ = [
    # Email
    "MailpitDetector",
    "SendGridDetector",
    "SESDetector",
    "FileEmailDetector",
    # Queue
    "RabbitMQDetector",
    "InMemoryQueueDetector",
    # Stream
    "RedisDetector",
    "InMemoryStreamDetector",
]
