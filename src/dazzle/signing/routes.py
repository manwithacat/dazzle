"""Auto-mounted signing routes for `signable: true` entities (#1283 phase 3d).

When a Dazzle app declares one or more entities with ``signable: true``,
``dazzle.signing.routes.create_signing_routes`` produces an FastAPI
``APIRouter`` carrying two endpoints:

    GET  /sign/{entity_name}/{record_id}?token=...
        Render the signing page. Validates the HMAC token, looks up
        the entity row, transitions ``status: sent -> viewed`` on first
        access, and returns an HTML page with the signing pad
        placeholder (the browser-side Island JS lands in phase 4).

    POST /api/sign/{entity_name}/{record_id}
        Receive the signature. Validates the HMAC token, runs the
        optional ``signing_validator:`` hook, generates the PDF, applies
        the PKCS#7 + RFC 3161 signature, transitions
        ``status: viewed -> signed``, and returns the signed PDF inline
        (``application/pdf``). File persistence to the
        ``signed_document`` column lands in phase 4 alongside the
        framework's file-storage abstraction.

The router is mounted by ``app_factory`` only when at least one entity
in the project has ``signable: true``. Apps that never touch the
primitive get a clean OpenAPI surface and the heavy crypto deps
(``fpdf2`` / ``pyhanko``) stay un-imported.
"""

from __future__ import annotations

