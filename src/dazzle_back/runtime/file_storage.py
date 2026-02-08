"""
File storage backend for DNR.

Provides local and S3-compatible storage for file uploads.
"""

from __future__ import annotations

import os
import re
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    pass


# =============================================================================
# File Metadata
# =============================================================================


class FileMetadata(BaseModel):
    """Metadata for stored files."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(description="Unique file identifier")
    filename: str = Field(description="Original filename")
    content_type: str = Field(description="MIME type")
    size: int = Field(description="File size in bytes")
    storage_key: str = Field(description="Storage path/key")
    storage_backend: str = Field(description="Backend name (local, s3)")
    entity_name: str | None = Field(default=None, description="Associated entity")
    entity_id: str | None = Field(default=None, description="Associated record ID")
    field_name: str | None = Field(default=None, description="Field name")
    thumbnail_key: str | None = Field(default=None, description="Thumbnail storage key")
    created_at: datetime = Field(description="Upload timestamp")
    url: str = Field(description="Public URL")
    thumbnail_url: str | None = Field(default=None, description="Thumbnail URL")


# =============================================================================
# Storage Backend Protocol
# =============================================================================


class StorageBackend(ABC):
    """Abstract storage backend interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name identifier."""
        pass

    @abstractmethod
    async def store(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
        path_prefix: str = "",
    ) -> FileMetadata:
        """
        Store a file and return metadata.

        Args:
            file: File-like object to store
            filename: Original filename
            content_type: MIME type
            path_prefix: Optional path prefix for organization

        Returns:
            FileMetadata with storage information
        """
        pass

    @abstractmethod
    async def retrieve(self, storage_key: str) -> bytes:
        """
        Retrieve file content.

        Args:
            storage_key: Storage path/key

        Returns:
            File content as bytes
        """
        pass

    @abstractmethod
    def stream(self, storage_key: str) -> AsyncIterator[bytes]:
        """
        Stream file content in chunks.

        Args:
            storage_key: Storage path/key

        Yields:
            File content in chunks
        """
        ...

    @abstractmethod
    async def delete(self, storage_key: str) -> bool:
        """
        Delete a file.

        Args:
            storage_key: Storage path/key

        Returns:
            True if deleted successfully
        """
        pass

    @abstractmethod
    def get_url(self, storage_key: str) -> str:
        """
        Get URL for accessing a file.

        Args:
            storage_key: Storage path/key

        Returns:
            Public or signed URL
        """
        pass


# =============================================================================
# Local Storage Backend
# =============================================================================


class LocalStorageBackend(StorageBackend):
    """
    Local filesystem storage backend.

    Stores files in a local directory, suitable for development
    and simple deployments.
    """

    def __init__(
        self,
        base_path: str | Path = ".dazzle/uploads",
        base_url: str = "/files",
    ):
        """
        Initialize local storage.

        Args:
            base_path: Directory to store files
            base_url: Base URL for file access
        """
        self.base_path = Path(base_path)
        self.base_url = base_url.rstrip("/")
        self.base_path.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "local"

    async def store(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
        path_prefix: str = "",
    ) -> FileMetadata:
        """Store file in local filesystem."""
        file_id = uuid4()
        safe_filename = secure_filename(filename)

        # Organize by date for easy cleanup
        date_path = datetime.now().strftime("%Y/%m/%d")
        relative_path = f"{path_prefix}/{date_path}" if path_prefix else date_path
        storage_key = f"{relative_path}/{file_id}_{safe_filename}"

        full_path = self.base_path / storage_key
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Read and write file content
        content = file.read()
        full_path.write_bytes(content)

        url = f"{self.base_url}/{storage_key}"

        return FileMetadata(
            id=file_id,
            filename=safe_filename,
            content_type=content_type,
            size=len(content),
            storage_key=storage_key,
            storage_backend=self.name,
            created_at=datetime.now(UTC),
            url=url,
        )

    async def retrieve(self, storage_key: str) -> bytes:
        """Retrieve file from local filesystem."""
        full_path = self.base_path / storage_key
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {storage_key}")
        return full_path.read_bytes()

    async def stream(self, storage_key: str) -> AsyncIterator[bytes]:
        """Stream file in chunks."""
        full_path = self.base_path / storage_key
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {storage_key}")

        chunk_size = 64 * 1024  # 64KB chunks
        with open(full_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    async def delete(self, storage_key: str) -> bool:
        """Delete file from local filesystem."""
        full_path = self.base_path / storage_key
        if full_path.exists():
            full_path.unlink()
            return True
        return False

    def get_url(self, storage_key: str) -> str:
        """Get URL for file access."""
        return f"{self.base_url}/{storage_key}"


# =============================================================================
# S3 Storage Backend
# =============================================================================


class S3StorageBackend(StorageBackend):
    """
    S3-compatible storage backend.

    Works with AWS S3, MinIO, and other S3-compatible services.
    """

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        public_url: str | None = None,
    ):
        """
        Initialize S3 storage.

        Args:
            bucket: S3 bucket name
            region: AWS region
            endpoint_url: Custom endpoint for MinIO etc.
            access_key: AWS access key (or from env)
            secret_key: AWS secret key (or from env)
            public_url: Optional CDN/public URL prefix
        """
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url
        self.public_url = public_url

        # Use environment variables if not provided
        self.access_key = access_key or os.environ.get("AWS_ACCESS_KEY_ID")
        self.secret_key = secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY")

    @property
    def name(self) -> str:
        return "s3"

    def _get_client_config(self) -> dict[str, str]:
        """Get boto3 client configuration."""
        config = {
            "region_name": self.region,
        }
        if self.endpoint_url:
            config["endpoint_url"] = self.endpoint_url
        if self.access_key:
            config["aws_access_key_id"] = self.access_key
        if self.secret_key:
            config["aws_secret_access_key"] = self.secret_key
        return config

    async def store(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
        path_prefix: str = "",
    ) -> FileMetadata:
        """Store file in S3."""
        try:
            import aioboto3
        except ImportError:
            raise ImportError(
                "aioboto3 is required for S3 storage. Install with: pip install aioboto3"
            )

        file_id = uuid4()
        safe_filename = secure_filename(filename)

        date_path = datetime.now().strftime("%Y/%m/%d")
        storage_key = (
            f"{path_prefix}/{date_path}/{file_id}_{safe_filename}"
            if path_prefix
            else f"{date_path}/{file_id}_{safe_filename}"
        )

        content = file.read()

        session = aioboto3.Session()
        async with session.client("s3", **self._get_client_config()) as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=storage_key,
                Body=content,
                ContentType=content_type,
            )

        url = self.get_url(storage_key)

        return FileMetadata(
            id=file_id,
            filename=safe_filename,
            content_type=content_type,
            size=len(content),
            storage_key=storage_key,
            storage_backend=self.name,
            created_at=datetime.now(UTC),
            url=url,
        )

    async def retrieve(self, storage_key: str) -> bytes:
        """Retrieve file from S3."""
        try:
            import aioboto3
        except ImportError:
            raise ImportError("aioboto3 is required for S3 storage")

        session = aioboto3.Session()
        async with session.client("s3", **self._get_client_config()) as s3:
            response = await s3.get_object(Bucket=self.bucket, Key=storage_key)
            async with response["Body"] as stream:
                data: bytes = await stream.read()
                return data

    async def stream(self, storage_key: str) -> AsyncIterator[bytes]:
        """Stream file from S3."""
        try:
            import aioboto3
        except ImportError:
            raise ImportError("aioboto3 is required for S3 storage")

        session = aioboto3.Session()
        async with session.client("s3", **self._get_client_config()) as s3:
            response = await s3.get_object(Bucket=self.bucket, Key=storage_key)
            async with response["Body"] as stream:
                async for chunk in stream.iter_chunks():
                    yield chunk

    async def delete(self, storage_key: str) -> bool:
        """Delete file from S3."""
        try:
            import aioboto3
        except ImportError:
            raise ImportError("aioboto3 is required for S3 storage")

        session = aioboto3.Session()
        async with session.client("s3", **self._get_client_config()) as s3:
            await s3.delete_object(Bucket=self.bucket, Key=storage_key)
            return True

    def get_url(self, storage_key: str) -> str:
        """Get URL for file access."""
        if self.public_url:
            return f"{self.public_url.rstrip('/')}/{storage_key}"

        if self.endpoint_url:
            return f"{self.endpoint_url}/{self.bucket}/{storage_key}"

        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{storage_key}"

    async def get_presigned_url(
        self,
        storage_key: str,
        expiry: int = 3600,
        method: str = "get_object",
    ) -> str:
        """
        Get a presigned URL for temporary access.

        Args:
            storage_key: File storage key
            expiry: URL expiry in seconds
            method: S3 operation (get_object, put_object)

        Returns:
            Presigned URL
        """
        try:
            import aioboto3
        except ImportError:
            raise ImportError("aioboto3 is required for S3 storage")

        session = aioboto3.Session()
        async with session.client("s3", **self._get_client_config()) as s3:
            url: str = await s3.generate_presigned_url(
                method,
                Params={"Bucket": self.bucket, "Key": storage_key},
                ExpiresIn=expiry,
            )
            return url


# =============================================================================
# File Metadata Store (SQLite or PostgreSQL)
# =============================================================================


class FileMetadataStore:
    """
    File metadata storage using SQLite or PostgreSQL.

    Tracks uploaded files and their associations with entities.
    Supports both SQLite (default, local dev) and PostgreSQL (production).
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        database_url: str | None = None,
    ):
        """
        Initialize metadata store.

        Args:
            db_path: Path to SQLite database (default: .dazzle/files.db)
            database_url: PostgreSQL connection URL (takes precedence over db_path)
        """
        self._database_url = database_url
        self._use_postgres = bool(database_url)

        if self._use_postgres:
            # Parse and store PostgreSQL URL
            self._pg_url = database_url
            # Normalize Heroku's postgres:// to postgresql://
            if self._pg_url and self._pg_url.startswith("postgres://"):
                self._pg_url = self._pg_url.replace("postgres://", "postgresql://", 1)
        else:
            self.db_path = Path(db_path) if db_path else Path(".dazzle/files.db")
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> Any:
        """Get a database connection (SQLite or PostgreSQL)."""
        if self._use_postgres:
            import psycopg
            from psycopg.rows import dict_row

            return psycopg.connect(self._pg_url, row_factory=dict_row)
        else:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            return conn

    def _init_db(self) -> None:
        """Initialize database tables."""
        if self._use_postgres:
            self._init_postgres_db()
        else:
            self._init_sqlite_db()

    def _init_sqlite_db(self) -> None:
        """Initialize SQLite tables."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dazzle_files (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    storage_key TEXT NOT NULL,
                    storage_backend TEXT NOT NULL,
                    entity_name TEXT,
                    entity_id TEXT,
                    field_name TEXT,
                    thumbnail_key TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_files_entity
                ON dazzle_files(entity_name, entity_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_files_field
                ON dazzle_files(entity_name, field_name)
            """)
            conn.commit()

    def _init_postgres_db(self) -> None:
        """Initialize PostgreSQL tables."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dazzle_files (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size BIGINT NOT NULL,
                    storage_key TEXT NOT NULL,
                    storage_backend TEXT NOT NULL,
                    entity_name TEXT,
                    entity_id TEXT,
                    field_name TEXT,
                    thumbnail_key TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_files_entity
                ON dazzle_files(entity_name, entity_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_files_field
                ON dazzle_files(entity_name, field_name)
            """)
            conn.commit()
        finally:
            conn.close()

    def save(self, metadata: FileMetadata) -> None:
        """Save file metadata."""
        params = (
            str(metadata.id),
            metadata.filename,
            metadata.content_type,
            metadata.size,
            metadata.storage_key,
            metadata.storage_backend,
            metadata.entity_name,
            metadata.entity_id,
            metadata.field_name,
            metadata.thumbnail_key,
            metadata.created_at.isoformat(),
        )

        if self._use_postgres:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO dazzle_files
                    (id, filename, content_type, size, storage_key, storage_backend,
                     entity_name, entity_id, field_name, thumbnail_key, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        filename = EXCLUDED.filename,
                        content_type = EXCLUDED.content_type,
                        size = EXCLUDED.size,
                        storage_key = EXCLUDED.storage_key,
                        storage_backend = EXCLUDED.storage_backend,
                        entity_name = EXCLUDED.entity_name,
                        entity_id = EXCLUDED.entity_id,
                        field_name = EXCLUDED.field_name,
                        thumbnail_key = EXCLUDED.thumbnail_key,
                        updated_at = EXCLUDED.created_at
                    """,
                    params,
                )
                conn.commit()
            finally:
                conn.close()
        else:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO dazzle_files
                    (id, filename, content_type, size, storage_key, storage_backend,
                     entity_name, entity_id, field_name, thumbnail_key, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    params,
                )
                conn.commit()

    def get(self, file_id: UUID | str) -> FileMetadata | None:
        """Get file metadata by ID."""
        if self._use_postgres:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM dazzle_files WHERE id = %s",
                    (str(file_id),),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return self._row_to_metadata(dict(row))
            finally:
                conn.close()
        else:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM dazzle_files WHERE id = ?",
                    (str(file_id),),
                ).fetchone()

                if not row:
                    return None

                return self._row_to_metadata(dict(row))

    def get_by_entity(
        self,
        entity_name: str,
        entity_id: str,
        field_name: str | None = None,
    ) -> list[FileMetadata]:
        """Get files associated with an entity."""
        if self._use_postgres:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                if field_name:
                    cursor.execute(
                        """
                        SELECT * FROM dazzle_files
                        WHERE entity_name = %s AND entity_id = %s AND field_name = %s
                        """,
                        (entity_name, entity_id, field_name),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM dazzle_files
                        WHERE entity_name = %s AND entity_id = %s
                        """,
                        (entity_name, entity_id),
                    )
                rows = cursor.fetchall()
                return [self._row_to_metadata(dict(row)) for row in rows]
            finally:
                conn.close()
        else:
            with self._get_connection() as conn:
                if field_name:
                    rows = conn.execute(
                        """
                        SELECT * FROM dazzle_files
                        WHERE entity_name = ? AND entity_id = ? AND field_name = ?
                        """,
                        (entity_name, entity_id, field_name),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT * FROM dazzle_files
                        WHERE entity_name = ? AND entity_id = ?
                        """,
                        (entity_name, entity_id),
                    ).fetchall()

                return [self._row_to_metadata(dict(row)) for row in rows]

    def delete(self, file_id: UUID | str) -> bool:
        """Delete file metadata."""
        if self._use_postgres:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM dazzle_files WHERE id = %s",
                    (str(file_id),),
                )
                rowcount = cursor.rowcount
                conn.commit()
                return bool(rowcount > 0)
            finally:
                conn.close()
        else:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM dazzle_files WHERE id = ?",
                    (str(file_id),),
                )
                conn.commit()
                return bool(cursor.rowcount > 0)

    def update_entity_association(
        self,
        file_id: UUID | str,
        entity_name: str,
        entity_id: str,
        field_name: str,
    ) -> bool:
        """Update file's entity association."""
        params = (
            entity_name,
            entity_id,
            field_name,
            datetime.now(UTC).isoformat(),
            str(file_id),
        )

        if self._use_postgres:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE dazzle_files
                    SET entity_name = %s, entity_id = %s, field_name = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    params,
                )
                rowcount = cursor.rowcount
                conn.commit()
                return bool(rowcount > 0)
            finally:
                conn.close()
        else:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    UPDATE dazzle_files
                    SET entity_name = ?, entity_id = ?, field_name = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    params,
                )
                conn.commit()
                return bool(cursor.rowcount > 0)

    def _row_to_metadata(self, row: dict[str, Any]) -> FileMetadata:
        """Convert database row to FileMetadata."""
        # Note: URL needs to be reconstructed based on backend
        # This is a simplified version; in practice, you'd use the storage backend
        storage_key = row["storage_key"]
        storage_backend = row["storage_backend"]

        if storage_backend == "local":
            url = f"/files/{storage_key}"
        else:
            url = storage_key  # S3 URLs stored directly

        thumbnail_url = None
        if row.get("thumbnail_key"):
            if storage_backend == "local":
                thumbnail_url = f"/files/{row['thumbnail_key']}"
            else:
                thumbnail_url = row["thumbnail_key"]

        return FileMetadata(
            id=UUID(row["id"]),
            filename=row["filename"],
            content_type=row["content_type"],
            size=row["size"],
            storage_key=storage_key,
            storage_backend=storage_backend,
            entity_name=row.get("entity_name"),
            entity_id=row.get("entity_id"),
            field_name=row.get("field_name"),
            thumbnail_key=row.get("thumbnail_key"),
            created_at=datetime.fromisoformat(row["created_at"]),
            url=url,
            thumbnail_url=thumbnail_url,
        )


