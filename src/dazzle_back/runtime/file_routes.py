"""
File upload routes for DNR Backend.

Provides REST endpoints for file upload, download, and management.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any
from uuid import UUID

from fastapi import FastAPI

from .file_storage import FileService, FileValidationError

logger = logging.getLogger(__name__)

# Callback type: (entity_name, entity_id, field_name, file_metadata_dict) -> None
UploadCallback = Callable[[str, str, str, dict[str, Any]], Awaitable[None]]


# =============================================================================
# Dependencies Container
# =============================================================================


@dataclass
class _FileDeps:
    file_service: FileService
    prefix: str
    require_auth: bool
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
    from fastapi import HTTPException

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
    from fastapi import HTTPException

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
    from fastapi import HTTPException
    from fastapi.responses import Response

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
            "Content-Disposition": f'attachment; filename="{metadata.filename}"',  # nosemgrep
            "Content-Length": str(metadata.size),
        },
    )


async def _stream_file(deps: _FileDeps, file_id: str) -> Any:
    """Stream file content."""
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse

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

    return StreamingResponse(
        stream,
        media_type=metadata.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{metadata.filename}"',  # nosemgrep
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
    from fastapi import HTTPException
    from fastapi.responses import Response

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
    from fastapi import HTTPException

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
    from fastapi import HTTPException

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
    try:
        from fastapi import File, Query, Request, UploadFile
    except ImportError:
        raise ImportError("FastAPI is required for file routes. Install with: pip install fastapi")

    import dazzle_back.runtime.rate_limit as _rl

    deps = _FileDeps(
        file_service=file_service,
        prefix=prefix,
        require_auth=require_auth,
        max_upload_size=max_upload_size,
        field_size_overrides=field_size_overrides or {},
        on_upload_callbacks=list(on_upload_callbacks) if on_upload_callbacks else [],
    )

    # Upload — needs wrapper to wire up FastAPI's File/Query params
    @app.post(f"{prefix}/upload")  # nosemgrep
    @_rl.limiter.limit(_rl.upload_limit)  # type: ignore[misc,untyped-decorator,unused-ignore]
    async def upload_file(
        request: Request,
        file: UploadFile = File(...),  # noqa: B008
        entity: str | None = Query(None, description="Associated entity name"),
        entity_id: str | None = Query(None, description="Associated entity ID"),
        field: str | None = Query(None, description="Field name"),
    ) -> dict[str, Any]:
        return await _upload_file(deps, request, file, entity, entity_id, field)

    # File info
    app.get(f"{prefix}/{{file_id}}")(partial(_get_file_info, deps))  # nosemgrep

    # Download
    app.get(f"{prefix}/{{file_id}}/download")(partial(_download_file, deps))  # nosemgrep

    # Stream
    app.get(f"{prefix}/{{file_id}}/stream")(partial(_stream_file, deps))  # nosemgrep

    # Thumbnail — needs wrapper for Query params with constraints
    @app.get(f"{prefix}/{{file_id}}/thumbnail")  # nosemgrep
    async def get_thumbnail(
        file_id: str,
        width: int = Query(200, ge=10, le=1000),
        height: int = Query(200, ge=10, le=1000),
    ) -> Any:
        return await _get_thumbnail(deps, file_id, width, height)

    # Delete
    app.delete(f"{prefix}/{{file_id}}")(partial(_delete_file, deps))  # nosemgrep

    # Entity-scoped routes — needs wrapper for Query param
    @app.get(f"{prefix}/entity/{{entity}}/{{entity_id}}")  # nosemgrep
    async def get_entity_files(
        entity: str,
        entity_id: str,
        field: str | None = Query(None),
    ) -> dict[str, Any]:
        return await _get_entity_files(deps, entity, entity_id, field)


def create_static_file_routes(
    app: FastAPI,
    base_path: str = ".dazzle/uploads",
    url_prefix: str = "/files",
) -> None:
    """Add static file serving for local storage.

    This serves uploaded files directly from the filesystem.

    Args:
        app: FastAPI application
        base_path: Base path for uploaded files
        url_prefix: URL prefix for file access
    """
    try:
        from fastapi.staticfiles import StaticFiles
    except ImportError:
        raise ImportError("FastAPI is required for static files")

    from pathlib import Path

    path = Path(base_path)
    path.mkdir(parents=True, exist_ok=True)

    app.mount(url_prefix, StaticFiles(directory=str(path)), name="files")
