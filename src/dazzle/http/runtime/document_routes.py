"""Scope-gated document range proxy (hx-pdf P1, #162).

``GET /_dazzle/documents/{entity}/{entity_id}/{field}/file`` streams a
file-field's bytes gated by the SAME access core the entity's read verb
uses — document access IS entity access (the ratified hx-pdf adaptation
4). ``/download`` adds attachment disposition + an audit event.

Contract (spec §3 proxy mode + §18 security):

- auth is wired as a real FastAPI dependency on BOTH handlers (the
  bulk_routes pattern) — never read off ``request.state``;
- entity resolves to a registered service, else opaque 404;
- the record must be readable under the entity's scope/permit
  (``gated_read`` when a cedar access spec exists; otherwise the plain
  read path, denied to anonymous callers when the app enforces auth —
  matching the REST read posture); denied/missing → opaque 404;
- the record's field value must reference the requested file AND the
  file metadata's (entity_name, entity_id, field_name) triple must match
  the URL — holding a foreign file id never leaks bytes;
- single byte ranges are validated: satisfiable → 206 +
  ``Content-Range``; unsatisfiable → 416; syntactically invalid or
  multipart ranges are ignored per RFC 9110 (whole body, 200);
- ``inline`` disposition is restricted to a viewer-safe content-type
  safelist (PDF + images); anything else serves as ``attachment`` —
  upload-time content types are client-controlled;
- every response carries ``X-Content-Type-Options: nosniff``,
  ``Accept-Ranges: bytes``, ``Cache-Control: private`` and a sanitized
  RFC 6266 ``Content-Disposition``.

The legacy ``/files/{id}`` reads are ID-keyed with NO entity scope —
this route is the scope-correct path for document viewing (the hx-pdf
Hyperpart's ``data-dz-pdf-src`` target).
"""

import logging
import re
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from dazzle.http.runtime.access.gated import (
    RecordNotFound,
    access_context_from,
    gated_read,
)
from dazzle.http.runtime.http_errors import require_found

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

# single-range form only: bytes=a-b | bytes=a- | bytes=-suffix
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")

# Content types safe to render inline from the app origin. Upload-time
# content types are client-controlled; a stored text/html served inline
# would run as origin HTML (nosniff does not stop an honest label).
_INLINE_SAFE = ("application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp")


class _Unsatisfiable:
    """Sentinel: a well-formed but out-of-bounds Range (→ 416)."""


_UNSATISFIABLE = _Unsatisfiable()