import html
import importlib
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from dazzle.core.ir import EntitySpec
from dazzle.signing.service import PdfBranding, async_sign_pdf, generate_pdf
from dazzle.signing.tokens import (
    InvalidTokenError,
    SigningError,
    token_hash,
    verify_token,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Public router factory
# ---------------------------------------------------------------------


def create_signing_routes(
    entities: list[EntitySpec],
    *,
    repositories: dict[str, Any],
    branding: PdfBranding | None = None,
    file_service: Any | None = None,
    project_root: Path | None = None,
) -> APIRouter | None:
    """Build the auto-mounted signing router.

    Args:
        entities: All entities in the linked AppSpec. Scanned for
            ``signable=True`` — only those entities get reachable
            routes.
        repositories: ``{entity_name: Repository}`` map from the
            runtime. The handlers read + update through these.
        branding: Project-level PDF branding (organisation, footer,
            jurisdiction). Defaults to a minimal ``PdfBranding`` whose
            ``organisation`` is "Dazzle App" — projects will normally
            supply their own via the runtime configuration.
        file_service: Optional :class:`FileService` (or anything with
            an ``upload(file, filename, content_type, entity_name,
            entity_id, field_name)`` async method). When supplied, the
            signed PDF is persisted via this service and the entity
            row's ``signed_document`` field is patched with the
            resulting URL. When ``None`` (file uploads disabled), the
            PDF is still returned inline and the row's
            ``signed_document`` stays null.
        project_root: Optional path to the project root. Used to
            resolve file-based signing templates under
            ``templates/letters/<entity>/default.html.j2``. When
            ``None``, file-based templates are not resolved and the
            stub placeholder is used as fallback.

    Returns:
        ``None`` if no entity has ``signable: true``. Otherwise an
        ``APIRouter`` ready to be ``include_router``-ed.
    """
    signable = {e.name: e for e in entities if getattr(e, "signable", False)}
    if not signable:
        return None

    resolved_branding = branding or PdfBranding(organisation="Dazzle App")

    router = APIRouter(tags=["Signing"])

    @router.get("/sign/{entity_name}/{record_id}", response_class=HTMLResponse)
    async def render_signing_page(
        entity_name: str, record_id: UUID, request: Request
    ) -> HTMLResponse:
        return await _handle_get(
            entity_name=entity_name,
            record_id=record_id,
            request=request,
            signable=signable,
            repositories=repositories,
            project_root=project_root,
        )

    @router.post("/api/sign/{entity_name}/{record_id}")
    async def submit_signature(
        entity_name: str,
        record_id: UUID,
        body: SignSubmission,
        request: Request,
    ) -> Response:
        return await _handle_post(
            entity_name=entity_name,
            record_id=record_id,
            body=body,
            request=request,
            signable=signable,
            repositories=repositories,
            branding=resolved_branding,
            file_service=file_service,
            project_root=project_root,
        )

    return router


# ---------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------


class SignSubmission(BaseModel):
    """POST body for ``/api/sign/{entity}/{id}``.

    ``token`` lives in the body (not the query string) on the POST so
    it isn't logged in webserver access logs alongside the signature.
    """

    token: str
    signatory_name: str | None = None
    signature_png_b64: str | None = None
    decline: bool = False
    decline_reason: str | None = None


# ---------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------


async def _handle_get(
    *,
    entity_name: str,
    record_id: UUID,
    request: Request,
    signable: dict[str, EntitySpec],
    repositories: dict[str, Any],
    project_root: Path | None = None,
) -> HTMLResponse:
    entity = _lookup_signable(entity_name, signable)
    repo = _lookup_repo(entity_name, repositories)

    # All HTML response bodies are produced by helpers that pass every
    # interpolated value through ``html.escape``. The ``nosemgrep``
    # comments below silence the FastAPI XSS rule which fires on any
    # ``HTMLResponse(string)`` call regardless of upstream escaping.
    token = request.query_params.get("token", "")
    if not token:
        body = _error_page("Missing signing token")
        return HTMLResponse(body, status_code=400)  # nosemgrep

    try:
        verified_id, _email = verify_token(token)
    except InvalidTokenError as exc:
        log.info("Signing link validation failed for %s/%s: %s", entity_name, record_id, exc)
        body = _error_page("Invalid or expired link")
        return HTMLResponse(body, status_code=403)  # nosemgrep

    if verified_id != str(record_id):
        body = _error_page("Token does not match record")
        return HTMLResponse(body, status_code=403)  # nosemgrep

    row = await repo.read(record_id)
    if row is None:
        body = _error_page("Document not found")
        return HTMLResponse(body, status_code=404)  # nosemgrep

    status = _row_get(row, "status")
    if status not in ("sent", "viewed"):
        body = _terminal_page(status)
        return HTMLResponse(body, status_code=200)  # nosemgrep

    if status == "sent":
        await repo.update(
            record_id,
            {
                "status": "viewed",
                "viewed_at": _utcnow(),
                "signer_ip": _client_ip(request),
                "signer_user_agent": request.headers.get("user-agent", "")[:500],
            },
        )

    document_body = _resolve_document_body(entity=entity, row=row, project_root=project_root)
    body = _signing_page(
        entity_name=entity.name,
        record_id=str(record_id),
        token=token,
        document_body=document_body,
    )
    return HTMLResponse(body)  # nosemgrep


async def _handle_post(
    *,
    entity_name: str,
    record_id: UUID,
    body: SignSubmission,
    request: Request,
    signable: dict[str, EntitySpec],
    repositories: dict[str, Any],
    branding: PdfBranding,
    file_service: Any | None = None,
    project_root: Path | None = None,
) -> Response:
    entity = _lookup_signable(entity_name, signable)
    repo = _lookup_repo(entity_name, repositories)

    try:
        verified_id, signer_email = verify_token(body.token)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=403, detail=f"Invalid token: {exc}") from exc

    if verified_id != str(record_id):
        raise HTTPException(status_code=403, detail="Token does not match record")

    row = await repo.read(record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")

    status = _row_get(row, "status")
    if status not in ("sent", "viewed"):
        raise HTTPException(
            status_code=409,
            detail=f"Document in terminal status {status!r}; cannot accept signature",
        )

    if body.decline:
        await repo.update(
            record_id,
            {
                "status": "declined",
                "signing_token_hash": token_hash(body.token),
                "signer_ip": _client_ip(request),
                "signer_user_agent": request.headers.get("user-agent", "")[:500],
            },
        )
        return JSONResponse({"status": "declined"})

    if entity.signing_validator:
        try:
            _invoke_validator(entity.signing_validator, entity=entity, row=row)
        except SigningError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    signatory_name = body.signatory_name or signer_email or "Signer"
    signature_png: bytes | None = None
    if body.signature_png_b64:
        import base64

        signature_png = base64.b64decode(body.signature_png_b64)

    try:
        document_body = _resolve_document_body(entity=entity, row=row, project_root=project_root)
    except SigningError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    # SigningError carries an actionable message (missing [signing] extra,
    # unconfigured cert, …). Without this wrapper it escapes as a bare
    # {"detail": "Internal Server Error"} that tells the signer nothing
    # (#1377 — burned two trial persona runs before anyone saw the cause).
    try:
        pdf = generate_pdf(
            document_body,
            signer_name=signatory_name,
            branding=branding,
            signature_png_bytes=signature_png,
        )
        signed_pdf = await async_sign_pdf(
            pdf,
            signer_name=signatory_name,
            signer_email=signer_email,
            branding=branding,
        )
    except SigningError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    patch: dict[str, Any] = {
        "status": "signed",
        "signed_at": _utcnow(),
        "signing_token_hash": token_hash(body.token),
        "signer_ip": _client_ip(request),
        "signer_user_agent": request.headers.get("user-agent", "")[:500],
    }

    if file_service is not None:
        import io as _io

        filename = f"{entity.name}-{record_id}.pdf"
        try:
            metadata = await file_service.upload(
                _io.BytesIO(signed_pdf),
                filename=filename,
                content_type="application/pdf",
                entity_name=entity.name,
                entity_id=str(record_id),
                field_name="signed_document",
                path_prefix=f"signing/{entity.name}",
            )
            # `signed_document` is a `file` field; the framework stores
            # path/URL strings. Use the storage backend's public URL so
            # the document is fetchable through the file-routes
            # download path.
            patch["signed_document"] = metadata.url
        except Exception:
            log.warning(
                "Failed to persist signed PDF for %s/%s — PDF still "
                "returned inline; signed_document field left null",
                entity.name,
                record_id,
                exc_info=True,
            )

    await repo.update(record_id, patch)

    return Response(
        content=signed_pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": (f'attachment; filename="{entity.name}-{record_id}.pdf"')},
    )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _lookup_signable(name: str, signable: dict[str, EntitySpec]) -> EntitySpec:
    entity = signable.get(name)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"No signable entity named {name!r}")
    return entity


