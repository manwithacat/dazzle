"""
Tests for file storage system.

Tests local storage, metadata store, validation, and file service.
"""

from io import BytesIO
from uuid import UUID, uuid4

import pytest

from dazzle_dnr_back.runtime.file_storage import (
    FileMetadata,
    FileMetadataStore,
    FileValidationError,
    FileValidator,
    LocalStorageBackend,
    create_local_file_service,
    secure_filename,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_storage_path(tmp_path):
    """Create a temporary storage path."""
    storage_path = tmp_path / "uploads"
    storage_path.mkdir()
    return storage_path


@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary database path."""
    return tmp_path / "files.db"


@pytest.fixture
def local_storage(temp_storage_path):
    """Create a local storage backend."""
    return LocalStorageBackend(
        base_path=temp_storage_path,
        base_url="/files",
    )


@pytest.fixture
def metadata_store(temp_db_path):
    """Create a file metadata store."""
    return FileMetadataStore(temp_db_path)


@pytest.fixture
def file_service(temp_storage_path, temp_db_path):
    """Create a file service."""
    return create_local_file_service(
        base_path=temp_storage_path,
        db_path=temp_db_path,
    )


@pytest.fixture
def sample_file():
    """Create a sample file-like object."""
    content = b"Hello, World! This is a test file."
    return BytesIO(content)


@pytest.fixture
def sample_image():
    """Create a minimal valid PNG image."""
    # Minimal 1x1 red PNG
    png_data = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0'
        b'\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    return BytesIO(png_data)


@pytest.fixture
def sample_pdf():
    """Create a minimal valid PDF."""
    pdf_data = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    return BytesIO(pdf_data)


# =============================================================================
# Secure Filename Tests
# =============================================================================


class TestSecureFilename:
    """Tests for secure_filename function."""

    def test_basic_filename(self):
        """Test basic filename passes through."""
        assert secure_filename("document.pdf") == "document.pdf"

    def test_removes_path(self):
        """Test path components are removed."""
        assert secure_filename("/path/to/document.pdf") == "document.pdf"
        # Path.name returns only the final component
        assert secure_filename("../../../etc/passwd") == "passwd"

    def test_replaces_special_chars(self):
        """Test special characters are replaced."""
        assert secure_filename("my file (1).pdf") == "my_file__1_.pdf"

    def test_removes_leading_dot(self):
        """Test leading dots are removed."""
        assert secure_filename(".htaccess") == "htaccess"

    def test_limits_length(self):
        """Test filename length is limited."""
        long_name = "a" * 200 + ".pdf"
        result = secure_filename(long_name)
        assert len(result) <= 114  # 100 + "." + 10 (extension limit)

    def test_empty_becomes_unnamed(self):
        """Test empty filename becomes unnamed."""
        assert secure_filename("") == "unnamed_file"
        assert secure_filename("...") == "unnamed_file"


# =============================================================================
# FileValidator Tests
# =============================================================================


class TestFileValidator:
    """Tests for FileValidator."""

    def test_validate_valid_file(self, sample_file):
        """Test validation passes for valid file."""
        validator = FileValidator(max_size=1024 * 1024)
        is_valid, error, content_type = validator.validate(
            sample_file, "test.txt"
        )

        assert is_valid is True
        assert error is None

    def test_validate_file_too_large(self):
        """Test validation fails for oversized file."""
        validator = FileValidator(max_size=10)
        large_file = BytesIO(b"x" * 100)

        is_valid, error, _ = validator.validate(large_file, "large.txt")

        assert is_valid is False
        assert "exceeds maximum size" in error

    def test_validate_empty_file(self):
        """Test validation fails for empty file."""
        validator = FileValidator()
        empty_file = BytesIO(b"")

        is_valid, error, _ = validator.validate(empty_file, "empty.txt")

        assert is_valid is False
        assert "empty" in error.lower()

    def test_validate_allowed_types(self, sample_image):
        """Test validation with allowed types."""
        validator = FileValidator(allowed_types=["image/*"])

        is_valid, error, content_type = validator.validate(
            sample_image, "image.png"
        )

        assert is_valid is True
        assert "image" in content_type

    def test_validate_disallowed_type(self, sample_file):
        """Test validation fails for disallowed type."""
        validator = FileValidator(allowed_types=["image/*"])

        is_valid, error, _ = validator.validate(sample_file, "test.txt")

        assert is_valid is False
        assert "not allowed" in error


# =============================================================================
# LocalStorageBackend Tests
# =============================================================================


class TestLocalStorageBackend:
    """Tests for LocalStorageBackend."""

    @pytest.mark.asyncio
    async def test_store_file(self, local_storage, sample_file):
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
    async def test_store_with_prefix(self, local_storage, sample_file):
        """Test storing with path prefix."""
        metadata = await local_storage.store(
            sample_file,
            "test.txt",
            "text/plain",
            path_prefix="documents",
        )

        assert "documents" in metadata.url

    @pytest.mark.asyncio
    async def test_retrieve_file(self, local_storage, sample_file):
        """Test retrieving a stored file."""
        # Store first
        metadata = await local_storage.store(
            sample_file,
            "test.txt",
            "text/plain",
        )

        # Retrieve
        content = await local_storage.retrieve(metadata.storage_key)

        assert content == b"Hello, World! This is a test file."

    @pytest.mark.asyncio
    async def test_retrieve_not_found(self, local_storage):
        """Test retrieving non-existent file."""
        with pytest.raises(FileNotFoundError):
            await local_storage.retrieve("nonexistent/file.txt")

    @pytest.mark.asyncio
    async def test_delete_file(self, local_storage, sample_file, temp_storage_path):
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
    async def test_delete_not_found(self, local_storage):
        """Test deleting non-existent file."""
        deleted = await local_storage.delete("nonexistent/file.txt")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_stream_file(self, local_storage, sample_file):
        """Test streaming a file."""
        # Store first
        metadata = await local_storage.store(
            sample_file,
            "test.txt",
            "text/plain",
        )

        # Stream
        chunks = []
        async for chunk in local_storage.stream(metadata.storage_key):
            chunks.append(chunk)

        content = b"".join(chunks)
        assert content == b"Hello, World! This is a test file."

    def test_get_url(self, local_storage):
        """Test URL generation."""
        url = local_storage.get_url("2025/11/28/abc_test.txt")
        assert url == "/files/2025/11/28/abc_test.txt"


# =============================================================================
# FileMetadataStore Tests
# =============================================================================


class TestFileMetadataStore:
    """Tests for FileMetadataStore."""

    def test_save_and_get(self, metadata_store):
        """Test saving and retrieving metadata."""
        from datetime import datetime

        metadata = FileMetadata(
            id=uuid4(),
            filename="test.txt",
            content_type="text/plain",
            size=100,
            storage_key="2025/11/28/abc_test.txt",
            storage_backend="local",
            created_at=datetime.utcnow(),
            url="/files/2025/11/28/abc_test.txt",
        )

        metadata_store.save(metadata)
        retrieved = metadata_store.get(metadata.id)

        assert retrieved is not None
        assert retrieved.id == metadata.id
        assert retrieved.filename == "test.txt"

    def test_get_not_found(self, metadata_store):
        """Test getting non-existent metadata."""
        result = metadata_store.get(uuid4())
        assert result is None

    def test_delete(self, metadata_store):
        """Test deleting metadata."""
        from datetime import datetime

        metadata = FileMetadata(
            id=uuid4(),
            filename="test.txt",
            content_type="text/plain",
            size=100,
            storage_key="test.txt",
            storage_backend="local",
            created_at=datetime.utcnow(),
            url="/files/test.txt",
        )

        metadata_store.save(metadata)
        deleted = metadata_store.delete(metadata.id)

        assert deleted is True
        assert metadata_store.get(metadata.id) is None

    def test_get_by_entity(self, metadata_store):
        """Test getting files by entity."""
        from datetime import datetime

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
                created_at=datetime.utcnow(),
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
            created_at=datetime.utcnow(),
            url="/files/other.txt",
        )
        metadata_store.save(other_metadata)

        # Get by entity
        files = metadata_store.get_by_entity("Task", "task-123")
        assert len(files) == 3

        # Get by entity and field
        files = metadata_store.get_by_entity("Task", "task-123", "attachment")
        assert len(files) == 3

    def test_update_entity_association(self, metadata_store):
        """Test updating entity association."""
        from datetime import datetime

        metadata = FileMetadata(
            id=uuid4(),
            filename="test.txt",
            content_type="text/plain",
            size=100,
            storage_key="test.txt",
            storage_backend="local",
            created_at=datetime.utcnow(),
            url="/files/test.txt",
        )
        metadata_store.save(metadata)

        # Update association
        updated = metadata_store.update_entity_association(
            metadata.id, "Task", "task-123", "attachment"
        )

        assert updated is True

        # Verify
        retrieved = metadata_store.get(metadata.id)
        assert retrieved.entity_name == "Task"
        assert retrieved.entity_id == "task-123"
        assert retrieved.field_name == "attachment"


# =============================================================================
# FileService Tests
# =============================================================================


class TestFileService:
    """Tests for FileService."""

    @pytest.mark.asyncio
    async def test_upload(self, file_service, sample_file):
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
    async def test_upload_with_entity(self, file_service, sample_file):
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
    async def test_upload_validation_fails(self, file_service):
        """Test upload validation failure."""
        # Create oversized file
        file_service.validator.max_size = 10
        large_file = BytesIO(b"x" * 100)

        with pytest.raises(FileValidationError):
            await file_service.upload(large_file, "large.txt")

    @pytest.mark.asyncio
    async def test_download(self, file_service, sample_file):
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
    async def test_download_not_found(self, file_service):
        """Test downloading non-existent file."""
        with pytest.raises(FileNotFoundError):
            await file_service.download(uuid4())

    @pytest.mark.asyncio
    async def test_delete(self, file_service, sample_file):
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

    def test_get_metadata(self, file_service):
        """Test getting metadata without download."""
        # Metadata doesn't exist yet
        result = file_service.get_metadata(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_entity_files(self, file_service):
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

    @pytest.mark.asyncio
    async def test_associate_with_entity(self, file_service, sample_file):
        """Test associating uploaded file with entity."""
        # Upload without entity
        metadata = await file_service.upload(
            sample_file,
            "test.txt",
            "text/plain",
        )

        # Associate later
        associated = await file_service.associate_with_entity(
            metadata.id, "Task", "task-123", "attachment"
        )

        assert associated is True

        # Verify
        files = file_service.get_entity_files("Task", "task-123", "attachment")
        assert len(files) == 1
        assert files[0].id == metadata.id


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_local_file_service(self, tmp_path):
        """Test creating local file service."""
        service = create_local_file_service(
            base_path=tmp_path / "uploads",
            db_path=tmp_path / "files.db",
            base_url="/uploads",
            max_size=5 * 1024 * 1024,
            allowed_types=["image/*", "application/pdf"],
        )

        assert service is not None
        assert service.validator.max_size == 5 * 1024 * 1024
        assert service.validator.allowed_types == ["image/*", "application/pdf"]