# =============================================================================
# File Validator
# =============================================================================


class FileValidationError(Exception):
    """Raised when file validation fails."""

    def __init__(self, message: str, field: str | None = None):
        self.message = message
        self.field = field
        super().__init__(message)


class FileValidator:
    """Validate uploaded files."""

    # Dangerous MIME types that should never be allowed
    DANGEROUS_TYPES = {
        "application/x-executable",
        "application/x-msdos-program",
        "application/x-msdownload",
        "application/x-sh",
        "application/x-shellscript",
    }

    def __init__(
        self,
        max_size: int = 10 * 1024 * 1024,  # 10MB
        allowed_types: list[str] | None = None,
    ):
        """
        Initialize validator.

        Args:
            max_size: Maximum file size in bytes
            allowed_types: Allowed MIME types (supports wildcards like "image/*")
        """
        self.max_size = max_size
        self.allowed_types = allowed_types

    def validate(
        self,
        file: BinaryIO,
        filename: str,
        _declared_content_type: str | None = None,
    ) -> tuple[bool, str | None, str]:
        """
        Validate a file.

        Args:
            file: File-like object
            filename: Original filename
            declared_content_type: Content-Type from upload

        Returns:
            Tuple of (is_valid, error_message, detected_content_type)
        """
        # Check size
        file.seek(0, 2)  # Seek to end
        size = file.tell()
        file.seek(0)  # Reset

        if size > self.max_size:
            return (
                False,
                f"File exceeds maximum size of {self.max_size // (1024 * 1024)}MB",
                "",
            )

        if size == 0:
            return False, "File is empty", ""

        # Detect MIME type by content
        content_type = self._detect_mime_type(file)
        file.seek(0)

        # Check for dangerous types
        if content_type in self.DANGEROUS_TYPES:
            return False, f"File type '{content_type}' is not allowed", content_type

        # Check allowed types
        if self.allowed_types:
            if not self._matches_allowed_types(content_type):
                return (
                    False,
                    f"File type '{content_type}' not allowed. "
                    f"Allowed: {', '.join(self.allowed_types)}",
                    content_type,
                )

        return True, None, content_type

    def _detect_mime_type(self, file: BinaryIO) -> str:
        """Detect MIME type from file content."""
        try:
            import magic

            content = file.read(2048)
            file.seek(0)
            result: str = magic.from_buffer(content, mime=True)
            return result
        except ImportError:
            # Fallback: simple detection based on magic bytes
            return self._simple_mime_detection(file)

    def _simple_mime_detection(self, file: BinaryIO) -> str:
        """Simple MIME detection without python-magic."""
        header = file.read(16)
        file.seek(0)

        # Common file signatures
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if header.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
            return "image/gif"
        if header.startswith(b"%PDF"):
            return "application/pdf"
        if header.startswith(b"PK\x03\x04"):
            return "application/zip"
        if header.startswith(b"\x00\x00\x00") and b"ftyp" in header[:16]:
            return "video/mp4"

        return "application/octet-stream"

    def _matches_allowed_types(self, content_type: str) -> bool:
        """Check if content type matches allowed types."""
        if not self.allowed_types:
            return True

        for pattern in self.allowed_types:
            if pattern.endswith("/*"):
                # Wildcard match (e.g., "image/*")
                prefix = pattern[:-1]  # "image/"
                if content_type.startswith(prefix):
                    return True
            elif content_type == pattern:
                return True

        return False


