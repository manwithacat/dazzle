"""
Blob storage for email content.

Stores raw email content and attachments separately from events.
Events contain pointers to blobs, not the content itself.

Implementations:
- LocalBlobStore: File-based for development
- S3BlobStore: AWS S3 for production
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger("dazzle.email.blob_store")


@dataclass
class BlobMetadata:
    """Metadata for a stored blob."""

    pointer: str  # Unique identifier for retrieval
    sha256: str  # Content hash
    size_bytes: int  # Content size
    content_type: str  # MIME type
    created_at: datetime
    metadata: dict[str, str]  # Additional metadata


class BlobStore(ABC):
    """Abstract interface for blob storage.

    All blob operations are idempotent - storing the same content
    twice returns the same pointer (content-addressable option)
    or a new pointer (unique option).
    """

    @abstractmethod
    async def store(
        self,
        content: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
        prefix: str = "",
    ) -> BlobMetadata:
        """Store content and return metadata with pointer.

        Args:
            content: Raw bytes to store
            content_type: MIME type
            metadata: Additional metadata
            prefix: Path prefix (e.g., "raw/", "attachments/")

        Returns:
            BlobMetadata with pointer for retrieval
        """
        ...

    @abstractmethod
    async def retrieve(self, pointer: str) -> bytes | None:
        """Retrieve content by pointer.

        Args:
            pointer: Blob pointer from store()

        Returns:
            Content bytes or None if not found
        """
        ...

    @abstractmethod
    async def delete(self, pointer: str) -> bool:
        """Delete a blob.

        Args:
            pointer: Blob pointer

        Returns:
            True if deleted, False if not found
        """
        ...

    @abstractmethod
    async def get_metadata(self, pointer: str) -> BlobMetadata | None:
        """Get metadata for a blob.

        Args:
            pointer: Blob pointer

        Returns:
            Metadata or None if not found
        """
        ...

    @abstractmethod
    async def exists(self, pointer: str) -> bool:
        """Check if a blob exists.

        Args:
            pointer: Blob pointer

        Returns:
            True if exists
        """
        ...


class LocalBlobStore(BlobStore):
    """File-based blob store for development.

    Stores blobs in a local directory with metadata sidecar files.
    """

    def __init__(self, base_path: Path | str | None = None):
        """Initialize local blob store.

        Args:
            base_path: Base directory for storage.
                       Defaults to .dazzle/mailstore/
        """
        if base_path is None:
            base_path = Path.cwd() / ".dazzle" / "mailstore"
        self._base_path = Path(base_path)
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the store directory."""
        self._base_path.mkdir(parents=True, exist_ok=True)
        (self._base_path / "raw").mkdir(exist_ok=True)
        (self._base_path / "attachments").mkdir(exist_ok=True)
        (self._base_path / "metadata").mkdir(exist_ok=True)
        self._initialized = True
        logger.info(f"LocalBlobStore initialized at {self._base_path}")

    def _ensure_initialized(self) -> None:
        """Ensure store is initialized."""
        if not self._initialized:
            # Sync initialization for convenience
            self._base_path.mkdir(parents=True, exist_ok=True)
            (self._base_path / "raw").mkdir(exist_ok=True)
            (self._base_path / "attachments").mkdir(exist_ok=True)
            (self._base_path / "metadata").mkdir(exist_ok=True)
            self._initialized = True

    def _pointer_to_path(self, pointer: str) -> Path:
        """Convert pointer to file path."""
        # Pointer format: prefix/uuid or just uuid
        return self._base_path / pointer

    def _metadata_path(self, pointer: str) -> Path:
        """Get metadata sidecar path for a pointer."""
        return self._base_path / "metadata" / f"{pointer.replace('/', '_')}.json"

    async def store(
        self,
        content: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
        prefix: str = "raw",
    ) -> BlobMetadata:
        """Store content to local filesystem."""
        self._ensure_initialized()

        # Generate unique ID
        blob_id = str(uuid.uuid4())
        pointer = f"{prefix}/{blob_id}" if prefix else blob_id

        # Compute hash
        sha256 = hashlib.sha256(content).hexdigest()

        # Store content
        content_path = self._pointer_to_path(pointer)
        content_path.parent.mkdir(parents=True, exist_ok=True)
        content_path.write_bytes(content)

        # Store metadata
        blob_meta = BlobMetadata(
            pointer=pointer,
            sha256=sha256,
            size_bytes=len(content),
            content_type=content_type,
            created_at=datetime.now(UTC),
            metadata=metadata or {},
        )

        meta_path = self._metadata_path(pointer)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(
                {
                    "pointer": blob_meta.pointer,
                    "sha256": blob_meta.sha256,
                    "size_bytes": blob_meta.size_bytes,
                    "content_type": blob_meta.content_type,
                    "created_at": blob_meta.created_at.isoformat(),
                    "metadata": blob_meta.metadata,
                },
                indent=2,
            )
        )

        logger.debug(f"Stored blob: {pointer} ({blob_meta.size_bytes} bytes)")
        return blob_meta

    async def retrieve(self, pointer: str) -> bytes | None:
        """Retrieve content from local filesystem."""
        self._ensure_initialized()
        path = self._pointer_to_path(pointer)
        if path.exists():
            return path.read_bytes()
        return None

    async def delete(self, pointer: str) -> bool:
        """Delete blob and metadata."""
        self._ensure_initialized()
        content_path = self._pointer_to_path(pointer)
        meta_path = self._metadata_path(pointer)

        deleted = False
        if content_path.exists():
            content_path.unlink()
            deleted = True
        if meta_path.exists():
            meta_path.unlink()
            deleted = True

        return deleted

    async def get_metadata(self, pointer: str) -> BlobMetadata | None:
        """Get metadata from sidecar file."""
        self._ensure_initialized()
        meta_path = self._metadata_path(pointer)

        if not meta_path.exists():
            return None

        try:
            data = json.loads(meta_path.read_text())
            return BlobMetadata(
                pointer=data["pointer"],
                sha256=data["sha256"],
                size_bytes=data["size_bytes"],
                content_type=data["content_type"],
                created_at=datetime.fromisoformat(data["created_at"]),
                metadata=data.get("metadata", {}),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to read metadata for {pointer}: {e}")
            return None

    async def exists(self, pointer: str) -> bool:
        """Check if blob exists."""
        self._ensure_initialized()
        return self._pointer_to_path(pointer).exists()


class S3BlobStore(BlobStore):
    """AWS S3 blob store for production.

    Requires boto3 and AWS credentials.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "mailstore/",
        region: str | None = None,
    ):
        """Initialize S3 blob store.

        Args:
            bucket: S3 bucket name
            prefix: Key prefix within bucket
            region: AWS region (optional, uses default)
        """
        self._bucket = bucket
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._region = region
        self._client: Any = None

    async def initialize(self) -> None:
        """Initialize S3 client."""
        try:
            import boto3

            self._client = boto3.client("s3", region_name=self._region)
            logger.info(f"S3BlobStore initialized: s3://{self._bucket}/{self._prefix}")
        except ImportError:
            raise ImportError("boto3 is required for S3BlobStore. Install with: pip install boto3")

    def _full_key(self, pointer: str) -> str:
        """Get full S3 key for a pointer."""
        return f"{self._prefix}{pointer}"

    async def store(
        self,
        content: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
        prefix: str = "raw",
    ) -> BlobMetadata:
        """Store content to S3."""
        if not self._client:
            await self.initialize()

        blob_id = str(uuid.uuid4())
        pointer = f"{prefix}/{blob_id}" if prefix else blob_id
        sha256 = hashlib.sha256(content).hexdigest()

        # S3 metadata must be strings
        s3_metadata = {
            "sha256": sha256,
            "created_at": datetime.now(UTC).isoformat(),
            **(metadata or {}),
        }

        self._client.put_object(
            Bucket=self._bucket,
            Key=self._full_key(pointer),
            Body=content,
            ContentType=content_type,
            Metadata=s3_metadata,
        )

        return BlobMetadata(
            pointer=pointer,
            sha256=sha256,
            size_bytes=len(content),
            content_type=content_type,
            created_at=datetime.now(UTC),
            metadata=metadata or {},
        )

    async def retrieve(self, pointer: str) -> bytes | None:
        """Retrieve content from S3."""
        if not self._client:
            await self.initialize()

        try:
            response = self._client.get_object(
                Bucket=self._bucket,
                Key=self._full_key(pointer),
            )
            return response["Body"].read()  # type: ignore[no-any-return]
        except self._client.exceptions.NoSuchKey:
            return None

    async def delete(self, pointer: str) -> bool:
        """Delete from S3."""
        if not self._client:
            await self.initialize()

        try:
            self._client.delete_object(
                Bucket=self._bucket,
                Key=self._full_key(pointer),
            )
            return True
        except Exception:
            return False

    async def get_metadata(self, pointer: str) -> BlobMetadata | None:
        """Get metadata from S3 object."""
        if not self._client:
            await self.initialize()

        try:
            response = self._client.head_object(
                Bucket=self._bucket,
                Key=self._full_key(pointer),
            )
            s3_meta = response.get("Metadata", {})
            return BlobMetadata(
                pointer=pointer,
                sha256=s3_meta.get("sha256", ""),
                size_bytes=response.get("ContentLength", 0),
                content_type=response.get("ContentType", "application/octet-stream"),
                created_at=datetime.fromisoformat(s3_meta.get("created_at", datetime.now(UTC).isoformat())),
                metadata={k: v for k, v in s3_meta.items() if k not in ("sha256", "created_at")},
            )
        except Exception:
            return None

    async def exists(self, pointer: str) -> bool:
        """Check if object exists in S3."""
        if not self._client:
            await self.initialize()

        try:
            self._client.head_object(
                Bucket=self._bucket,
                Key=self._full_key(pointer),
            )
            return True
        except Exception:
            return False


def get_blob_store() -> BlobStore:
    """Get appropriate blob store based on environment.

    Environment variables:
        DAZZLE_ENV: 'dev' or 'prod'
        DAZZLE_BLOB_STORE: 'local' or 's3'
        DAZZLE_S3_BUCKET: S3 bucket name (required for s3)
        DAZZLE_S3_PREFIX: S3 key prefix (optional)
        DAZZLE_MAILSTORE_PATH: Local path (optional for local)

    Returns:
        Configured BlobStore instance
    """
    env = os.environ.get("DAZZLE_ENV", "dev")
    store_type = os.environ.get("DAZZLE_BLOB_STORE", "local" if env == "dev" else "s3")

    if store_type == "s3":
        bucket = os.environ.get("DAZZLE_S3_BUCKET")
        if not bucket:
            raise ValueError("DAZZLE_S3_BUCKET environment variable required for S3 blob store")
        prefix = os.environ.get("DAZZLE_S3_PREFIX", "mailstore/")
        return S3BlobStore(bucket=bucket, prefix=prefix)
    else:
        path = os.environ.get("DAZZLE_MAILSTORE_PATH")
        return LocalBlobStore(base_path=path)
