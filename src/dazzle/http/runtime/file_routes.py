"""
File upload routes for Dazzle backend runtime.

Provides REST endpoints for file upload, download, and management.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from .file_storage import FileService, FileValidationError

logger = logging.getLogger(__name__)

# Callback type: (entity_name, entity_id, field_name, file_metadata_dict) -> None
UploadCallback = Callable[[str, str, str, dict[str, Any]], Awaitable[None]]

# Content types safe to render inline from the app origin (#1551,
# mirrors the hx-pdf P1 document route). Upload-time content types are
# client-controlled; a stored text/html served inline runs as origin
# HTML — nosniff does not stop an honest label.
INLINE_SAFE_CONTENT_TYPES = (
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
)


def content_disposition(kind: str, name: str) -> str:
    """Build a sanitized RFC 6266 Content-Disposition.

    The ``filename=`` value is ASCII-folded (headers are latin-1; a
    non-ASCII name would 500 at the Starlette layer) with injection
    hazards stripped; the original name rides ``filename*`` UTF-8
    encoded. Promoted from the hx-pdf P1 document route (#162) —
    single source for every file-serving surface.
    """
    from urllib.parse import quote

    printable = "".join(c for c in name if c.isprintable())
    ascii_name = (
        printable.encode("ascii", "ignore").decode("ascii").replace('"', "").replace(";", "")
    ).strip()[:255] or "document"
    utf8_star = quote(printable[:255], safe="")
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_star}"


async def _no_auth() -> Any:
    """Stand-in dependency when the server wires no auth (test rigs)."""
    return None


def _require_posture(deps: "_FileDeps", auth_context: Any) -> None:
    """Deny anonymous callers when the app enforces auth (#1551).

    Parity with the REST posture: exactly where an /api call would
    401, the legacy /files surface does too. Auth-less apps keep
    anonymous access. The entity-SCOPED read path is the hx-pdf P1
    document route; this is only the posture floor for ID-keyed access.
    """
    if deps.require_auth and not (
        auth_context is not None and getattr(auth_context, "is_authenticated", False)
    ):
        raise HTTPException(status_code=401, detail="Authentication required")


# =============================================================================
# Dependencies Container
# =============================================================================


@dataclass
class _FileDeps:
    file_service: FileService
    prefix: str
    require_auth: bool
    auth_dep: Any
    max_upload_size: int
    field_size_overrides: dict[tuple[str, str], int] = field(default_factory=dict)
    on_upload_callbacks: list[UploadCallback] = field(default_factory=list)


# =============================================================================
# Helpers
# =============================================================================


def _effective_max_size(deps: _FileDeps, entity: str | None, field_name: str | None) -> int:
    """Return the upload size limit for this entity/field, or the global default."""
    if entity and field_name:
        override = deps.field_size_overrides.get((entity, field_name))
        if override is not None:
            return override
    return deps.max_upload_size


# =============================================================================
# Module-level handler functions
# =============================================================================


async def _upload_file(
    deps: _FileDeps,
    request: Any,
    file: Any,
    entity: str | None = None,
    entity_id: str | None = None,
    field_name: str | None = None,
) -> dict[str, Any]:
    """Upload a file.

    Returns file metadata including ID and URLs.
    """
    from .image_processor import ThumbnailService

    thumbnail_service = ThumbnailService()

    # Check Content-Length against the effective limit for this entity/field
    limit = _effective_max_size(deps, entity, field_name)
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > limit:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Request body too large. "  # nosemgrep
                        f"Maximum upload size is {limit // (1024 * 1024)}MB."  # nosemgrep
                    ),
                )
        except ValueError:
            pass

    try:
        # Read file content
        content = await file.read()
        from io import BytesIO

        file_obj = BytesIO(content)

        # Upload
        metadata = await deps.file_service.upload(
            file=file_obj,
            filename=file.filename or "unnamed",
            content_type=file.content_type,
            entity_name=entity,
            entity_id=entity_id,
            field_name=field_name,
        )

        # Generate thumbnail for images
        thumbnail_url = None
        if thumbnail_service.should_generate(metadata.content_type):
            try:
                thumbnail_data = thumbnail_service.generate(content)
                from io import BytesIO

                thumb_file = BytesIO(thumbnail_data)

                # Store thumbnail
                thumb_metadata = await deps.file_service.storage.store(
                    thumb_file,
                    f"thumb_{metadata.filename}",  # nosemgrep
                    "image/jpeg",
                    path_prefix="thumbnails",
                )
                thumbnail_url = thumb_metadata.url
            except Exception:
                logger.warning("Thumbnail generation failed", exc_info=True)

        result = {
            "id": str(metadata.id),
            "filename": metadata.filename,
            "content_type": metadata.content_type,
            "size": metadata.size,
            "url": metadata.url,
            "thumbnail_url": thumbnail_url,
            "created_at": metadata.created_at.isoformat(),
        }

        # Fire post-upload callbacks when entity context is provided
        if entity and entity_id and field_name and deps.on_upload_callbacks:
            for cb in deps.on_upload_callbacks:
                try:
                    await cb(entity, entity_id, field_name, result)
                except Exception:
                    logger.warning("Post-upload callback failed", exc_info=True)

        return result

    except FileValidationError as e:
        logger.error("File validation failed: %s", e)
        raise HTTPException(status_code=400, detail="File validation failed")
    except Exception as e:
        logger.error("File upload failed: %s", e)
        raise HTTPException(status_code=500, detail="Upload failed")


async def _get_file_info(deps: _FileDeps, file_id: str) -> dict[str, Any]:
    """Get file metadata."""
    try:
        uuid_id = UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file ID")

    try:
        metadata = deps.file_service.get_metadata(uuid_id)
    except Exception as e:
        logger.error("Failed to read file metadata for %s: %s", file_id, e)
        raise HTTPException(status_code=500, detail="Failed to read file metadata")
    if not metadata:
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "id": str(metadata.id),
        "filename": metadata.filename,
        "content_type": metadata.content_type,
        "size": metadata.size,
        "url": metadata.url,
        "thumbnail_url": metadata.thumbnail_url,
        "entity_name": metadata.entity_name,
        "entity_id": metadata.entity_id,
        "field_name": metadata.field_name,
        "created_at": metadata.created_at.isoformat(),
    }


async def _download_file(deps: _FileDeps, file_id: str) -> Any:
    """Download file content."""
    try:
        uuid_id = UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file ID")

    try:
        content, metadata = await deps.file_service.download(uuid_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")

    return Response(
        content=content,
        media_type=metadata.content_type,
        headers={
            "Content-Disposition": content_disposition(  # nosemgrep
                "attachment", metadata.filename
            ),
            "Content-Length": str(metadata.size),
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _stream_file(deps: _FileDeps, file_id: str) -> Any:
    """Stream file content."""
    try:
        uuid_id = UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file ID")

    try:
        metadata = deps.file_service.get_metadata(uuid_id)
    except Exception as e:
        logger.error("Failed to read file metadata for %s: %s", file_id, e)
        raise HTTPException(status_code=500, detail="Failed to read file metadata")
    if not metadata:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        stream, _ = await deps.file_service.stream(uuid_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        logger.error("Failed to stream file %s: %s", file_id, e)
        raise HTTPException(status_code=500, detail="Failed to stream file")

    kind = "inline" if metadata.content_type in INLINE_SAFE_CONTENT_TYPES else "attachment"
    return StreamingResponse(
        stream,
        media_type=metadata.content_type,
        headers={
            "Content-Disposition": content_disposition(kind, metadata.filename),  # nosemgrep
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _get_thumbnail(
    deps: _FileDeps,
    file_id: str,
    width: int = 200,
    height: int = 200,
) -> Any:
    """Get thumbnail for an image.

    Generates on-the-fly if not cached.
    """
    from .image_processor import ImageProcessor, ThumbnailService

    thumbnail_service = ThumbnailService()

    try:
        uuid_id = UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file ID")

    try:
        content, metadata = await deps.file_service.download(uuid_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")

    if not thumbnail_service.should_generate(metadata.content_type):
        raise HTTPException(
            status_code=400,
            detail="Thumbnails not supported for this file type",
        )

    if not ImageProcessor.is_available():
        raise HTTPException(
            status_code=501,
            detail="Image processing not available (Pillow not installed)",
        )

    try:
        thumbnail = thumbnail_service.generate(content, width, height)
    except Exception as e:
        logger.error("Thumbnail generation failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Thumbnail generation failed",
        )

    return Response(
        content=thumbnail,
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f'inline; filename="thumb_{metadata.filename}"',  # nosemgrep
            "Cache-Control": "public, max-age=86400",
        },
    )


async def _delete_file(deps: _FileDeps, file_id: str) -> dict[str, Any]:
    """Delete a file."""
    try:
        uuid_id = UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file ID")

    try:
        deleted = await deps.file_service.delete(uuid_id)
    except Exception as e:
        logger.error("Failed to delete file %s: %s", file_id, e)
        raise HTTPException(status_code=500, detail="Failed to delete file")
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")

    return {"deleted": True, "id": file_id}


async def _get_entity_files(
    deps: _FileDeps,
    entity: str,
    entity_id: str,
    field_name: str | None = None,
) -> dict[str, Any]:
    """Get all files associated with an entity."""
    try:
        files = deps.file_service.get_entity_files(entity, entity_id, field_name)
    except Exception as e:
        logger.error("Failed to list files for %s/%s: %s", entity, entity_id, e)
        raise HTTPException(status_code=500, detail="Failed to list entity files")

    return {
        "files": [
            {
                "id": str(f.id),
                "filename": f.filename,
                "content_type": f.content_type,
                "size": f.size,
                "url": f.url,
                "thumbnail_url": f.thumbnail_url,
                "field_name": f.field_name,
                "created_at": f.created_at.isoformat(),
            }
            for f in files
        ],
        "count": len(files),
    }


# =============================================================================
# Factory
# =============================================================================


def create_file_routes(
    app: FastAPI,
    file_service: FileService,
    prefix: str = "/files",
    require_auth: bool = False,
    max_upload_size: int = 10 * 1024 * 1024,  # 10MB default
    field_size_overrides: dict[tuple[str, str], int] | None = None,
    on_upload_callbacks: list[UploadCallback] | None = None,
    optional_auth_dep: Any = None,
    require_auth_by_default: bool = False,
) -> None:
    """Add file upload routes to FastAPI app.

    Routes:
        POST /files/upload - Upload a file
        GET /files/{file_id} - Get file info
        GET /files/{file_id}/download - Download file
        GET /files/{file_id}/thumbnail - Get thumbnail
        DELETE /files/{file_id} - Delete file

    Args:
        app: FastAPI application
        file_service: FileService instance
        prefix: URL prefix for routes
        require_auth: Whether to require authentication
    """
    import dazzle.http.runtime.rate_limit as _rl

    auth_dep = optional_auth_dep if optional_auth_dep is not None else _no_auth
    deps = _FileDeps(
        file_service=file_service,
        prefix=prefix,
        require_auth=require_auth or require_auth_by_default,
        auth_dep=auth_dep,
        max_upload_size=max_upload_size,
        field_size_overrides=field_size_overrides or {},
        on_upload_callbacks=list(on_upload_callbacks) if on_upload_callbacks else [],
    )

    # Upload — needs wrapper to wire up FastAPI's File/Query params
    @app.post(f"{prefix}/upload")  # nosemgrep
    @_rl.limits.limiter.limit(_rl.limits.upload_limit)  # type: ignore[misc,untyped-decorator,unused-ignore]
    async def upload_file(
        request: Request,
        file: UploadFile = File(...),  # noqa: B008
        entity: str | None = Query(None, description="Associated entity name"),
        entity_id: str | None = Query(None, description="Associated entity ID"),
        field: str | None = Query(None, description="Field name"),
        auth_context: Any = Depends(auth_dep),  # noqa: B008
    ) -> dict[str, Any]:
        _require_posture(deps, auth_context)
        return await _upload_file(deps, request, file, entity, entity_id, field)

    # File info
    @app.get(f"{prefix}/{{file_id}}")  # nosemgrep
    async def get_file_info(file_id: str, auth_context: Any = Depends(auth_dep)) -> dict[str, Any]:
        _require_posture(deps, auth_context)
        return await _get_file_info(deps, file_id)

    # Download
    @app.get(f"{prefix}/{{file_id}}/download")  # nosemgrep
    async def download_file(file_id: str, auth_context: Any = Depends(auth_dep)) -> Any:
        _require_posture(deps, auth_context)
        return await _download_file(deps, file_id)

    # Stream
    @app.get(f"{prefix}/{{file_id}}/stream")  # nosemgrep
    async def stream_file(file_id: str, auth_context: Any = Depends(auth_dep)) -> Any:
        _require_posture(deps, auth_context)
        return await _stream_file(deps, file_id)

    # Thumbnail — needs wrapper for Query params with constraints
    @app.get(f"{prefix}/{{file_id}}/thumbnail")  # nosemgrep
    async def get_thumbnail(
        file_id: str,
        width: int = Query(200, ge=10, le=1000),
        height: int = Query(200, ge=10, le=1000),
        auth_context: Any = Depends(auth_dep),  # noqa: B008
    ) -> Any:
        _require_posture(deps, auth_context)
        return await _get_thumbnail(deps, file_id, width, height)

    # Delete
    @app.delete(f"{prefix}/{{file_id}}")  # nosemgrep
    async def delete_file(file_id: str, auth_context: Any = Depends(auth_dep)) -> dict[str, Any]:
        _require_posture(deps, auth_context)
        return await _delete_file(deps, file_id)

    # Entity-scoped routes — needs wrapper for Query param
    @app.get(f"{prefix}/entity/{{entity}}/{{entity_id}}")  # nosemgrep
    async def get_entity_files(
        entity: str,
        entity_id: str,
        field: str | None = Query(None),
        auth_context: Any = Depends(auth_dep),  # noqa: B008
    ) -> dict[str, Any]:
        _require_posture(deps, auth_context)
        return await _get_entity_files(deps, entity, entity_id, field)


def create_static_file_routes(
    app: FastAPI,
    base_path: str = ".dazzle/uploads",
    url_prefix: str = "/files",
    optional_auth_dep: Any = None,
    require_auth_by_default: bool = False,
) -> None:
    """Serve uploaded files by storage path, under the app's auth posture.

    Replaces the anonymous ``StaticFiles`` mount (#1551): every stored
    byte was readable by path in apps whose ``/api`` reads would 401,
    and a stored ``text/html`` upload served inline as origin HTML.
    The handler denies anonymous callers when the app enforces auth,
    refuses paths outside the uploads root, and restricts inline
    rendering to the viewer-safe safelist (everything else downloads
    as an attachment). ``FileResponse`` keeps Range support.

    Args:
        app: FastAPI application
        base_path: Base path for uploaded files
        url_prefix: URL prefix for file access
        optional_auth_dep: The app's optional-auth dependency
        require_auth_by_default: The app's auth posture
    """
    import mimetypes
    from pathlib import Path

    root = Path(base_path)
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    auth_dep = optional_auth_dep if optional_auth_dep is not None else _no_auth
    posture = _FileDeps(
        file_service=None,  # type: ignore[arg-type]  # posture check only
        prefix=url_prefix,
        require_auth=require_auth_by_default,
        auth_dep=auth_dep,
        max_upload_size=0,
    )

    @app.get(url_prefix + "/{file_path:path}", name="files")  # nosemgrep
    async def serve_stored_file(
        file_path: str, auth_context: Any = Depends(auth_dep)
    ) -> FileResponse:
        _require_posture(posture, auth_context)
        candidate = (resolved_root / file_path).resolve()
        if not candidate.is_relative_to(resolved_root) or not candidate.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        kind = "inline" if media_type in INLINE_SAFE_CONTENT_TYPES else "attachment"
        return FileResponse(
            candidate,
            media_type=media_type,
            headers={
                "Content-Disposition": content_disposition(kind, candidate.name),  # nosemgrep
                "X-Content-Type-Options": "nosniff",
            },
        )
