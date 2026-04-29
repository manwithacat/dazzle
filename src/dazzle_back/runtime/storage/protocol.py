"""Storage backend protocol for browser-direct uploads (#932).

Defines the minimum surface a storage backend must expose for the
framework's upload-ticket / finalize auto-routes (shipping in cycle
2+) to delegate to it.

Cycle 1 lands the types only; cycle 2 lands the S3 implementation
(`s3_provider.py`) and the in-memory fake (`testing.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class UploadTicket:
    """A presigned POST policy the client uses to upload directly to
    the backing store.

    Mirrors what `boto3.client("s3").generate_presigned_post` returns,
    plus the canonical S3 key the framework allocated. The client
    POSTs `<file>` to `url` with `fields` as multipart form data.

    Attributes:
        url: Presigned POST endpoint.
        fields: Form fields the client must include verbatim
            (signature, policy, content-type, etc.).
        s3_key: The exact key under which the upload will land. The
            client echoes this back on the finalize call so the
            framework can verify the object exists.
        expires_in_seconds: Time the ticket remains valid.
    """

    url: str
    fields: dict[str, str]
    s3_key: str
    expires_in_seconds: int


@dataclass(frozen=True)
class ObjectMetadata:
    """Result of a head_object call — used by the finalize route to
    verify the client actually uploaded what it claimed."""

    key: str
    size_bytes: int
    content_type: str | None = None
    etag: str | None = None


@runtime_checkable
class StorageProvider(Protocol):
    """Backend protocol — implement this to support a new storage
    target.

    Implementations must be safe to call concurrently (the framework
    assumes the underlying client handles its own connection pooling).

    The four config attributes (`name`, `bucket`, `prefix_template`,
    `max_bytes`, `content_types`, `ticket_ttl_seconds`) are mirrored
    from `dazzle.core.manifest.StorageConfig` so route generators can
    introspect a provider without crossing module boundaries.
    """

    name: str
    bucket: str
    prefix_template: str
    max_bytes: int
    content_types: list[str]
    ticket_ttl_seconds: int

    def render_prefix(self, *, user_id: str, record_id: str) -> str:
        """Substitute `{user_id}` and `{record_id}` into
        `prefix_template`. Returns the absolute prefix the upload
        will live under (always trailing-slashed)."""

    def mint_upload_ticket(self, *, key: str, content_type: str) -> UploadTicket:
        """Generate a presigned POST policy for `key`. The
        implementation enforces:

        - content-type matches `content_type` (and is in
          `self.content_types` when that list is non-empty).
        - content-length-range up to `self.max_bytes`.
        - `key` lives under a prefix the implementation considers
          authorised (callers should pass a key produced by
          `render_prefix(...)` to avoid sandbox escapes).
        """

    def head_object(self, key: str) -> ObjectMetadata | None:
        """Return metadata for an existing object, or None if the
        object doesn't exist. The finalize route uses this to verify
        the client actually uploaded under the key it claims."""

    def get_object(self, key: str) -> bytes | None:
        """Fetch the full body of an existing object, or None if the
        object doesn't exist. Used by the framework's auto-generated
        proxy route (#942) to stream files through the server with
        cookie auth — the s3_key never leaves the server, no presigned
        URLs are exposed to the browser. Implementations should buffer
        the full body in memory; streaming will be added in a
        subsequent cycle once a real-world streaming need surfaces."""