def _extract_file_id(raw: Any) -> UUID | None:
    """Pull the file UUID out of a file-field value.

    ``FieldType.FILE`` columns store a URL/path string (rendered
    directly as an href by the cell core) — usually ``/files/{id}/...``
    — but a bare UUID is accepted too.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    m = _UUID_RE.search(text)
    if not m:
        return None
    try:
        return UUID(m.group(0))
    except ValueError:  # pragma: no cover - regex guarantees shape
        return None


def _disposition(kind: str, name: str) -> str:
    """Build a sanitized RFC 6266 Content-Disposition.

    The ``filename=`` value is ASCII-folded (headers are latin-1; a
    non-ASCII name would 500 at the Starlette layer) with injection
    hazards stripped; the original name rides ``filename*`` UTF-8
    encoded (spec §18: filenames are sanitized).
    """
    printable = "".join(c for c in name if c.isprintable())
    ascii_name = (
        printable.encode("ascii", "ignore").decode("ascii").replace('"', "").replace(";", "")
    ).strip()[:255] or "document"
    utf8_star = quote(printable[:255], safe="")
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_star}"


def _parse_range(header: str | None, size: int) -> tuple[int, int] | _Unsatisfiable | None:
    """Return (start, end) inclusive for a satisfiable single range,
    the ``_UNSATISFIABLE`` sentinel for a well-formed but out-of-bounds
    range, or ``None`` when the header is absent/invalid/multipart
    (RFC 9110: ignore and serve the whole body)."""
    if not header:
        return None
    m = _RANGE_RE.match(header.strip())
    if not m:
        return None
    start_s, end_s = m.group(1), m.group(2)
    if start_s == "" and end_s == "":
        return None
    if start_s == "":
        # suffix range: last N bytes (N >= size → whole body, RFC-legal)
        n = int(end_s)
        if n == 0:
            return _UNSATISFIABLE
        start = max(0, size - n)
        return (start, size - 1)
    start = int(start_s)
    if start >= size:
        return _UNSATISFIABLE
    end = int(end_s) if end_s else size - 1
    if end < start:
        return None
    return (start, min(end, size - 1))


async def _no_auth() -> Any:
    """Stand-in dependency when the server wires no auth (test rigs)."""
    return None


def create_document_routes(
    *,
    file_service: Any,
    services: dict[str, Any],
    cedar_access_specs: dict[str, Any] | None,
    fk_graph: Any,
    optional_auth_dep: Any,
    admin_personas: list[str] | None,
    audit_logger: Any = None,
    require_auth_by_default: bool = False,
) -> APIRouter:
    """Build the ``/_dazzle/documents`` router.

    ``services`` is keyed by ENTITY name (the ``services_by_entity()``
    view — same contract as ``create_bulk_routes``).
    ``require_auth_by_default`` mirrors the REST read posture: when the
    app enforces auth, no-spec entities deny anonymous callers (opaque
    404) exactly like their ``/api`` reads would 401.
    """
    router = APIRouter(prefix="/_dazzle/documents")
    specs = cedar_access_specs or {}
    auth_dep = optional_auth_dep if optional_auth_dep is not None else _no_auth

    async def _resolve_bytes(
        entity: str, entity_id: str, field: str, auth_context: Any
    ) -> tuple[bytes, Any]:
        service = require_found(services.get(entity))
        try:
            eid = UUID(entity_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Not found")

        spec = specs.get(entity)
        record: Any = None
        if spec is not None:
            access = access_context_from(
                auth_context=auth_context,
                entity_name=entity,
                cedar_access_spec=spec,
                fk_graph=fk_graph,
                admin_personas=admin_personas,
            )
            try:
                record = await gated_read(service, access, eid)
            except RecordNotFound:
                raise HTTPException(status_code=404, detail="Not found")
        else:
            # No scope rules to evaluate — but the app's auth posture
            # still applies: anonymous callers are denied exactly where
            # the entity's /api read would 401 (opaque 404 here; READ
            # keeps row-existence opaque).
            if require_auth_by_default and not (
                auth_context is not None and getattr(auth_context, "is_authenticated", False)
            ):
                raise HTTPException(status_code=404, detail="Not found")
            record = await service.execute(operation="read", id=eid)
        record = require_found(record)

        raw = record.get(field) if isinstance(record, dict) else getattr(record, field, None)
        file_id = require_found(_extract_file_id(raw))

        metadata = require_found(file_service.get_metadata(file_id))
        # Defense in depth: the file must genuinely belong to this
        # entity/record/field — a readable record + a foreign file URL
        # must not leak the foreign bytes.
        if (
            (metadata.entity_name or "") != entity
            or str(metadata.entity_id or "") != str(eid)
            or (metadata.field_name or "") != field
        ):
            raise HTTPException(status_code=404, detail="Not found")

        try:
            content, _ = await file_service.download(file_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Not found")
        return content, metadata

    def _headers(metadata: Any, kind: str) -> dict[str, str]:
        media_type = str(metadata.content_type or "")
        if kind == "inline" and media_type not in _INLINE_SAFE:
            kind = "attachment"
        return {
            "Content-Disposition": _disposition(  # nosemgrep
                kind, str(metadata.filename or "document")
            ),
            "X-Content-Type-Options": "nosniff",
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=0",
        }

    @router.get("/{entity}/{entity_id}/{field}/file")
    async def document_file(
        entity: str,
        entity_id: str,
        field: str,
        request: Request,
        auth_context: Any = Depends(auth_dep),
    ) -> Response:
        content, metadata = await _resolve_bytes(entity, entity_id, field, auth_context)
        size = len(content)
        rng = _parse_range(request.headers.get("range"), size)
        headers = _headers(metadata, "inline")
        media_type = str(metadata.content_type or "application/octet-stream")
        if isinstance(rng, _Unsatisfiable):
            return Response(
                status_code=416,
                headers={**headers, "Content-Range": f"bytes */{size}"},
            )
        if rng is None:
            return Response(content=content, media_type=media_type, headers=headers)
        start, end = rng
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(
            content=content[start : end + 1],
            status_code=206,
            media_type=media_type,
            headers=headers,
        )

    @router.get("/{entity}/{entity_id}/{field}/download")
    async def document_download(
        entity: str,
        entity_id: str,
        field: str,
        request: Request,
        auth_context: Any = Depends(auth_dep),
    ) -> Response:
        content, metadata = await _resolve_bytes(entity, entity_id, field, auth_context)
        if audit_logger is not None:
            # AuditLogger's real API is log_decision (there is no
            # log_event) — the call shape must fail tests on drift, so
            # only transport failures are tolerated here.
            user = getattr(auth_context, "user", None)
            try:
                await audit_logger.log_decision(
                    operation="document_download",
                    entity_name=entity,
                    entity_id=entity_id,
                    decision="allow",
                    matched_policy=f"field={field} filename={metadata.filename or ''}",
                    policy_effect="allow",
                    user_id=str(getattr(user, "id", "") or "") or None,
                    request_path=str(request.url.path),
                    request_method="GET",
                )
            except (OSError, RuntimeError):  # pragma: no cover - transport only
                logger.warning("document_download audit failed", exc_info=True)
        return Response(
            content=content,
            media_type=str(metadata.content_type or "application/octet-stream"),
            headers=_headers(metadata, "attachment"),
        )

    return router
