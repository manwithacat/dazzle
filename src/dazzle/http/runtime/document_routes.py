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
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

import dazzle.http.runtime.rate_limit as _rl
from dazzle.http.runtime.access.gated import (
    RecordNotFound,
    access_context_from,
    gated_read,
)
from dazzle.http.runtime.byte_serving import AccessDecision, serve_bytes
from dazzle.http.runtime.http_errors import require_found

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


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


async def _no_auth() -> Any:
    """Stand-in dependency when the server wires no auth (test rigs)."""
    return None


def verify_file_triple(
    file_service: Any,
    entity: str,
    record_id: str,
    field: str,
    raw_value: Any,
) -> None:
    """#1551: a file-field write must reference a file whose metadata
    triple matches the owning (entity, id, field). Closes the
    client-chosen-metadata hole — a forged reference is a loud error.

    The empty-triple case (all three metadata fields are ``""``/None)
    is ALLOWED: that is the normal first-attach path for a just-uploaded
    pending file. The check fires only when the stored triple is
    non-empty and conflicts with the caller's target.

    Args:
        file_service: Must implement ``get_metadata(file_id)``
            returning an object with ``entity_name``, ``entity_id``,
            and ``field_name`` attributes (or None when missing).
        entity: The entity name the caller is writing to.
        record_id: The record's ID string (use ``""`` on create before
            the new ID is assigned — pending files have ``entity_id=""``
            so the check still passes).
        field: The field name on the entity.
        raw_value: Raw field value from the request body (URL/path or
            bare UUID). ``None`` / empty string → no-op (field cleared).
    """
    file_id = _extract_file_id(raw_value)
    if file_id is None:
        return  # not a file reference (empty / cleared)
    metadata = file_service.get_metadata(file_id)
    if metadata is None:
        raise ValueError(f"file {file_id} referenced by {entity}.{field} does not exist")
    if (
        (metadata.entity_name or "") not in ("", entity)
        or str(metadata.entity_id or "") not in ("", str(record_id))
        or (metadata.field_name or "") not in ("", field)
    ):
        raise ValueError(
            f"file {file_id} triple {metadata.entity_name}/{metadata.entity_id}/"
            f"{metadata.field_name} does not match {entity}/{record_id}/{field}"
        )


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

    async def _resolve_access(
        entity: str, entity_id: str, field: str, auth_context: Any
    ) -> tuple[Any, UUID, str, str | None]:
        """Enforce scope/permit, verify the file triple, and return
        ``(metadata, file_id, matched_policy, uid)`` for the caller to
        build an ``AccessDecision`` and call ``serve_bytes``.

        ``matched_policy`` is:
        - ``"cedar"``   — a Cedar access spec evaluated and allowed the read;
        - ``"posture"`` — no spec; the app's auth-posture floor was satisfied.
        """
        service = require_found(services.get(entity))
        try:
            eid = UUID(entity_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Not found")

        uid: str | None = str(getattr(getattr(auth_context, "user", None), "id", "") or "") or None

        spec = specs.get(entity)
        record: Any = None
        matched_policy: str
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
            matched_policy = "cedar"
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
            matched_policy = "posture"
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

        return metadata, file_id, matched_policy, uid

    @router.get("/pending/{file_id}")
    async def pending_document(
        file_id: str, request: Request, auth_context: Any = Depends(auth_dep)
    ) -> Response:
        """Uploader-gated pre-attach read (#1551).

        Grants iff the caller is the uploader AND the file is not yet
        attached to any record. All denials → opaque 404 (no information
        leak about which condition failed).
        """
        uid = str(getattr(getattr(auth_context, "user", None), "id", "") or "")
        metadata = file_service.get_metadata(file_id)
        # opaque 404 on: unknown file, unauthenticated, wrong uploader,
        # or file already attached to a record.
        if (
            metadata is None
            or not uid
            or str(metadata.uploaded_by or "") != uid
            or bool(metadata.entity_id)
        ):
            raise HTTPException(status_code=404, detail="Not found")
        decision = AccessDecision(
            user_id=uid,
            entity="(pending)",
            record_id=str(file_id),
            field=str(metadata.field_name or ""),
            matched_policy="uploader",
            verb="pending_read",
        )
        return await serve_bytes(
            decision=decision,
            file_service=file_service,
            metadata=metadata,
            file_id=file_id,
            range_header=request.headers.get("range"),
            disposition_kind="inline",
            audit=getattr(request.app.state, "byte_audit", None),
        )

    @router.get("/{entity}/{entity_id}/{field}/file")
    @_rl.limits.limiter.limit(_rl.limits.download_limit)  # type: ignore[misc,untyped-decorator,unused-ignore]
    async def document_file(
        entity: str,
        entity_id: str,
        field: str,
        request: Request,
        auth_context: Any = Depends(auth_dep),
    ) -> Response:
        metadata, file_id, matched_policy, uid = await _resolve_access(
            entity, entity_id, field, auth_context
        )
        decision = AccessDecision(
            user_id=uid,
            entity=entity,
            record_id=entity_id,
            field=field,
            matched_policy=matched_policy,
            verb="read",
        )
        return await serve_bytes(
            decision=decision,
            file_service=file_service,
            metadata=metadata,
            file_id=file_id,
            range_header=request.headers.get("range"),
            disposition_kind="inline",
            audit=getattr(request.app.state, "byte_audit", None),
        )

    @router.get("/{entity}/{entity_id}/{field}/download")
    @_rl.limits.limiter.limit(_rl.limits.download_limit)  # type: ignore[misc,untyped-decorator,unused-ignore]
    async def document_download(
        entity: str,
        entity_id: str,
        field: str,
        request: Request,
        auth_context: Any = Depends(auth_dep),
    ) -> Response:
        metadata, file_id, matched_policy, uid = await _resolve_access(
            entity, entity_id, field, auth_context
        )
        if audit_logger is not None:
            # AuditLogger's real API is log_decision (there is no
            # log_event) — the call shape must fail tests on drift, so
            # only transport failures are tolerated here.
            try:
                await audit_logger.log_decision(
                    operation="document_download",
                    entity_name=entity,
                    entity_id=entity_id,
                    decision="allow",
                    matched_policy=f"field={field} filename={metadata.filename or ''}",
                    policy_effect="allow",
                    user_id=uid,
                    request_path=str(request.url.path),
                    request_method="GET",
                )
            except (OSError, RuntimeError):  # pragma: no cover - transport only
                logger.warning("document_download audit failed", exc_info=True)
        decision = AccessDecision(
            user_id=uid,
            entity=entity,
            record_id=entity_id,
            field=field,
            matched_policy=matched_policy,
            verb="read",
        )
        return await serve_bytes(
            decision=decision,
            file_service=file_service,
            metadata=metadata,
            file_id=file_id,
            range_header=request.headers.get("range"),
            disposition_kind="attachment",
            audit=getattr(request.app.state, "byte_audit", None),
        )

    return router
