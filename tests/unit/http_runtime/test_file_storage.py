"""
Tests for file storage system.

Tests local storage, metadata store, validation, and file service.
"""

import os
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import pytest

from dazzle.http.runtime.file_storage import (
    FileMetadata,
    FileMetadataStore,
    FileService,
    FileValidationError,
    FileValidator,
    LocalStorageBackend,
    resolve_under_base,
    sanitize_storage_relpath,
    secure_filename,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_storage_path(tmp_path: Any) -> Any:
    """Create a temporary storage path."""
    storage_path = tmp_path / "uploads"
    storage_path.mkdir()
    return storage_path


@pytest.fixture
def temp_db_path(tmp_path: Any) -> Any:
    """Create a temporary database path."""
    return tmp_path / "files.db"


@pytest.fixture
def local_storage(temp_storage_path: Any) -> Any:
    """Create a local storage backend."""
    return LocalStorageBackend(
        base_path=temp_storage_path,
        base_url="/files",
    )


@pytest.fixture
def metadata_store() -> Any:
    """Create a file metadata store with clean table."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set")
    store = FileMetadataStore(database_url=database_url)
    # Clean table before each test for isolation
    from dazzle.http.runtime.pg_backend import PostgresBackend

    try:
        db = PostgresBackend(database_url)
        with db.connection() as conn:
            conn.execute("DELETE FROM dazzle_files")
    except Exception:  # best-effort test cleanup — table may not exist on a fresh DB
        pass
    return store


@pytest.fixture
def file_service(temp_storage_path: Any) -> Any:
    """Create a file service with clean table."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set")
    # Clean table before each test for isolation
    from dazzle.http.runtime.pg_backend import PostgresBackend

    try:
        db = PostgresBackend(database_url)
        with db.connection() as conn:
            conn.execute("DELETE FROM dazzle_files")
    except Exception:  # best-effort test cleanup — table may not exist on a fresh DB
        pass
    return FileService(
        LocalStorageBackend(temp_storage_path),
        FileMetadataStore(database_url=database_url),
        FileValidator(),
    )


@pytest.fixture
def sample_file() -> Any:
    """Create a sample file-like object."""
    content = b"Hello, World! This is a test file."
    return BytesIO(content)


@pytest.fixture
def sample_image() -> Any:
    """Create a minimal valid PNG image."""
    # Minimal 1x1 red PNG
    png_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
        b"\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return BytesIO(png_data)


@pytest.fixture
def sample_pdf() -> Any:
    """Create a minimal valid PDF."""
    pdf_data = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    return BytesIO(pdf_data)


# =============================================================================
# Secure Filename Tests
# =============================================================================


@pytest.mark.parametrize(
    ("raw", "safe"),
    [
        pytest.param("document.pdf", "document.pdf", id="plain-name-unchanged"),
        pytest.param("/path/to/document.pdf", "document.pdf", id="absolute-path-stripped"),
        pytest.param("../../../etc/passwd", "passwd", id="path-traversal-stripped"),
        pytest.param("my file (1).pdf", "my_file__1_.pdf", id="special-chars-replaced"),
        pytest.param(".htaccess", "htaccess", id="leading-dot-removed"),
        pytest.param("a" * 200 + ".pdf", "a" * 100 + ".pdf", id="stem-truncated-to-100"),
        pytest.param("", "unnamed_file", id="empty-becomes-unnamed"),
        pytest.param("...", "unnamed_file", id="dots-only-becomes-unnamed"),
    ],
)
def test_secure_filename(raw: str, safe: str) -> None:
    assert secure_filename(raw) == safe


# =============================================================================
# FileValidator Tests
# =============================================================================


@pytest.mark.parametrize(
    ("validator", "data", "filename", "error"),
    [
        pytest.param(
            FileValidator(max_size=10),
            b"x" * 100,
            "large.txt",
            "exceeds maximum size",
            id="too-large",
        ),
        pytest.param(FileValidator(), b"", "empty.txt", "File is empty", id="empty"),
        pytest.param(
            FileValidator(allowed_types=["image/*"]),
            b"Hello, World!",
            "test.txt",
            "not allowed",
            id="type-outside-allowlist",
        ),
    ],
)
def test_validator_rejects(validator: Any, data: bytes, filename: str, error: str) -> None:
    is_valid, message, _ = validator.validate(BytesIO(data), filename)
    assert is_valid is False
    assert message is not None and error in message


@pytest.mark.parametrize(
    ("validator", "fixture", "filename", "content_type"),
    [
        pytest.param(
            FileValidator(max_size=1024 * 1024),
            "sample_file",
            "test.txt",
            None,  # text sniffing differs with/without python-magic
            id="under-size-limit",
        ),
        pytest.param(
            FileValidator(allowed_types=["image/*"]),
            "sample_image",
            "image.png",
            "image/png",
            id="type-inside-wildcard-allowlist",
        ),
    ],
)
def test_validator_accepts(
    validator: Any, fixture: str, filename: str, content_type: str | None, request: Any
) -> None:
    is_valid, error, detected = validator.validate(request.getfixturevalue(fixture), filename)
    assert (is_valid, error) == (True, None)
    if content_type is not None:
        assert detected == content_type


