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
        body = _error_page(f"Invalid or expired link: {exc}")
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

    body = _signing_page(entity_name=entity.name, record_id=str(record_id), token=token)
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

    document_body = _stub_document_body(entity_name=entity.name, record_id=record_id)
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

    await repo.update(
        record_id,
        {
            "status": "signed",
            "signed_at": _utcnow(),
            "signing_token_hash": token_hash(body.token),
            "signer_ip": _client_ip(request),
            "signer_user_agent": request.headers.get("user-agent", "")[:500],
        },
    )

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


def _invoke_validator(dotted_path: str, *, entity: EntitySpec, row: Any) -> None:
    """Resolve and invoke a project-supplied ``signing_validator``.

    The hook can raise ``SigningError(...)`` to block the signature.

    Security: ``dotted_path`` is project-author DSL set at compile time
    (parsed via the lexer's identifier rule, not from request input).
    The regex guard rejects anything outside the
    ``module.submodule.fn`` shape so an attacker who somehow tampered
    with the spec still cannot reach arbitrary modules.
    """
    if not _VALIDATOR_PATH_RE.match(dotted_path):
        raise SigningError(f"signing_validator {dotted_path!r} is not a valid dotted path")
    module_path, _, fn_name = dotted_path.rpartition(".")
    try:
        # dotted_path is constrained by _VALIDATOR_PATH_RE above and
        # originates from project DSL, never from request input.
        module = importlib.import_module(module_path)  # nosemgrep
        fn: _ValidatorFn = getattr(module, fn_name)
    except (ImportError, AttributeError) as exc:
        raise SigningError(
            f"signing_validator {dotted_path!r} could not be resolved: {exc}"
        ) from exc
    result = fn(entity=entity, row=row)
    if hasattr(result, "__await__"):
        import asyncio

        asyncio.get_event_loop().run_until_complete(result)


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


def _signing_page(*, entity_name: str, record_id: str, token: str) -> str:
    safe_entity = html.escape(entity_name)
    safe_id = html.escape(record_id)
    # Tokens are HMAC-signed base64-url payloads (alnum + `-_=`). The
    # ``quote=True`` flag also escapes the ASCII quote characters so the
    # value is safe in an HTML attribute.
    safe_token = html.escape(token, quote=True)
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>Sign {safe_entity}</title></head>"
        '<body style="font-family: system-ui; max-width: 720px; margin: 2rem auto;">'
        f"<h1>Sign {safe_entity}</h1>"
        f"<p>Document identifier: <code>{safe_id}</code></p>"
        '<div id="signing-island" data-island="signing_pad" '
        f'data-entity="{safe_entity}" data-record="{safe_id}" '
        f'data-token="{safe_token}">'
        "<p>The signing pad will load here when the phase-4 Island JS "
        "is wired in. This page proves the route is mounted and the "
        "token + status transition are working.</p>"
        "</div>"
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
