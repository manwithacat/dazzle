"""Tests for post-upload event hooks (#437)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle_back.runtime.event_bus import EntityEventBus, EntityEventType


def _make_app_with_callbacks(
    callbacks: list | None = None,
) -> tuple[FastAPI, MagicMock]:
    """Create a minimal app with file routes and upload callbacks."""
    app = FastAPI()
    file_service = MagicMock()

    metadata = MagicMock()
    metadata.id = "file-001"
    metadata.filename = "test.pdf"
    metadata.content_type = "application/pdf"
    metadata.size = 100
    metadata.url = "/files/file-001"
    metadata.created_at = MagicMock(isoformat=lambda: "2026-01-01T00:00:00")
    file_service.upload = AsyncMock(return_value=metadata)

    from dazzle_back.runtime.file_routes import create_file_routes

    create_file_routes(
        app,
        file_service,
        on_upload_callbacks=callbacks,
    )
    return app, file_service


def test_callback_fires_with_entity_context():
    cb = AsyncMock()
    app, _ = _make_app_with_callbacks([cb])
    client = TestClient(app)
    resp = client.post(
        "/files/upload?entity=Document&entity_id=doc-1&field=raw_file",
        files={"file": ("test.pdf", b"content", "application/pdf")},
    )
    assert resp.status_code == 200
    cb.assert_called_once()
    args = cb.call_args[0]
    assert args[0] == "Document"
    assert args[1] == "doc-1"
    assert args[2] == "raw_file"
    assert args[3]["filename"] == "test.pdf"


def test_callback_not_fired_without_entity_context():
    cb = AsyncMock()
    app, _ = _make_app_with_callbacks([cb])
    client = TestClient(app)
    resp = client.post(
        "/files/upload",
        files={"file": ("test.pdf", b"content", "application/pdf")},
    )
    assert resp.status_code == 200
    cb.assert_not_called()


def test_callback_not_fired_with_partial_context():
    cb = AsyncMock()
    app, _ = _make_app_with_callbacks([cb])
    client = TestClient(app)
    # entity but no entity_id
    resp = client.post(
        "/files/upload?entity=Document",
        files={"file": ("test.pdf", b"content", "application/pdf")},
    )
    assert resp.status_code == 200
    cb.assert_not_called()


def test_callback_failure_does_not_block_upload():
    cb = AsyncMock(side_effect=RuntimeError("hook failed"))
    app, _ = _make_app_with_callbacks([cb])
    client = TestClient(app)
    resp = client.post(
        "/files/upload?entity=Document&entity_id=doc-1&field=raw_file",
        files={"file": ("test.pdf", b"content", "application/pdf")},
    )
    # Upload succeeds despite callback failure
    assert resp.status_code == 200
    assert resp.json()["filename"] == "test.pdf"


def test_multiple_callbacks_all_fire():
    cb1 = AsyncMock()
    cb2 = AsyncMock()
    app, _ = _make_app_with_callbacks([cb1, cb2])
    client = TestClient(app)
    resp = client.post(
        "/files/upload?entity=Document&entity_id=doc-1&field=raw_file",
        files={"file": ("test.pdf", b"content", "application/pdf")},
    )
    assert resp.status_code == 200
    cb1.assert_called_once()
    cb2.assert_called_once()


@pytest.mark.asyncio
async def test_event_bus_file_uploaded_event():
    bus = EntityEventBus()
    handler = AsyncMock()
    bus.add_handler(handler)

    await bus.emit_file_uploaded("Document", "doc-1", {"field_name": "raw_file"})
    handler.assert_called_once()
    event = handler.call_args[0][0]
    assert event.event_type == EntityEventType.FILE_UPLOADED
    assert event.entity_name == "Document"
    assert event.entity_id == "doc-1"
    assert event.data["field_name"] == "raw_file"


def test_hook_registry_accepts_post_upload():
    from dazzle_back.runtime.hook_registry import VALID_HOOK_POINTS

    assert "entity.post_upload" in VALID_HOOK_POINTS
