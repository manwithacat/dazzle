"""
File upload routes for DNR Backend.

Provides REST endpoints for file upload, download, and management.
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import FastAPI

from .file_storage import FileService

logger = logging.getLogger(__name__)


def create_file_routes(
    app: FastAPI,
    file_service: FileService,
    prefix: str = "/files",
    require_auth: bool = False,
    max_upload_size: int = 10 * 1024 * 1024,  # 10MB default
) -> None:
    """
    Add file upload routes to FastAPI app.

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
        from fastapi import Depends, File, HTTPException, Query, Request, UploadFile
        from fastapi.responses import Response, StreamingResponse
    except ImportError:
        raise ImportError("FastAPI is required for file routes. Install with: pip install fastapi")

    # Rate limiting
    import dazzle_back.runtime.rate_limit as _rl

    from .file_storage import FileValidationError
    from .image_processor import ImageProcessor, ThumbnailService

    thumbnail_service = ThumbnailService()

    def _check_content_length(request: Request) -> None:
        """Reject requests whose Content-Length exceeds the upload size limit."""
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > max_upload_size:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"Request body too large. "
                            f"Maximum upload size is {max_upload_size // (1024 * 1024)}MB."
                        ),
                    )
            except ValueError:
                pass  # Non-integer Content-Length — let downstream handle it

    @app.post(f"{prefix}/upload", dependencies=[Depends(_check_content_length)])
    @_rl.limiter.limit(_rl.upload_limit)
    async def upload_file(
        request: Request,
        file: UploadFile = File(...),  # noqa: B008
        entity: str | None = Query(None, description="Associated entity name"),
        entity_id: str | None = Query(None, description="Associated entity ID"),
        field: str | None = Query(None, description="Field name"),
    ) -> dict[str, Any]:
        """
        Upload a file.

        Returns file metadata including ID and URLs.
        """
        try:
            # Read file content
            content = await file.read()
            from io import BytesIO

            file_obj = BytesIO(content)

            # Upload
            metadata = await file_service.upload(
                file=file_obj,
                filename=file.filename or "unnamed",
                content_type=file.content_type,
                entity_name=entity,
                entity_id=entity_id,
                field_name=field,
            )

            # Generate thumbnail for images
            thumbnail_url = None
            if thumbnail_service.should_generate(metadata.content_type):
                try:
                    thumbnail_data = thumbnail_service.generate(content)
                    from io import BytesIO

                    thumb_file = BytesIO(thumbnail_data)

                    # Store thumbnail
                    thumb_metadata = await file_service.storage.store(
                        thumb_file,
                        f"thumb_{metadata.filename}",
                        "image/jpeg",
                        path_prefix="thumbnails",
                    )
                    thumbnail_url = thumb_metadata.url

                    # Update metadata with thumbnail
                    # Note: In a full implementation, we'd update the metadata store
                except Exception:
                    logger.warning("Thumbnail generation failed", exc_info=True)

            return {
                "id": str(metadata.id),
                "filename": metadata.filename,
                "content_type": metadata.content_type,
                "size": metadata.size,
                "url": metadata.url,
                "thumbnail_url": thumbnail_url,
                "created_at": metadata.created_at.isoformat(),
            }

        except FileValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    @app.get(f"{prefix}/{{file_id}}")
    async def get_file_info(file_id: str) -> dict[str, Any]:
        """Get file metadata."""
        try:
            uuid_id = UUID(file_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file ID")

        try:
            metadata = file_service.get_metadata(uuid_id)
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

    @app.get(f"{prefix}/{{file_id}}/download")
    async def download_file(file_id: str) -> Response:
        """Download file content."""
        try:
            uuid_id = UUID(file_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file ID")

        try:
            content, metadata = await file_service.download(uuid_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="File not found")

        return Response(
            content=content,
            media_type=metadata.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{metadata.filename}"',
                "Content-Length": str(metadata.size),
            },
        )

    @app.get(f"{prefix}/{{file_id}}/stream")
    async def stream_file(file_id: str) -> StreamingResponse:
        """Stream file content."""
        try:
            uuid_id = UUID(file_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file ID")

        try:
            metadata = file_service.get_metadata(uuid_id)
        except Exception as e:
            logger.error("Failed to read file metadata for %s: %s", file_id, e)
            raise HTTPException(status_code=500, detail="Failed to read file metadata")
        if not metadata:
            raise HTTPException(status_code=404, detail="File not found")

        try:
            stream, _ = await file_service.stream(uuid_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="File not found")
        except Exception as e:
            logger.error("Failed to stream file %s: %s", file_id, e)
            raise HTTPException(status_code=500, detail="Failed to stream file")

        return StreamingResponse(
            stream,
            media_type=metadata.content_type,
            headers={
                "Content-Disposition": f'inline; filename="{metadata.filename}"',
            },
        )

    @app.get(f"{prefix}/{{file_id}}/thumbnail")
    async def get_thumbnail(
        file_id: str,
        width: int = Query(200, ge=10, le=1000),
        height: int = Query(200, ge=10, le=1000),
    ) -> Response:
        """
        Get thumbnail for an image.

        Generates on-the-fly if not cached.
        """
        try:
            uuid_id = UUID(file_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file ID")

        try:
            content, metadata = await file_service.download(uuid_id)
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
            raise HTTPException(
                status_code=500,
                detail=f"Thumbnail generation failed: {e}",
            )

        return Response(
            content=thumbnail,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f'inline; filename="thumb_{metadata.filename}"',
                "Cache-Control": "public, max-age=86400",
            },
        )

    @app.delete(f"{prefix}/{{file_id}}")
    async def delete_file(file_id: str) -> dict[str, Any]:
        """Delete a file."""
        try:
            uuid_id = UUID(file_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file ID")

        try:
            deleted = await file_service.delete(uuid_id)
        except Exception as e:
            logger.error("Failed to delete file %s: %s", file_id, e)
            raise HTTPException(status_code=500, detail="Failed to delete file")
        if not deleted:
            raise HTTPException(status_code=404, detail="File not found")

        return {"deleted": True, "id": file_id}

    # Entity-scoped routes
    @app.get(f"{prefix}/entity/{{entity}}/{{entity_id}}")
    async def get_entity_files(
        entity: str,
        entity_id: str,
        field: str | None = Query(None),
    ) -> dict[str, Any]:
        """Get all files associated with an entity."""
        try:
            files = file_service.get_entity_files(entity, entity_id, field)
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


def create_static_file_routes(
    app: FastAPI,
    base_path: str = ".dazzle/uploads",
    url_prefix: str = "/files",
) -> None:
    """
    Add static file serving for local storage.

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
