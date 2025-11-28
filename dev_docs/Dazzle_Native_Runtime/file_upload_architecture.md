# DNR File Upload Architecture

**Date**: 2025-11-28
**Status**: Implementation Phase
**Phase**: Week 9-10

---

## Overview

This document defines the architecture for file uploads and rich fields in DNR, supporting both local storage (development) and S3-compatible storage (production).

---

## Field Type Extensions

### New Scalar Types

```python
class ScalarType(str, Enum):
    # ... existing types ...
    FILE = "file"           # File upload field
    IMAGE = "image"         # Image upload with preview/thumbnail
    RICHTEXT = "richtext"   # Markdown/HTML rich text
```

### File Field Configuration

```python
class FileFieldConfig(BaseModel):
    """Configuration for file/image fields."""

    # Storage
    max_size: int = 10 * 1024 * 1024  # 10MB default
    allowed_types: list[str] | None = None  # MIME types, e.g., ["image/png", "image/jpeg"]

    # Image-specific
    generate_thumbnail: bool = False
    thumbnail_size: tuple[int, int] = (200, 200)

    # Storage backend override
    storage_backend: str | None = None  # "local", "s3", or custom
```

### Rich Text Configuration

```python
class RichTextConfig(BaseModel):
    """Configuration for rich text fields."""

    format: Literal["markdown", "html"] = "markdown"
    max_length: int | None = None
    allow_images: bool = True  # Allow inline images
    sanitize: bool = True  # Sanitize HTML output
```

---

## Storage Architecture

### Storage Backend Protocol

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, AsyncIterator

class FileMetadata(BaseModel):
    """Metadata for stored files."""
    id: UUID
    filename: str
    content_type: str
    size: int
    created_at: datetime
    url: str
    thumbnail_url: str | None = None

class StorageBackend(ABC):
    """Abstract storage backend interface."""

    @abstractmethod
    async def store(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
        path_prefix: str = "",
    ) -> FileMetadata:
        """Store a file and return metadata."""
        pass

    @abstractmethod
    async def retrieve(self, file_id: UUID) -> AsyncIterator[bytes]:
        """Retrieve file content as async iterator."""
        pass

    @abstractmethod
    async def delete(self, file_id: UUID) -> bool:
        """Delete a file."""
        pass

    @abstractmethod
    async def get_url(self, file_id: UUID, expiry: int = 3600) -> str:
        """Get a URL for accessing the file."""
        pass
```

### Local Storage Backend

For development and simple deployments:

```python
class LocalStorageBackend(StorageBackend):
    """Local filesystem storage."""

    def __init__(
        self,
        base_path: Path = Path(".dazzle/uploads"),
        base_url: str = "/files",
    ):
        self.base_path = base_path
        self.base_url = base_url
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def store(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
        path_prefix: str = "",
    ) -> FileMetadata:
        file_id = uuid4()
        safe_filename = secure_filename(filename)

        # Organize by date for easy cleanup
        date_path = datetime.now().strftime("%Y/%m/%d")
        full_path = self.base_path / path_prefix / date_path / f"{file_id}_{safe_filename}"
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        content = file.read()
        full_path.write_bytes(content)

        # Generate thumbnail for images
        thumbnail_url = None
        if content_type.startswith("image/"):
            thumbnail_url = await self._generate_thumbnail(full_path, file_id)

        return FileMetadata(
            id=file_id,
            filename=safe_filename,
            content_type=content_type,
            size=len(content),
            created_at=datetime.utcnow(),
            url=f"{self.base_url}/{path_prefix}/{date_path}/{file_id}_{safe_filename}",
            thumbnail_url=thumbnail_url,
        )
```

### S3-Compatible Storage Backend

For production with AWS S3, MinIO, or compatible services:

```python
class S3StorageBackend(StorageBackend):
    """S3-compatible storage (AWS S3, MinIO, etc.)."""

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        endpoint_url: str | None = None,  # For MinIO
        access_key: str | None = None,
        secret_key: str | None = None,
        public_url: str | None = None,  # CDN URL
    ):
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url
        self.public_url = public_url

        # Use environment variables if not provided
        self.access_key = access_key or os.environ.get("AWS_ACCESS_KEY_ID")
        self.secret_key = secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY")

    async def store(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
        path_prefix: str = "",
    ) -> FileMetadata:
        import aioboto3

        file_id = uuid4()
        safe_filename = secure_filename(filename)
        key = f"{path_prefix}/{datetime.now():%Y/%m/%d}/{file_id}_{safe_filename}"

        session = aioboto3.Session()
        async with session.client(
            "s3",
            region_name=self.region,
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        ) as s3:
            content = file.read()
            await s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
            )

        url = self._get_object_url(key)

        return FileMetadata(
            id=file_id,
            filename=safe_filename,
            content_type=content_type,
            size=len(content),
            created_at=datetime.utcnow(),
            url=url,
        )
