"""Triple-verification helper for file-field writes (#1551 Task 4).

``verify_file_triple`` raises ``ValueError`` when a file reference's
stored metadata triple (entity_name / entity_id / field_name) does not
match the owning (entity, record_id, field) the caller is writing to.

The pending-file case (all three metadata fields empty) is ALLOWED —
that is the normal first-attach path.
"""

import pytest

from dazzle.http.runtime.document_routes import verify_file_triple

# A valid-looking file path with a real UUID so _extract_file_id picks it up.
_FILE_PATH = "/files/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/f.pdf"


def test_forged_triple_rejected() -> None:
    class _Meta:
        entity_name = "OtherEntity"
        entity_id = "x"
        field_name = "file"

    class _FS:
        def get_metadata(self, fid):  # type: ignore[no-untyped-def]
            return _Meta()

    with pytest.raises(ValueError):
        verify_file_triple(_FS(), "Attachment", "r1", "file", _FILE_PATH)


def test_matching_triple_ok() -> None:
    class _Meta:
        entity_name = "Attachment"
        entity_id = "r1"
        field_name = "file"

    class _FS:
        def get_metadata(self, fid):  # type: ignore[no-untyped-def]
            return _Meta()

    verify_file_triple(_FS(), "Attachment", "r1", "file", _FILE_PATH)  # no raise


# --- Finding 2: previously untested branches ---


def test_empty_raw_value_is_noop() -> None:
    """None / empty string raw_value → no-op; file_service never called."""

    class _FS:
        def get_metadata(self, fid):  # type: ignore[no-untyped-def]
            raise AssertionError("should not be called")

    verify_file_triple(_FS(), "Attachment", "r1", "file", None)  # no raise
    verify_file_triple(_FS(), "Attachment", "r1", "file", "")  # no raise


def test_unknown_file_raises_value_error() -> None:
    """get_metadata returns None (unknown file) → loud ValueError."""

    class _FS:
        def get_metadata(self, fid):  # type: ignore[no-untyped-def]
            return None

    with pytest.raises(ValueError, match="does not exist"):
        verify_file_triple(_FS(), "Attachment", "r1", "file", _FILE_PATH)


# --- Finding 1: end-to-end gate test through the handler factory ---


@pytest.mark.asyncio
async def test_create_handler_rejects_forged_file_field() -> None:
    """create_create_handler with file_service+file_fields raises HTTP 422 on a
    forged file reference (metadata triple points at a different entity/record).

    This is the end-to-end gate test for Finding 1: proves the handler factory
    wiring actually fires verify_file_triple on a real forged value.
    """
    pytest.importorskip("fastapi")

    from unittest.mock import AsyncMock, MagicMock

    from fastapi import HTTPException
    from pydantic import BaseModel

    from dazzle.http.runtime.route_generator import (
        HandlerConfig,
        RouteSpec,
        create_create_handler,
    )

    # Minimal input schema with one file field
    class _Schema(BaseModel):
        attachment: str | None = None

    class _ForgeMeta:
        entity_name = "OtherEntity"
        entity_id = "other-id"
        field_name = "attachment"

    class _FakeFS:
        def get_metadata(self, fid):  # type: ignore[no-untyped-def]
            return _ForgeMeta()

    service = AsyncMock()
    service.execute = AsyncMock(return_value={"id": "new-id", "attachment": _FILE_PATH})

    handler = create_create_handler(
        RouteSpec(
            handler=HandlerConfig(entity_name="Upload"),
            service=service,
            input_schema=_Schema,
        ),
        file_service=_FakeFS(),
        file_fields=["attachment"],
    )

    request = MagicMock()
    request.headers = {"content-type": "application/json"}
    request.json = AsyncMock(return_value={"attachment": _FILE_PATH})
    request.app.state = MagicMock()

    # _build_noauth_handler wraps a create handler as _noauth_create(request)
    # — only one positional arg (no auth context).
    with pytest.raises(HTTPException) as exc_info:
        await handler(request)
    assert exc_info.value.status_code == 422
