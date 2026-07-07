"""#1551 Task 3 — session-sourced uploaded_by on file metadata.

Pins:
  - FileMetadata.uploaded_by field exists and defaults to None.
  - FileService.upload() accepts uploaded_by and persists it.
  - FileMetadataStore.get() returns uploaded_by (round-trip).
  - The /files/upload route sources uploaded_by from the session (auth_context.user.id),
    never from a client-supplied query param.
"""

import io
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.file_routes import create_file_routes
from dazzle.http.runtime.file_storage import (
    FileService,
    FileValidator,
    LocalStorageBackend,
)

# ---------------------------------------------------------------------------
# Minimal in-memory store — avoids a real PostgreSQL connection in unit tests.
# Tests only the FileService layer; the FileMetadataStore DDL is exercised by
# test_file_storage_pg.py and the integration suite.
# ---------------------------------------------------------------------------


class _InMemoryStore:
    """Dict-backed fake conforming to the FileMetadataStore save/get interface."""

    def __init__(self) -> None:
        self._db: dict = {}

    def save(self, metadata: Any) -> None:
        self._db[str(metadata.id)] = metadata

    def get(self, file_id: Any) -> Any:
        return self._db.get(str(file_id))


def _service(tmp_path: Any) -> FileService:
    storage = LocalStorageBackend(tmp_path, "/files")
    store = _InMemoryStore()
    return FileService(storage, store, FileValidator())


# ---------------------------------------------------------------------------
# Unit tests — FileService.upload / round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_persists_uploaded_by(tmp_path: Any) -> None:
    svc = _service(tmp_path)
    meta = await svc.upload(
        io.BytesIO(b"hello"),
        filename="h.txt",
        content_type="text/plain",
        entity_name="Attachment",
        entity_id="r1",
        field_name="file",
        uploaded_by="user-123",
    )
    assert meta.uploaded_by == "user-123"
    fetched = svc.get_metadata(meta.id)
    assert fetched is not None
    assert fetched.uploaded_by == "user-123"


@pytest.mark.asyncio
async def test_upload_uploaded_by_defaults_to_none(tmp_path: Any) -> None:
    """When uploaded_by is omitted the field is None (not missing)."""
    svc = _service(tmp_path)
    meta = await svc.upload(
        io.BytesIO(b"hi"),
        filename="a.txt",
        content_type="text/plain",
    )
    assert meta.uploaded_by is None


# ---------------------------------------------------------------------------
# Route tests — /files/upload sources uid from session, ignores client param
# ---------------------------------------------------------------------------


def _route_metadata() -> MagicMock:
    md = MagicMock()
    md.id = "22222222-2222-2222-2222-222222222222"
    md.filename = "f.txt"
    md.content_type = "text/plain"
    md.size = 5
    md.url = "/files/x/f.txt"
    md.thumbnail_url = None
    md.uploaded_by = "uid-abc"
    md.created_at = datetime(2026, 1, 1)
    return md


def _auth_dep(user_id: str | None) -> Any:
    async def dep() -> Any:
        if user_id is None:
            return None
        user = SimpleNamespace(id=user_id)
        return SimpleNamespace(is_authenticated=True, user=user)

    return dep


def _make_upload_app(
    *, user_id: str | None, require_auth: bool = False
) -> tuple[FastAPI, MagicMock]:
    app = FastAPI()
    file_service = MagicMock()
    md = _route_metadata()
    file_service.upload = AsyncMock(return_value=md)
    # thumbnail service: no Pillow in CI, disable cleanly
    file_service.storage = MagicMock()
    file_service.storage.store = AsyncMock(return_value=md)

    create_file_routes(
        app,
        file_service,
        require_auth=require_auth,
        optional_auth_dep=_auth_dep(user_id),
    )
    return app, file_service


def test_upload_route_records_session_uid() -> None:
    """Authenticated upload: uploaded_by is sourced from auth_context.user.id."""
    app, file_service = _make_upload_app(user_id="uid-abc", require_auth=True)
    client = TestClient(app)
    resp = client.post(
        "/files/upload",
        files={"file": ("f.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 200
    call_kwargs = file_service.upload.call_args[1]
    assert call_kwargs.get("uploaded_by") == "uid-abc"


def test_upload_route_ignores_client_uploaded_by_param() -> None:
    """?uploaded_by= query param must be silently ignored — never a client input."""
    app, file_service = _make_upload_app(user_id="uid-abc", require_auth=True)
    client = TestClient(app)
    resp = client.post(
        "/files/upload?uploaded_by=attacker-injected",
        files={"file": ("f.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 200
    call_kwargs = file_service.upload.call_args[1]
    # Must use session uid, not the injected param
    assert call_kwargs.get("uploaded_by") == "uid-abc"
    assert call_kwargs.get("uploaded_by") != "attacker-injected"


def test_upload_route_unauthenticated_uploaded_by_is_none() -> None:
    """Auth-less apps: uploaded_by is None (no user in session)."""
    app, file_service = _make_upload_app(user_id=None, require_auth=False)
    client = TestClient(app)
    resp = client.post(
        "/files/upload",
        files={"file": ("f.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 200
    call_kwargs = file_service.upload.call_args[1]
    assert call_kwargs.get("uploaded_by") is None
