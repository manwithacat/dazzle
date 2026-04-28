"""Upload-ticket auto-route generation (#932 cycle 3).

For every entity that has at least one `file storage=<name>` field,
the framework registers a `POST /api/{entity}/upload-ticket` route.
The handler:

1. Authenticates via the cookie session (uses #933's
   `current_user_id` helper — no manual SQL).
2. Generates a UUID `record_id` for the future row.
3. Looks up the storage provider via `StorageRegistry`.
4. Validates the requested `content_type` against the declared
   `content_types` allowlist (when non-empty).
5. Builds the canonical S3 key from `provider.render_prefix` +
   filename.
6. Mints a presigned POST policy via
   `provider.mint_upload_ticket` and returns it.

The finalize step (verify-key + INSERT) is intentionally NOT
auto-generated in cycle 3 — projects can write a 30-line finalize
handler using `current_user_id()` + `registry.head_object()` +
their entity's existing repository. Cycle 4 evaluates whether the
finalize pattern can be auto-generated cleanly enough to ship.
"""

import re
import uuid
from typing import TYPE_CHECKING, Any

# Module-scoped FastAPI imports — the per-route handlers' signatures
# need the real `Request` class visible at decoration time so FastAPI's
# signature introspection treats it as the request object rather than
# a query parameter (closure-scoped imports broke that path).
from fastapi import Request
from fastapi.responses import JSONResponse

from dazzle_back.runtime.auth import current_user_id

if TYPE_CHECKING:
    from .registry import StorageRegistry


# Filenames are echoed in the S3 key for debugging; keep ASCII-safe.
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(filename: str) -> str:
    """Strip path traversal + non-ASCII, cap length. Returns
    ``"upload"`` if the result would be empty."""
    base = filename.strip().split("/")[-1].split("\\")[-1]
    cleaned = _SAFE_FILENAME_RE.sub("_", base)[:120]
    return cleaned or "upload"


def _build_upload_ticket_handler(
    *,
    storage_name: str,
    field_name: str,
    registry: "StorageRegistry",
) -> Any:
    """Factory for the per-entity-field upload-ticket handler.

    Captures `storage_name` + `field_name` + the registry in the
    closure. The route generator binds one of these per entity that
    has at least one `file storage=<name>` field. (When an entity
    has multiple file fields with different storage bindings, a
    `?field=<name>` query param disambiguates — see the multi-field
    path in `register_upload_ticket_routes`.)
    """

    async def handler(request: Request) -> JSONResponse:
        user_id = current_user_id(request)
        if user_id is None:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)

        try:
            body = await request.json()
        except Exception:
            body = {}
        filename = _safe_filename(str(body.get("filename") or "upload"))
        content_type = str(body.get("content_type") or "application/octet-stream")

        try:
            provider = registry.get(storage_name)
        except KeyError:
            return JSONResponse(
                {"error": f"storage {storage_name!r} not configured"},
                status_code=503,
            )
        except Exception as exc:  # missing env var, bad backend, etc.
            return JSONResponse(
                {"error": f"storage {storage_name!r} unavailable: {exc}"},
                status_code=503,
            )

        if provider.content_types and content_type not in provider.content_types:
            return JSONResponse(
                {
                    "error": "content_type not allowed",
                    "field": field_name,
                    "got": content_type,
                    "allowed": provider.content_types,
                },
                status_code=400,
            )

        record_id = str(uuid.uuid4())
        prefix = provider.render_prefix(user_id=user_id, record_id=record_id)
        key = f"{prefix}{filename}"

        try:
            ticket = provider.mint_upload_ticket(key=key, content_type=content_type)
        except Exception as exc:  # boto3 errors, signature failures
            return JSONResponse(
                {"error": f"failed to mint upload ticket: {exc}"},
                status_code=500,
            )

        return JSONResponse(
            {
                "record_id": record_id,
                "field": field_name,
                "storage": storage_name,
                "s3_bucket": provider.bucket,
                "s3_key": ticket.s3_key,
                "max_bytes": provider.max_bytes,
                "expires_in_seconds": ticket.expires_in_seconds,
                "upload": {
                    "url": ticket.url,
                    "fields": ticket.fields,
                },
            }
        )

    return handler


def register_upload_ticket_routes(
    *,
    app: Any,
    appspec: Any,
    registry: "StorageRegistry",
) -> list[str]:
    """Walk `appspec.domain.entities` and register a
    `POST /api/{entity_lower}/upload-ticket` route for every entity
    that has at least one `file storage=<name>` field.

    Multi-field entities: when an entity declares multiple file
    fields each with their own `storage=` binding, the registered
    handler reads `body["field"]` to pick the right binding. Single-
    field entities don't need that — the field name is fixed in the
    closure.

    Returns the list of registered route paths (one per entity) for
    diagnostics + tests.
    """
    registered: list[str] = []
    for entity in appspec.domain.entities:
        storage_fields = [
            f for f in entity.fields if getattr(f, "storage", None) and f.type.kind.value == "file"
        ]
        if not storage_fields:
            continue
        slug = entity.name.lower()
        path = f"/api/{slug}/upload-ticket"
        if len(storage_fields) == 1:
            f = storage_fields[0]
            assert f.storage is not None  # guaranteed by the filter above
            handler = _build_upload_ticket_handler(
                storage_name=f.storage,
                field_name=f.name,
                registry=registry,
            )
        else:
            handler = _build_multi_field_handler(
                fields_by_name={f.name: f.storage for f in storage_fields if f.storage},
                registry=registry,
            )
        app.post(path, tags=["Storage"])(handler)
        registered.append(path)
    return registered


def _build_multi_field_handler(
    *,
    fields_by_name: dict[str, str],
    registry: "StorageRegistry",
) -> Any:
    """Variant handler for entities with multiple `file storage=...`
    fields — reads `body["field"]` to choose which storage binding
    applies. Falls back to the first declared field when `field` is
    omitted (backward-compatible with single-field projects)."""

    async def dispatcher(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        field_name = str(body.get("field") or next(iter(fields_by_name)))
        if field_name not in fields_by_name:
            return JSONResponse(
                {
                    "error": f"unknown field {field_name!r}",
                    "available": sorted(fields_by_name),
                },
                status_code=400,
            )
        storage_name = fields_by_name[field_name]
        # Reuse the single-field handler for the actual logic.
        single = _build_upload_ticket_handler(
            storage_name=storage_name,
            field_name=field_name,
            registry=registry,
        )
        result: JSONResponse = await single(request)
        return result

    return dispatcher