# =============================================================================
# LocalStorageBackend Tests
# =============================================================================


class TestLocalStorageBackend:
    """Tests for LocalStorageBackend."""

    @pytest.mark.asyncio
    async def test_store_file(self, local_storage: Any, sample_file: Any) -> None:
        """Test storing a file."""
        metadata = await local_storage.store(
            sample_file,
            "test.txt",
            "text/plain",
        )

        assert metadata.filename == "test.txt"
        assert metadata.content_type == "text/plain"
        assert metadata.size > 0
        assert metadata.url.startswith("/files/")
        assert isinstance(metadata.id, UUID)

    @pytest.mark.asyncio
    async def test_store_with_prefix(self, local_storage: Any, sample_file: Any) -> None:
        """Test storing with path prefix."""
        metadata = await local_storage.store(
            sample_file,
            "test.txt",
            "text/plain",
            path_prefix="documents",
        )

        assert "documents" in metadata.url

    @pytest.mark.asyncio
    async def test_store_rejects_traversal_prefix(
        self, local_storage: Any, sample_file: Any, temp_storage_path: Any
    ) -> None:
        """path_prefix with .. must not write outside base_path (CodeQL #220/#221)."""
        metadata = await local_storage.store(
            sample_file,
            "evil.txt",
            "text/plain",
            path_prefix="../../outside",
        )
        written = temp_storage_path / metadata.storage_key
        assert written.exists()
        assert written.resolve().is_relative_to(temp_storage_path.resolve())
        assert ".." not in metadata.storage_key
        assert not (temp_storage_path.parent / "outside").exists()

    @pytest.mark.asyncio
    async def test_retrieve_rejects_traversal_key(self, local_storage: Any) -> None:
        """storage_key traversal cannot read outside base_path."""
        with pytest.raises((ValueError, FileNotFoundError)):
            await local_storage.retrieve("../../../etc/passwd")

    def test_sanitize_and_resolve_helpers(self, temp_storage_path: Any) -> None:
        assert sanitize_storage_relpath("../../a/b") == "a/b"
        assert sanitize_storage_relpath("/abs/x") == "abs/x"
        resolved = resolve_under_base(temp_storage_path, "docs/nested/file.txt")
        assert resolved.is_relative_to(temp_storage_path.resolve())
        with pytest.raises(ValueError):
            resolve_under_base(temp_storage_path, "")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("read", ["retrieve", "stream"])
    async def test_store_then_read_round_trips(
        self, local_storage: Any, sample_file: Any, read: str
    ) -> None:
        metadata = await local_storage.store(sample_file, "test.txt", "text/plain")

        if read == "retrieve":
            content = await local_storage.retrieve(metadata.storage_key)
        else:
            content = b"".join([c async for c in local_storage.stream(metadata.storage_key)])

        assert content == b"Hello, World! This is a test file."

    @pytest.mark.asyncio
    async def test_retrieve_not_found(self, local_storage: Any) -> None:
        """Test retrieving non-existent file."""
        with pytest.raises(FileNotFoundError):
            await local_storage.retrieve("nonexistent/file.txt")

    @pytest.mark.asyncio
    async def test_delete_file(
        self, local_storage: Any, sample_file: Any, temp_storage_path: Any
    ) -> None:
        """Test deleting a file."""
        # Store first
        metadata = await local_storage.store(
            sample_file,
            "test.txt",
            "text/plain",
        )

        # File exists
        full_path = temp_storage_path / metadata.storage_key
        assert full_path.exists()

        # Delete
        deleted = await local_storage.delete(metadata.storage_key)

        assert deleted is True
        assert not full_path.exists()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, local_storage: Any) -> None:
        """Test deleting non-existent file."""
        deleted = await local_storage.delete("nonexistent/file.txt")
        assert deleted is False

    def test_get_url(self, local_storage: Any) -> None:
        """Test URL generation."""
        url = local_storage.get_url("2025/11/28/abc_test.txt")
        assert url == "/files/2025/11/28/abc_test.txt"