def _lookup_repo(name: str, repositories: dict[str, Any]) -> Any:
    repo = repositories.get(name)
    if repo is None:
        raise HTTPException(status_code=500, detail=f"No repository configured for entity {name!r}")
    return repo


def _row_get(row: Any, key: str) -> Any:
    """Read a column from a row that may be a model OR a dict."""
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _utcnow() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    client = request.client
    return (client.host if client else "")[:45]


_ValidatorFn = Callable[..., Any] | Callable[..., Awaitable[Any]]


# Restrict dotted paths to lowercase identifier segments separated by dots.
# `signing_validator` is project-author DSL declared at compile time and
# parsed via the lexer's identifier rule, so by construction it cannot
# carry request-time input. The regex is defence-in-depth and a
# documented trust boundary so static scanners can see the constraint
# explicitly.
_VALIDATOR_PATH_RE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)+$")


def _resolve_dotted_callable(dotted_path: str, *, kind: str) -> Any:
    """Resolve a project-supplied dotted-path callable.

    Used by both ``signing_validator`` and ``signing_template``. The
    regex guard rejects anything outside the ``module.submodule.fn``
    shape so an attacker who somehow tampered with the spec still
    cannot reach arbitrary modules.

    Security: ``dotted_path`` is project-author DSL set at compile time
    (parsed via the lexer's identifier rule, not from request input).
    The regex guard is defence-in-depth and a documented trust
    boundary so static scanners can see the constraint explicitly.
    """
    if not _VALIDATOR_PATH_RE.match(dotted_path):
        raise SigningError(f"{kind} {dotted_path!r} is not a valid dotted path")
    module_path, _, fn_name = dotted_path.rpartition(".")
    try:
        # dotted_path is constrained by _VALIDATOR_PATH_RE above and
        # originates from project DSL, never from request input.
        module = importlib.import_module(module_path)  # nosemgrep
        return getattr(module, fn_name)
    except (ImportError, AttributeError) as exc:
        raise SigningError(f"{kind} {dotted_path!r} could not be resolved: {exc}") from exc


def _invoke_validator(dotted_path: str, *, entity: EntitySpec, row: Any) -> None:
    """Resolve and invoke a project-supplied ``signing_validator``.

    The hook can raise ``SigningError(...)`` to block the signature.
    """
    fn: _ValidatorFn = _resolve_dotted_callable(dotted_path, kind="signing_validator")
    result = fn(entity=entity, row=row)
    if hasattr(result, "__await__"):
        import asyncio

        asyncio.get_event_loop().run_until_complete(result)


def _invoke_template(dotted_path: str, *, entity: EntitySpec, row: Any) -> str:
    """Resolve and invoke a project-supplied ``signing_template``.

    Function must return the document body HTML as a ``str``. The
    framework feeds the result into ``generate_pdf`` for fpdf2 to
    render. Async templates are not supported in phase 6a — the
    rendering happens inside a request handler that's already awaiting
    other work, and adding asyncio.run-from-inside-async ergonomics
    here is bigger than the use case warrants. Sync return only.
    """
    fn = _resolve_dotted_callable(dotted_path, kind="signing_template")
    result = fn(entity=entity, row=row)
    if not isinstance(result, str):
        raise SigningError(
            f"signing_template {dotted_path!r} must return str, got {type(result).__name__}"
        )
    return result


