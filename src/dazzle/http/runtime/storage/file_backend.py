"""A named ``[storage.<name>]`` backend behind the ``FileService`` (#1816).

``FileService`` stores bytes through a ``StorageBackend`` and records each
file in ``dazzle_files``. ``ProviderStorageBackend`` adapts a registry
``StorageProvider`` (S3, R2, MinIO …) to that interface, so bytes the
framework produces itself — signed documents under ``[signing] storage`` —
land in the project's object store instead of the serving process's local
disk, and every metadata-driven read (the signatory's signed-copy link, the
scope-gated ``/_dazzle/documents`` proxy) fetches them back through the
provider.

The file URL a stored object records is the storage's proxy route
(``/api/storage/<name>/proxy?key=…``): bytes go through the server under
cookie auth, no presigned URL is minted. The provider is resolved from the
registry on first use, so declaring the backend costs nothing at boot.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, BinaryIO
from uuid import uuid4

from dazzle.http.runtime.file_storage import (
    FileMetadata,
    StorageBackend,
    sanitize_storage_relpath,
    secure_filename,
    storage_proxy_url,
)

if TYPE_CHECKING:
    from .protocol import StorageProvider
    from .registry import StorageRegistry

#: ``FileMetadata.storage_backend`` value prefix for registry-backed files.
BACKEND_PREFIX = "storage:"


def storage_backend_name(storage_name: str) -> str:
    """The ``storage_backend`` recorded in ``dazzle_files`` for a file kept
    in ``[storage.<storage_name>]``."""
    return f"{BACKEND_PREFIX}{storage_name}"


class ProviderStorageBackend(StorageBackend):
    """``StorageBackend`` over one named registry storage."""

    def __init__(self, registry: StorageRegistry, storage_name: str) -> None:
        self._registry = registry
        self.storage_name = storage_name

    @property
    def name(self) -> str:
        return storage_backend_name(self.storage_name)

    def _provider(self) -> StorageProvider:
        return self._registry.get(self.storage_name)

    async def store(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
        path_prefix: str = "",
    ) -> FileMetadata:
        """Write under the storage's (literal) prefix, mirroring the local
        backend's ``<path_prefix>/<yyyy/mm/dd>/<file_id>_<name>`` layout so
        the file id stays the first UUID in the key."""
        provider = self._provider()
        file_id = uuid4()
        safe_filename = secure_filename(filename)
        date_path = datetime.now().strftime("%Y/%m/%d")
        safe_prefix = sanitize_storage_relpath(path_prefix)
        relative = f"{safe_prefix}/{date_path}" if safe_prefix else date_path
        key = f"{provider.prefix_template}{relative}/{file_id}_{safe_filename}"
        content = file.read()
        await asyncio.to_thread(provider.put_object, key, content, content_type=content_type)
        return FileMetadata(
            id=file_id,
            filename=safe_filename,
            content_type=content_type,
            size=len(content),
            storage_key=key,
            storage_backend=self.name,
            created_at=datetime.now(UTC),
            url=self.get_url(key),
        )

    async def retrieve(self, storage_key: str) -> bytes:
        body = await asyncio.to_thread(self._provider().get_object, storage_key)
        if body is None:
            raise FileNotFoundError(f"File not found: {storage_key}")
        return body

    async def stream(self, storage_key: str) -> AsyncIterator[bytes]:
        # The provider buffers whole objects (same as the proxy route).
        yield await self.retrieve(storage_key)

    async def read_range(
        self, storage_key: str, start: int, end: int | None
    ) -> AsyncIterator[bytes]:
        body = await self.retrieve(storage_key)
        yield body[start:] if end is None else body[start : end + 1]

    async def delete(self, storage_key: str) -> bool:
        return await asyncio.to_thread(self._provider().delete_object, storage_key)

    def get_url(self, storage_key: str) -> str:
        return storage_proxy_url(self.storage_name, storage_key)