# =============================================================================
# FileMetadataStore Tests
# =============================================================================


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — FileMetadataStore requires PostgreSQL",
)
class TestFileMetadataStore:
    """Tests for FileMetadataStore."""

    def test_save_and_get(self, metadata_store: Any) -> None:
        """Test saving and retrieving metadata."""

        metadata = FileMetadata(
            id=uuid4(),
            filename="test.txt",
            content_type="text/plain",
            size=100,
            storage_key="2025/11/28/abc_test.txt",
            storage_backend="local",
            created_at=datetime.now(UTC),
            url="/files/2025/11/28/abc_test.txt",
        )

        metadata_store.save(metadata)
        retrieved = metadata_store.get(metadata.id)

        assert retrieved is not None
        assert retrieved.id == metadata.id
        assert retrieved.filename == "test.txt"

    def test_get_not_found(self, metadata_store: Any) -> None:
        """Test getting non-existent metadata."""
        result = metadata_store.get(uuid4())
        assert result is None

    def test_delete(self, metadata_store: Any) -> None:
        """Test deleting metadata."""

        metadata = FileMetadata(
            id=uuid4(),
            filename="test.txt",
            content_type="text/plain",
            size=100,
            storage_key="test.txt",
            storage_backend="local",
            created_at=datetime.now(UTC),
            url="/files/test.txt",
        )

        metadata_store.save(metadata)
        deleted = metadata_store.delete(metadata.id)

        assert deleted is True
        assert metadata_store.get(metadata.id) is None

    def test_get_by_entity(self, metadata_store: Any) -> None:
        """Test getting files by entity."""

        # Save multiple files for same entity
        for i in range(3):
            metadata = FileMetadata(
                id=uuid4(),
                filename=f"file{i}.txt",
                content_type="text/plain",
                size=100,
                storage_key=f"file{i}.txt",
                storage_backend="local",
                entity_name="Task",
                entity_id="task-123",
                field_name="attachment",
                created_at=datetime.now(UTC),
                url=f"/files/file{i}.txt",
            )
            metadata_store.save(metadata)

        # Save file for different entity
        other_metadata = FileMetadata(
            id=uuid4(),
            filename="other.txt",
            content_type="text/plain",
            size=100,
            storage_key="other.txt",
            storage_backend="local",
            entity_name="Task",
            entity_id="task-456",
            created_at=datetime.now(UTC),
            url="/files/other.txt",
        )
        metadata_store.save(other_metadata)

        # Get by entity
        files = metadata_store.get_by_entity("Task", "task-123")
        assert len(files) == 3

        # Get by entity and field
        files = metadata_store.get_by_entity("Task", "task-123", "attachment")
        assert len(files) == 3


# =============================================================================
# FileService Tests
# =============================================================================


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — FileService requires PostgreSQL",
)
class TestFileService:
    """Tests for FileService."""

    @pytest.mark.asyncio
    async def test_upload(self, file_service: Any, sample_file: Any) -> None:
        """Test uploading a file."""
        metadata = await file_service.upload(
            sample_file,
            "test.txt",
            "text/plain",
        )

        assert metadata.filename == "test.txt"
        assert metadata.content_type == "text/plain"
        assert metadata.size > 0

    @pytest.mark.asyncio
    async def test_upload_with_entity(self, file_service: Any, sample_file: Any) -> None:
        """Test uploading with entity association."""
        metadata = await file_service.upload(
            sample_file,
            "test.txt",
            "text/plain",
            entity_name="Task",
            entity_id="task-123",
            field_name="attachment",
        )

        assert metadata.entity_name == "Task"
        assert metadata.entity_id == "task-123"
        assert metadata.field_name == "attachment"

    @pytest.mark.asyncio
    async def test_upload_validation_fails(self, file_service: Any) -> None:
        """Test upload validation failure."""
        # Create oversized file
        file_service.validator.max_size = 10
        large_file = BytesIO(b"x" * 100)

        with pytest.raises(FileValidationError):
            await file_service.upload(large_file, "large.txt")

    @pytest.mark.asyncio
    async def test_download(self, file_service: Any, sample_file: Any) -> None:
        """Test downloading a file."""
        # Upload first
        metadata = await file_service.upload(
            sample_file,
            "test.txt",
            "text/plain",
        )

        # Download
        content, retrieved_metadata = await file_service.download(metadata.id)

        assert content == b"Hello, World! This is a test file."
        assert retrieved_metadata.id == metadata.id

    @pytest.mark.asyncio
    async def test_download_not_found(self, file_service: Any) -> None:
        """Test downloading non-existent file."""
        with pytest.raises(FileNotFoundError):
            await file_service.download(uuid4())

    @pytest.mark.asyncio
    async def test_delete(self, file_service: Any, sample_file: Any) -> None:
        """Test deleting a file."""
        # Upload first
        metadata = await file_service.upload(
            sample_file,
            "test.txt",
            "text/plain",
        )

        # Delete
        deleted = await file_service.delete(metadata.id)

        assert deleted is True
        assert file_service.get_metadata(metadata.id) is None

    def test_get_metadata(self, file_service: Any) -> None:
        """Test getting metadata without download."""
        # Metadata doesn't exist yet
        result = file_service.get_metadata(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_entity_files(self, file_service: Any) -> None:
        """Test getting files for an entity."""
        # Upload files for entity
        for i in range(3):
            file_obj = BytesIO(f"Content {i}".encode())
            await file_service.upload(
                file_obj,
                f"file{i}.txt",
                "text/plain",
                entity_name="Task",
                entity_id="task-123",
                field_name="attachment",
            )

        files = file_service.get_entity_files("Task", "task-123")
        assert len(files) == 3
