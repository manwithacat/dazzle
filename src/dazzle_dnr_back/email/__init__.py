"""
Email integration for DAZZLE applications.

Implements the two-stream email model:
- Inbound: Raw → Normalized pipeline
- Outbound: Event-driven sending with tracking

Design Document: dev_docs/architecture/event_first/Dazzle-Email-Integration-Spec-v1.md
"""

from .blob_store import BlobStore, LocalBlobStore, S3BlobStore, get_blob_store
from .inbound import InboundMailAdapter, MailpitInboundAdapter, RawMailArtifact
from .normalizer import EmailNormalizer, NormalizationResult
from .outbound import EmailSender, EmailSendResult

__all__ = [
    # Blob storage
    "BlobStore",
    "LocalBlobStore",
    "S3BlobStore",
    "get_blob_store",
    # Inbound
    "InboundMailAdapter",
    "MailpitInboundAdapter",
    "RawMailArtifact",
    # Normalizer
    "EmailNormalizer",
    "NormalizationResult",
    # Outbound
    "EmailSender",
    "EmailSendResult",
]