# =============================================================================
# Utilities
# =============================================================================


def secure_filename(filename: str) -> str:
    """
    Sanitize filename for safe storage.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    # Get just the filename, no path
    filename = Path(filename).name

    # Remove any non-alphanumeric except dots, dashes, underscores
    filename = re.sub(r"[^\w.\-]", "_", filename)

    # Ensure it doesn't start with a dot (hidden file)
    filename = filename.lstrip(".")

    # Limit length
    if "." in filename:
        name, ext = filename.rsplit(".", 1)
        name = name[:100]
        ext = ext[:10]
        filename = f"{name}.{ext}"
    else:
        filename = filename[:100]

    # Ensure we have something
    if not filename:
        filename = "unnamed_file"

    return filename


# =============================================================================
# File Service
# =============================================================================


class FileService:
    """
    High-level file service for DNR.

    Combines storage backend, metadata store, and validation.
    """

    def __init__(
        self,
        storage: StorageBackend,
        metadata_store: FileMetadataStore,
        validator: FileValidator | None = None,
    ):
        """
        Initialize file service.

        Args:
            storage: Storage backend (local or S3)
            metadata_store: File metadata store
            validator: Optional file validator
        """
        self.storage = storage
        self.metadata_store = metadata_store
        self.validator = validator or FileValidator()

    async def upload(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str | None = None,
        entity_name: str | None = None,
        entity_id: str | None = None,
        field_name: str | None = None,
        path_prefix: str = "",
    ) -> FileMetadata:
        """
        Upload a file.

        Args:
            file: File-like object
            filename: Original filename
            content_type: MIME type (will be detected if not provided)
            entity_name: Associated entity
            entity_id: Associated record ID
            field_name: Field name
            path_prefix: Optional storage path prefix

        Returns:
            FileMetadata for the uploaded file

        Raises:
            FileValidationError: If validation fails
        """
        # Validate
        is_valid, error, detected_type = self.validator.validate(file, filename, content_type)
        if not is_valid:
            raise FileValidationError(error or "Validation failed")

        # Use detected type if not provided
        content_type = content_type or detected_type

        # Store file
        file.seek(0)
        metadata = await self.storage.store(file, filename, content_type, path_prefix)

        # Update with entity association
        if entity_name or entity_id or field_name:
            metadata = FileMetadata(
                **{
                    **metadata.model_dump(),
                    "entity_name": entity_name,
                    "entity_id": entity_id,
                    "field_name": field_name,
                }
            )

        # Save metadata
        self.metadata_store.save(metadata)

        return metadata

    async def download(self, file_id: UUID | str) -> tuple[bytes, FileMetadata]:
        """
        Download a file.

        Args:
            file_id: File ID

        Returns:
            Tuple of (content, metadata)

        Raises:
            FileNotFoundError: If file not found
        """
        metadata = self.metadata_store.get(file_id)
        if not metadata:
            raise FileNotFoundError(f"File not found: {file_id}")

        content = await self.storage.retrieve(metadata.storage_key)
        return content, metadata

    async def stream(self, file_id: UUID | str) -> tuple[AsyncIterator[bytes], FileMetadata]:
        """
        Stream a file.

        Args:
            file_id: File ID

        Returns:
            Tuple of (content iterator, metadata)
        """
        metadata = self.metadata_store.get(file_id)
        if not metadata:
            raise FileNotFoundError(f"File not found: {file_id}")

        stream = self.storage.stream(metadata.storage_key)
        return stream, metadata

    async def delete(self, file_id: UUID | str) -> bool:
        """
        Delete a file.

        Args:
            file_id: File ID

        Returns:
            True if deleted
        """
        metadata = self.metadata_store.get(file_id)
        if not metadata:
            return False

        # Delete from storage
        await self.storage.delete(metadata.storage_key)

        # Delete thumbnail if exists
        if metadata.thumbnail_key:
            await self.storage.delete(metadata.thumbnail_key)

        # Delete metadata
        return self.metadata_store.delete(file_id)

    def get_metadata(self, file_id: UUID | str) -> FileMetadata | None:
        """Get file metadata."""
        return self.metadata_store.get(file_id)

    def get_entity_files(
        self,
        entity_name: str,
        entity_id: str,
        field_name: str | None = None,
    ) -> list[FileMetadata]:
        """Get files associated with an entity."""
        return self.metadata_store.get_by_entity(entity_name, entity_id, field_name)

    async def associate_with_entity(
        self,
        file_id: UUID | str,
        entity_name: str,
        entity_id: str,
        field_name: str,
    ) -> bool:
        """Associate a file with an entity record."""
        return self.metadata_store.update_entity_association(
            file_id, entity_name, entity_id, field_name
        )


# =============================================================================
# Factory Functions
# =============================================================================


def create_local_file_service(
    base_path: str | Path = ".dazzle/uploads",
    db_path: str | Path = ".dazzle/files.db",
    base_url: str = "/files",
    max_size: int = 10 * 1024 * 1024,
    allowed_types: list[str] | None = None,
) -> FileService:
    """
    Create a file service with local storage.

    Args:
        base_path: Directory for file storage
        db_path: Path to metadata database
        base_url: Base URL for file access
        max_size: Maximum file size
        allowed_types: Allowed MIME types

    Returns:
        Configured FileService
    """
    storage = LocalStorageBackend(base_path, base_url)
    metadata_store = FileMetadataStore(db_path)
    validator = FileValidator(max_size, allowed_types)
    return FileService(storage, metadata_store, validator)


def create_s3_file_service(
    bucket: str,
    db_path: str | Path = ".dazzle/files.db",
    region: str = "us-east-1",
    endpoint_url: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    public_url: str | None = None,
    max_size: int = 10 * 1024 * 1024,
    allowed_types: list[str] | None = None,
) -> FileService:
    """
    Create a file service with S3 storage.

    Args:
        bucket: S3 bucket name
        db_path: Path to metadata database
        region: AWS region
        endpoint_url: Custom endpoint for MinIO etc.
        access_key: AWS access key
        secret_key: AWS secret key
        public_url: CDN URL prefix
        max_size: Maximum file size
        allowed_types: Allowed MIME types

    Returns:
        Configured FileService
    """
    storage = S3StorageBackend(bucket, region, endpoint_url, access_key, secret_key, public_url)
    metadata_store = FileMetadataStore(db_path)
    validator = FileValidator(max_size, allowed_types)
    return FileService(storage, metadata_store, validator)