def _resolve_document_body(
    *,
    entity: EntitySpec,
    row: Any,
    project_root: Path | None,
) -> str:
    """Resolve the document body HTML for both GET and POST handlers.

    Priority:
        1. ``entity.signing_template`` — project-supplied Python callable.
        2. ``<project_root>/templates/letters/<entity.name>/default.html.j2``
           rendered by the minimal placeholder substitution renderer.
        3. ``_stub_document_body`` fallback (phase-3d placeholder).

    Raises:
        SigningError: if the signing_template callable is found but
            raises or returns a non-str value. File-based and stub
            paths never raise.
    """
    if entity.signing_template:
        return _invoke_template(entity.signing_template, entity=entity, row=row)

    if project_root is not None:
        from dazzle.signing.template_renderer import (
            find_signing_template,
            render_signing_template_file,
        )

        path = find_signing_template(project_root, entity.name)
        if path is not None:
            log.debug("Rendering signing template %s for %s", path, entity.name)
            return render_signing_template_file(path, row=row, entity=entity)

    record_id_str = str(getattr(row, "id", "") or "")
    try:
        record_uuid = UUID(record_id_str)
    except (ValueError, AttributeError):
        record_uuid = UUID(int=0)
    return _stub_document_body(entity_name=entity.name, record_id=record_uuid)


def _stub_document_body(*, entity_name: str, record_id: UUID) -> str:
    """Placeholder document body for phase 3d.

    Phase 4 will swap this for project-supplied template lookup
    (``templates/letters/<entity>/<type>.html.j2`` or the equivalent
    typed-Fragment template). For now it prints enough identifying
    detail that the signed PDF is auditable.
    """
    safe_entity = html.escape(entity_name)
    safe_id = html.escape(str(record_id))
    return (
        f"<h1>{safe_entity}</h1>"
        f"<p>Document identifier: {safe_id}</p>"
        "<p>This is a placeholder document body. Phase 4 of the "
        "<code>signable: true</code> primitive will resolve the "
        "project-supplied template for this entity type.</p>"
    )


def _signing_page(*, entity_name: str, record_id: str, token: str, document_body: str) -> str:
    import json

    safe_entity = html.escape(entity_name)
    safe_id = html.escape(record_id)
    # The Island reads props from data-island-props; encode as JSON and
    # then HTML-escape so the JSON itself can't break out of the
    # attribute quotes. Tokens are HMAC-signed base64-url payloads
    # (alnum + ``-_=``) so by character class they're attribute-safe,
    # but escaping defends against future token-shape changes.
    props = json.dumps(
        {
            "entity": entity_name,
            "record": record_id,
            "token": token,
            "signatoryName": "Signer",
            "entityName": entity_name,
            "apiBase": "/api/sign",
        }
    )
    safe_props = html.escape(props, quote=True)
    # document_body is rendered HTML from a trusted template path
    # (project author's .html.j2 or signing_template callable).
    # Field interpolations are already HTML-escaped by
    # render_signing_template_file. The <section> wrapper is inert.
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>Sign {safe_entity}</title>"
        '<link rel="stylesheet" href="/static/dist/dazzle.min.css">'
        "</head>"
        '<body style="font-family: system-ui; max-width: 720px; margin: 2rem auto;">'
        f"<h1>Sign {safe_entity}</h1>"
        f"<p>Document identifier: <code>{safe_id}</code></p>"
        '<section class="signing-document">'
        f"{document_body}"
        "</section>"
        "<hr>"
        '<div data-island="signing_pad" '
        'data-island-src="/static/js/islands/signing-pad.js" '
        f'data-island-props="{safe_props}">'
        "<p>Loading signing pad…</p>"
        "</div>"
        '<script src="https://cdn.jsdelivr.net/npm/signature_pad@5/dist/signature_pad.umd.min.js"></script>'
        '<script src="/static/js/dz-islands.js"></script>'
        "</body></html>"
    )


def _error_page(message: str) -> str:
    safe_message = html.escape(message)
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Cannot sign document</title></head>"
        '<body style="font-family: system-ui; max-width: 540px; margin: 2rem auto;">'
        f"<h1>Cannot sign document</h1><p>{safe_message}</p>"
        "</body></html>"
    )


def _terminal_page(status: str) -> str:
    safe_status = html.escape(status or "unknown")
    message = {
        "signed": "This document has already been signed.",
        "declined": "This document was declined.",
        "expired": "The signing link for this document has expired.",
        "superseded": "This document was superseded.",
    }.get(status, f"Document is in status {safe_status!r}; cannot accept a signature.")
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Document unavailable</title></head>"
        '<body style="font-family: system-ui; max-width: 540px; margin: 2rem auto;">'
        f"<h1>{safe_status.title()}</h1><p>{message}</p>"
        "</body></html>"
    )