```

---

## Database Schema

### Files Table

```sql
CREATE TABLE dnr_files (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    storage_key TEXT NOT NULL,     -- Path/key in storage backend
    storage_backend TEXT NOT NULL,  -- "local", "s3", etc.
    entity_name TEXT,              -- Associated entity (nullable)
    entity_id TEXT,                -- Associated record ID (nullable)
    field_name TEXT,               -- Field this file belongs to
    thumbnail_key TEXT,            -- Thumbnail storage key
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE INDEX idx_files_entity ON dnr_files(entity_name, entity_id);
CREATE INDEX idx_files_field ON dnr_files(entity_name, field_name);
```

### Entity Field Storage

File fields store the file UUID as a reference:

```json
{
  "id": "task-123",
  "title": "My Task",
  "attachment": "file-uuid-456",       // Single file
  "attachments": ["uuid-1", "uuid-2"]  // Multiple files (array)
}
```

---

## API Endpoints

### File Upload

```
POST /api/files/upload
Content-Type: multipart/form-data

Parameters:
- file: The file to upload (required)
- entity: Entity name (optional, for association)
- entity_id: Entity record ID (optional)
- field: Field name (optional)

Response:
{
  "id": "uuid",
  "filename": "document.pdf",
  "content_type": "application/pdf",
  "size": 102400,
  "url": "/files/2025/11/28/uuid_document.pdf",
  "thumbnail_url": null
}
```

### File Download

```
GET /api/files/{file_id}
GET /api/files/{file_id}/download  # Force download
GET /api/files/{file_id}/thumbnail # Get thumbnail (images only)
```

### File Delete

```
DELETE /api/files/{file_id}
```

### Entity-Scoped Files

```
GET /api/{entity}/{id}/files/{field}
POST /api/{entity}/{id}/files/{field}
DELETE /api/{entity}/{id}/files/{field}/{file_id}
```

---

## Configuration

### In BackendSpec

```python
class FileStorageConfig(BaseModel):
    """File storage configuration."""

    backend: Literal["local", "s3"] = "local"

    # Local options
    local_path: Path = Path(".dazzle/uploads")
    local_base_url: str = "/files"

    # S3 options
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_endpoint: str | None = None  # For MinIO
    s3_public_url: str | None = None  # CDN URL

    # Limits
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    allowed_types: list[str] | None = None
```

### In dazzle.toml

```toml
[storage]
backend = "local"  # or "s3"

[storage.local]
path = ".dazzle/uploads"
base_url = "/files"

[storage.s3]
bucket = "my-app-files"
region = "us-east-1"
# endpoint = "http://localhost:9000"  # For MinIO
# public_url = "https://cdn.example.com"  # Optional CDN

[storage.limits]
max_file_size = 10485760  # 10MB
allowed_types = ["image/*", "application/pdf"]
```

---

## Rich Text Support

### Markdown Processing

```python
class MarkdownProcessor:
    """Process markdown content with security and image handling."""

    def __init__(
        self,
        storage: StorageBackend,
        allow_images: bool = True,
        allow_html: bool = False,
    ):
        self.storage = storage
        self.allow_images = allow_images
        self.allow_html = allow_html

    def render_html(self, markdown: str) -> str:
        """Render markdown to safe HTML."""
        import markdown as md
        from bleach import clean

        html = md.markdown(
            markdown,
            extensions=["fenced_code", "tables", "nl2br"],
        )

        if not self.allow_html:
            html = clean(
                html,
                tags=["p", "h1", "h2", "h3", "h4", "h5", "h6",
                      "strong", "em", "a", "ul", "ol", "li",
                      "code", "pre", "blockquote", "table",
                      "thead", "tbody", "tr", "th", "td", "img"],
                attributes={"a": ["href"], "img": ["src", "alt"]},
            )

        return html

    async def process_inline_images(
        self,
        markdown: str,
        entity: str | None = None,
        entity_id: str | None = None,
    ) -> str:
        """Process base64 inline images, upload them, and replace with URLs."""
        import re

        pattern = r'!\[(.*?)\]\(data:([^;]+);base64,([^)]+)\)'

        async def replace_match(match):
            alt = match.group(1)
            content_type = match.group(2)
            base64_data = match.group(3)

            # Decode and upload
            import base64
            from io import BytesIO

            data = base64.b64decode(base64_data)
            file = BytesIO(data)

            ext = content_type.split("/")[-1]
            filename = f"inline_{uuid4().hex[:8]}.{ext}"

            metadata = await self.storage.store(
                file, filename, content_type,
                path_prefix=f"richtext/{entity or 'general'}"
            )

            return f"![{alt}]({metadata.url})"

        # Process all matches
        for match in re.finditer(pattern, markdown):
            replacement = await replace_match(match)
            markdown = markdown.replace(match.group(0), replacement)

        return markdown
```

---

## Image Processing

### Thumbnail Generation

```python
from PIL import Image
from io import BytesIO

class ImageProcessor:
    """Process images for thumbnails and optimization."""

    @staticmethod
    async def generate_thumbnail(
        image_data: bytes,
        size: tuple[int, int] = (200, 200),
        format: str = "JPEG",
        quality: int = 85,
    ) -> bytes:
        """Generate a thumbnail from image data."""
        img = Image.open(BytesIO(image_data))

        # Convert to RGB if necessary (for JPEG)
        if format == "JPEG" and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Thumbnail preserves aspect ratio
        img.thumbnail(size, Image.Resampling.LANCZOS)

        output = BytesIO()
        img.save(output, format=format, quality=quality)
        output.seek(0)

        return output.read()

    @staticmethod
    async def optimize_image(
        image_data: bytes,
        max_dimension: int = 2048,
        quality: int = 85,
    ) -> bytes:
        """Optimize image for web delivery."""
        img = Image.open(BytesIO(image_data))

        # Resize if too large
        if max(img.size) > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        # Convert to RGB for JPEG
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        output = BytesIO()
        img.save(output, format="JPEG", quality=quality, optimize=True)
        output.seek(0)

        return output.read()
```

---

## Security Considerations

### File Validation

```python
import magic  # python-magic for MIME detection

class FileValidator:
    """Validate uploaded files."""

    def __init__(
        self,
        max_size: int = 10 * 1024 * 1024,
        allowed_types: list[str] | None = None,
    ):
        self.max_size = max_size
        self.allowed_types = allowed_types

    def validate(self, file: BinaryIO, filename: str) -> tuple[bool, str | None]:
        """Validate a file, return (valid, error_message)."""

        # Check size
        file.seek(0, 2)  # Seek to end
        size = file.tell()
        file.seek(0)  # Reset

        if size > self.max_size:
            return False, f"File exceeds maximum size of {self.max_size} bytes"

        # Check MIME type (by content, not extension!)
        content = file.read(2048)  # Read enough for magic
        file.seek(0)

        detected_type = magic.from_buffer(content, mime=True)

        if self.allowed_types:
            allowed = False
            for pattern in self.allowed_types:
                if pattern.endswith("/*"):
                    # Wildcard match (e.g., "image/*")
                    if detected_type.startswith(pattern[:-1]):
                        allowed = True
                        break
                elif detected_type == pattern:
                    allowed = True
                    break

            if not allowed:
                return False, f"File type '{detected_type}' not allowed"

        # Check for dangerous file types
        dangerous = ["application/x-executable", "application/x-msdos-program"]
        if detected_type in dangerous:
            return False, f"File type '{detected_type}' is not allowed"

        return True, None
```

### Filename Sanitization

```python
import re
from pathlib import Path

def secure_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    # Get just the filename, no path
    filename = Path(filename).name

    # Remove any non-alphanumeric except dots, dashes, underscores
    filename = re.sub(r'[^\w\.\-]', '_', filename)

    # Limit length
    name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
    name = name[:100]

    return f"{name}.{ext}" if ext else name
```

---

## Implementation Plan

### Week 9 Tasks

1. **Extend Field Types** (Day 1)
   - Add FILE, IMAGE, RICHTEXT to ScalarType
   - Add FileFieldConfig and RichTextConfig models
   - Update FieldType to handle new types

2. **Storage Backend** (Day 2-3)
   - Implement StorageBackend protocol
   - Implement LocalStorageBackend
   - Add file metadata table to migrations

3. **File Endpoints** (Day 4-5)
   - Implement upload endpoint
   - Implement download/streaming endpoint
   - Add file validation

### Week 10 Tasks

4. **S3 Backend** (Day 1-2)
   - Implement S3StorageBackend
   - Add presigned URL support
   - Test with MinIO locally

5. **Image Processing** (Day 3)
   - Thumbnail generation
   - Image optimization
   - Lazy thumbnail creation

6. **Rich Text** (Day 4)
   - Markdown processor
   - Inline image handling
   - HTML sanitization

7. **Testing & Integration** (Day 5)
   - 30+ file upload tests
   - Integration with entity CRUD
   - Documentation update

---

## Dependencies

### Required Packages

```toml
[project.optional-dependencies]
files = [
    "python-multipart>=0.0.6",   # FastAPI file uploads
    "python-magic>=0.4.27",       # MIME type detection
    "Pillow>=10.0.0",             # Image processing
    "aioboto3>=12.0.0",           # Async S3 client
    "bleach>=6.0.0",              # HTML sanitization
    "markdown>=3.5.0",            # Markdown processing
]
```

### System Dependencies

```bash
# For python-magic (libmagic)
# macOS:
brew install libmagic

# Ubuntu/Debian:
apt-get install libmagic1

# Alpine:
apk add libmagic
```

---

## Testing Strategy

### Test Categories

1. **Unit Tests** - Storage backends, validators, processors
2. **Integration Tests** - Full upload/download flow
3. **E2E Tests** - File fields in entity CRUD

### Test Fixtures

```python
@pytest.fixture
def sample_image() -> bytes:
    """Create a minimal valid PNG."""
    from PIL import Image
    from io import BytesIO

    img = Image.new('RGB', (100, 100), color='red')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()

@pytest.fixture
def sample_pdf() -> bytes:
    """Create a minimal valid PDF."""
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
```
