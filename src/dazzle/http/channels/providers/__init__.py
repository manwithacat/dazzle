"""
Email provider detectors: Mailpit, SendGrid, SES, file fallback.
"""

from .email import (
    FileEmailDetector,
    MailpitDetector,
    SendGridDetector,
    SESDetector,
)

__all__ = [
    "MailpitDetector",
    "SendGridDetector",
    "SESDetector",
    "FileEmailDetector",
]
