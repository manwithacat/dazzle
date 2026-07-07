"""Tests for StorageBackend.read_range + FileService.read_range (#1551)."""

import io
from unittest.mock import MagicMock

import pytest

from dazzle.http.runtime.file_storage import (
    FileService,
    FileValidator,
    LocalStorageBackend,
)


async def _collect(aiter):
    out = b""
    async for chunk in aiter:
        out += chunk
    return out


@pytest.mark.asyncio
async def test_local_read_range_exact_window(tmp_path):
    backend = LocalStorageBackend(tmp_path, "/files")
    key = "sub/f.bin"
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "f.bin").write_bytes(bytes(range(256)) * 4)  # 1024 bytes

    assert await _collect(backend.read_range(key, 0, 9)) == bytes(range(10))
    assert await _collect(backend.read_range(key, 100, None)) == (bytes(range(256)) * 4)[100:]
    # suffix-style (caller resolves start; backend takes absolute offsets)
    assert await _collect(backend.read_range(key, 1020, 1023)) == bytes([252, 253, 254, 255])


@pytest.mark.asyncio
async def test_local_read_range_missing_file_raises(tmp_path):
    backend = LocalStorageBackend(tmp_path, "/files")
    with pytest.raises(FileNotFoundError):
        await _collect(backend.read_range("nope.bin", 0, None))


@pytest.mark.asyncio
async def test_file_service_read_range_size_drift_fails_loud(tmp_path):
    """Size drift (disk != metadata) must raise RuntimeError, not stream a lie."""
    # Real backend against tmp_path
    backend = LocalStorageBackend(tmp_path, "/files")

    # Store a real file through the backend to get real metadata (storage_key, etc.)
    content = b"hello world" * 100
    metadata = await backend.store(
        io.BytesIO(content),
        "test.bin",
        "application/octet-stream",
    )

    # Stub the metadata store — no real PostgreSQL needed for this test
    mock_store = MagicMock()
    mock_store.get.return_value = metadata

    service = FileService(
        storage=backend,
        metadata_store=mock_store,
        validator=FileValidator(),
    )

    # Truncate the on-disk file behind the service's back
    disk_path = tmp_path / metadata.storage_key
    disk_path.write_bytes(b"truncated")

    # read_range must refuse with RuntimeError, not stream a wrong Content-Length
    with pytest.raises(RuntimeError, match="size drift"):
        await service.read_range(metadata.id, 0, None)
