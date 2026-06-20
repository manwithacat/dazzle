"""Tests for per-field file upload size limits (#436)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
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

    from dazzle.http.runtime.file_routes import create_file_routes

    create_file_routes(
        app,
        file_service,
        max_upload_size=max_upload_size,
        field_size_overrides=field_size_overrides,
    )
    return app, file_service


@pytest.mark.parametrize(
    ("max_upload_size", "field_size_overrides", "url", "content_length", "expected_status"),
    [
        (1024, None, "/files/upload", "2048", 413),
        (1024 * 1024, None, "/files/upload", "100", 200),
        (
            10 * 1024 * 1024,
            {("Document", "raw_file"): 200 * 1024 * 1024},
            "/files/upload?entity=Document&field=raw_file",
            str(50 * 1024 * 1024),
            200,
        ),
        (
            10 * 1024 * 1024,
            {("Document", "raw_file"): 200 * 1024 * 1024},
            "/files/upload?entity=Document&field=raw_file",
            str(300 * 1024 * 1024),
            413,
        ),
        (
            10 * 1024 * 1024,
            {("Document", "raw_file"): 200 * 1024 * 1024},
            "/files/upload?entity=Other&field=photo",
            str(50 * 1024 * 1024),
            413,
        ),
    ],
    ids=[
        "test_global_limit_rejects_large_upload",
        "test_global_limit_accepts_small_upload",
        "test_field_override_allows_larger_upload",
        "test_field_override_still_enforces_its_own_limit",
        "test_no_override_uses_global_limit",
    ],
)
def test_upload_size_enforcement(
    max_upload_size: int,
    field_size_overrides: dict | None,
    url: str,
    content_length: str,
    expected_status: int,
):
    kwargs: dict = {"max_upload_size": max_upload_size}
    if field_size_overrides is not None:
        kwargs["field_size_overrides"] = field_size_overrides
    app, _ = _make_app(**kwargs)
    client = TestClient(app)
    resp = client.post(
        url,
        files={"file": ("test.pdf", b"x" * 100, "application/pdf")},
        headers={"content-length": content_length},
    )
    assert resp.status_code == expected_status
