"""Tests for per-field file upload size limits (#436)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app(
    max_upload_size: int = 10 * 1024 * 1024,
    field_size_overrides: dict[tuple[str, str], int] | None = None,
) -> tuple[FastAPI, MagicMock]:
    """Create a minimal app with file routes for testing."""
    app = FastAPI()
    file_service = MagicMock()

    # Mock the upload method to return metadata
    metadata = MagicMock()
    metadata.id = "test-id"
    metadata.filename = "test.pdf"
    metadata.content_type = "application/pdf"
    metadata.size = 100
    metadata.url = "/files/test-id"
    metadata.created_at = MagicMock(isoformat=lambda: "2026-01-01T00:00:00")
    file_service.upload = AsyncMock(return_value=metadata)

    from dazzle_back.runtime.file_routes import create_file_routes

    create_file_routes(
        app,
        file_service,
        max_upload_size=max_upload_size,
        field_size_overrides=field_size_overrides,
    )
    return app, file_service


def test_global_limit_rejects_large_upload():
    app, _ = _make_app(max_upload_size=1024)
    client = TestClient(app)
    resp = client.post(
        "/files/upload",
        files={"file": ("test.pdf", b"x" * 100, "application/pdf")},
        headers={"content-length": "2048"},
    )
    assert resp.status_code == 413


def test_global_limit_accepts_small_upload():
    app, svc = _make_app(max_upload_size=1024 * 1024)
    client = TestClient(app)
    resp = client.post(
        "/files/upload",
        files={"file": ("test.pdf", b"x" * 100, "application/pdf")},
        headers={"content-length": "100"},
    )
    assert resp.status_code == 200


def test_field_override_allows_larger_upload():
    """A field with max_size=200MB should accept uploads the global limit would reject."""
    app, svc = _make_app(
        max_upload_size=10 * 1024 * 1024,  # 10MB global
        field_size_overrides={("Document", "raw_file"): 200 * 1024 * 1024},  # 200MB
    )
    client = TestClient(app)
    resp = client.post(
        "/files/upload?entity=Document&field=raw_file",
        files={"file": ("big.pdf", b"x" * 100, "application/pdf")},
        headers={"content-length": str(50 * 1024 * 1024)},  # 50MB
    )
    assert resp.status_code == 200


def test_field_override_still_enforces_its_own_limit():
    """A field with max_size=200MB should still reject uploads > 200MB."""
    app, _ = _make_app(
        max_upload_size=10 * 1024 * 1024,
        field_size_overrides={("Document", "raw_file"): 200 * 1024 * 1024},
    )
    client = TestClient(app)
    resp = client.post(
        "/files/upload?entity=Document&field=raw_file",
        files={"file": ("huge.pdf", b"x" * 100, "application/pdf")},
        headers={"content-length": str(300 * 1024 * 1024)},  # 300MB > 200MB
    )
    assert resp.status_code == 413


def test_no_override_uses_global_limit():
    """When no field override exists, global limit applies."""
    app, _ = _make_app(
        max_upload_size=10 * 1024 * 1024,
        field_size_overrides={("Document", "raw_file"): 200 * 1024 * 1024},
    )
    client = TestClient(app)
    # Upload to a different entity/field — no override
    resp = client.post(
        "/files/upload?entity=Other&field=photo",
        files={"file": ("big.pdf", b"x" * 100, "application/pdf")},
        headers={"content-length": str(50 * 1024 * 1024)},  # 50MB > 10MB global
    )
    assert resp.status_code == 413
