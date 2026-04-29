"""Auto-generated storage proxy routes (#942 cycle 1a).

When a project declares one or more ``[storage.<name>]`` blocks, the
framework registers a ``GET /api/storage/{storage_name}/proxy`` route
per storage. The route streams the object's bytes through the server
under cookie auth — the s3_key never leaves the server, no presigned
download URL is exposed to the browser. Same security model as the
``upload-ticket`` mint route from cycle 3 of #932, but for the read
path.

The shared+private fan-in case from #941 works naturally: a field
declared ``storage=cohort_pdfs|starter_packs`` produces two proxy
routes (one per storage), and the frontend constructs the right URL
based on which prefix the s3_key matches. The framework doesn't need
to encode that decision per-field.

## Security model

- Cookie-auth via the standard ``require_auth()`` decorator. No
  unauthenticated reads.
- Prefix sandbox: the supplied ``key`` query parameter must match
  the regex derived from ``provider.prefix_template`` with
  ``{user_id}`` bound to ``current_user`` (same pattern as the
  finalize verifier in ``verify.py``). Stops cross-user key claims.
  When the template carries no ``{user_id}`` placeholder (shared
  assets like starter packs), the sandbox accepts any key under the
  literal prefix — that's the intentional shape, the bucket is
  public-read at the application layer.
- Object existence: ``provider.head_object(key)`` returns None →
  404. Stops authenticated probing of arbitrary keys.

## Out of scope for cycle 1a

- Range request support (``Range: bytes=...``) — current handler
  buffers the full body. Fine for ≤200MB objects; a future
  ``stream_object`` provider method can add range support when
  multi-gigabyte assets surface.
- Per-entity routes that auto-resolve s3_key from a row id — that
  shape couples the proxy to the service layer. Project frontends
  already render the s3_key as part of the entity's detail surface,
  so they can construct the proxy URL directly.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

# Module-scope FastAPI imports: route handlers built by closure
# factories below need ``Request`` resolvable at function-signature
# inspection time. Importing inside the factory body hides the
# annotation from FastAPI and the framework treats ``request:
# Request`` as a query parameter — same lesson as ``routes.py``
# (cycle 3 of #932). Don't move these inside the factory.
from fastapi import HTTPException, Request, Response

from dazzle_back.runtime.auth import current_user_id

if TYPE_CHECKING:
    from fastapi import FastAPI

    from dazzle.core.ir import AppSpec

    from .registry import StorageRegistry


log = logging.getLogger("dazzle.storage.proxy")


def _expected_prefix_pattern(prefix_template: str, user_id: str) -> re.Pattern[str]:
    """Same prefix-sandbox pattern builder as
    ``verify._expected_prefix_pattern`` — duplicated here to keep the
    two surfaces (write-side verify, read-side proxy) decoupled. If a
    third surface needs the same regex, lift this into a shared
    helper."""
    pattern = re.escape(prefix_template)
    pattern = pattern.replace(re.escape("{user_id}"), re.escape(user_id))
    pattern = re.sub(r"\\\{[a-zA-Z_]+\\\}", "[^/]+", pattern)
    return re.compile("^" + pattern)


def _build_proxy_handler(*, storage_name: str, registry: StorageRegistry) -> Any:
    """Build a per-storage proxy handler closure. ``Request`` /
    ``Response`` / ``HTTPException`` and ``current_user_id`` are
    imported at module scope so FastAPI's signature introspection
    resolves the ``request: Request`` annotation correctly."""

    async def handler(request: Request) -> Response:
        user_id = current_user_id(request)
        if user_id is None:
            raise HTTPException(status_code=401, detail="unauthorised")

        key = request.query_params.get("key")
        if not key or not isinstance(key, str):
            raise HTTPException(
                status_code=400,
                detail={"error": "missing_key", "reason": "?key=<s3_key> required"},
            )

        try:
            provider = registry.get(storage_name)
        except KeyError:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "storage_unconfigured",
                    "storage": storage_name,
                },
            ) from None

        prefix_template = getattr(provider, "prefix_template", None)
        if prefix_template:
            sandbox = _expected_prefix_pattern(prefix_template, str(user_id))
            if not sandbox.match(key):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "outside_sandbox",
                        "reason": (
                            "key falls outside the caller's prefix — "
                            "did the request reuse another user's key?"
                        ),
                    },
                )

        meta = provider.head_object(key)
        if meta is None:
            raise HTTPException(status_code=404, detail={"error": "object_not_found"})

        try:
            body = provider.get_object(key)
        except Exception as exc:  # noqa: BLE001 — provider may raise anything
            log.warning("proxy_get_object_failed storage=%s key=%s err=%s", storage_name, key, exc)
            raise HTTPException(
                status_code=503,
                detail={"error": "storage_read_failed", "reason": str(exc)},
            ) from exc
        if body is None:
            # head said yes, get said no — race or inconsistency. Map
            # to 404 since the read couldn't complete.
            raise HTTPException(status_code=404, detail={"error": "object_not_found"})

        # Inline disposition keeps the file viewable in the browser
        # (PDF, image) rather than triggering a download; projects
        # that want a download can override the Content-Disposition
        # in front of this route.
        return Response(
            content=body,
            media_type=meta.content_type or "application/octet-stream",
            headers={"Content-Disposition": "inline"},
        )

    return handler


def register_storage_proxy_routes(
    *,
    app: FastAPI,
    appspec: AppSpec,
    registry: StorageRegistry,
) -> list[str]:
    """Register one ``GET /api/storage/{storage_name}/proxy`` route per
    storage that is referenced by at least one ``file storage=...``
    field in the AppSpec.

    Storages declared in dazzle.toml but not referenced from any
    field don't get a proxy route — there's nothing to read through
    them. This mirrors the upload-ticket route registration logic in
    ``routes.py`` (cycle 3 of #932).

    Returns the list of registered route paths for logging /
    diagnostics.
    """
    referenced: set[str] = set()
    for entity in appspec.domain.entities:
        for field in entity.fields:
            for storage_name in getattr(field, "storage", ()) or ():
                referenced.add(storage_name)

    registered: list[str] = []
    for storage_name in sorted(referenced):
        path = f"/api/storage/{storage_name}/proxy"
        handler = _build_proxy_handler(storage_name=storage_name, registry=registry)
        app.get(path, tags=["Storage"])(handler)
        registered.append(path)
    return registered
