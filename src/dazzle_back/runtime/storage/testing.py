"""In-memory `StorageProvider` for tests (#932 cycle 2).

`FakeStorageProvider` satisfies the `StorageProvider` protocol with
a dict-backed store. No boto3, no network. Tests construct one
directly — no fixtures, no environment setup.

Usage::

    fake = FakeStorageProvider(name="cohort_pdfs", bucket="test-bucket",
                                prefix_template="uploads/{user_id}/{record_id}/")
    ticket = fake.mint_upload_ticket(key="uploads/u1/r1/file.pdf",
                                      content_type="application/pdf")
    fake.put_object("uploads/u1/r1/file.pdf", b"<pdf bytes>",
                    content_type="application/pdf")
    metadata = fake.head_object("uploads/u1/r1/file.pdf")
    assert metadata.size_bytes == 12

The ticket URLs returned point at `https://fake-storage.local/<bucket>`
— there's no actual server. Tests that want to round-trip a real
upload should use moto via the `[aws-test]` extra.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .protocol import ObjectMetadata, UploadTicket


@dataclass
class _StoredObject:
    body: bytes
    content_type: str | None
    etag: str


@dataclass
class FakeStorageProvider:
    """In-memory `StorageProvider` for unit tests.

    All protocol attributes are configurable via the dataclass
    constructor. Object storage lives in a private dict keyed by S3
    key.

    Attributes mirror the protocol surface; additional methods
    `put_object` and `objects` let tests seed and inspect the
    backing store directly.
    """

    name: str = "test_storage"
    bucket: str = "test-bucket"
    prefix_template: str = "uploads/{user_id}/{record_id}/"
    max_bytes: int = 50 * 1024 * 1024
    content_types: list[str] = field(default_factory=list)
    ticket_ttl_seconds: int = 600

    _objects: dict[str, _StoredObject] = field(default_factory=dict, repr=False)
    minted_tickets: list[UploadTicket] = field(default_factory=list, repr=False)

    # ── Protocol surface ──────────────────────────────────────────

    def render_prefix(self, *, user_id: str, record_id: str) -> str:
        return self.prefix_template.format(user_id=user_id, record_id=record_id)

    def mint_upload_ticket(
        self,
        *,
        key: str,
        content_type: str,
    ) -> UploadTicket:
        ticket = UploadTicket(
            url=f"https://fake-storage.local/{self.bucket}",
            fields={
                "key": key,
                "Content-Type": content_type,
                "x-fake-policy": "ok",
            },
            s3_key=key,
            expires_in_seconds=self.ticket_ttl_seconds,
        )
        self.minted_tickets.append(ticket)
        return ticket

    def head_object(self, key: str) -> ObjectMetadata | None:
        obj = self._objects.get(key)
        if obj is None:
            return None
        return ObjectMetadata(
            key=key,
            size_bytes=len(obj.body),
            content_type=obj.content_type,
            etag=obj.etag,
        )

    # ── Test-only helpers ─────────────────────────────────────────

    def put_object(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        """Seed an object as if a client had finished uploading."""
        etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
        self._objects[key] = _StoredObject(body=body, content_type=content_type, etag=etag)

    def objects(self) -> dict[str, bytes]:
        """Snapshot of (key → body) for assertion convenience."""
        return {k: v.body for k, v in self._objects.items()}

    def reset(self) -> None:
        """Drop every object + minted ticket. Useful as a per-test
        fixture finaliser."""
        self._objects.clear()
        self.minted_tickets.clear()
