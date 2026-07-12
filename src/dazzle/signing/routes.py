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
from dazzle.http.runtime.byte_serving import AccessDecision, serve_bytes
from dazzle.http.runtime.document_routes import _extract_file_id
from dazzle.http.runtime.http_errors import require_found
from dazzle.signing.service import PdfBranding, async_sign_pdf, generate_pdf
from dazzle.signing.tokens import (
    InvalidTokenError,
    SigningError,
    mint_token,
    token_hash,
    verify_token,
    verify_token_allow_expired,
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
    support_contact: str = "",
    resend_hook: str = "",
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
        support_contact: Optional human contact (email/URL) shown on
            signing error pages — the recovery fallback when no
            ``resend_hook`` is configured (TR-53).
        resend_hook: Optional dotted path to a project callable
            ``fn(*, entity_name, row, email, signing_url)`` that
            delivers a freshly-minted signing link to the ORIGINAL
            recipient through the app's own channel. When set, the
            expired-link page offers a self-serve "Request a new
            signing link" button. The framework never returns the new
            token to the browser — possession of an expired link must
            not extend it.

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
            support_contact=support_contact,
            resend_hook=resend_hook,
        )

    @router.post("/sign/{entity_name}/{record_id}/resend", response_class=HTMLResponse)
    async def request_link_resend(
        entity_name: str, record_id: UUID, request: Request
    ) -> HTMLResponse:
        return await _handle_resend(
            entity_name=entity_name,
            record_id=record_id,
            request=request,
            signable=signable,
            repositories=repositories,
            support_contact=support_contact,
            resend_hook=resend_hook,
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

    @router.get("/sign/{entity_name}/{record_id}/signed-copy")
    async def download_signed_copy(entity_name: str, record_id: UUID, request: Request) -> Response:
        """Durable retrieval of the persisted signed PDF (#1571). Gated by the
        ORIGINAL signing token — only the exact credential that signed (or could
        have signed) this record can fetch the copy."""
        return await _handle_signed_copy(
            entity_name=entity_name,
            record_id=record_id,
            request=request,
            signable=signable,
            repositories=repositories,
            file_service=file_service,
            support_contact=support_contact,
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


# Statuses in which a signing document is terminal — no longer awaiting a
# signature. A signable entity's *active* states are any of its declared
# ``status`` enum values NOT in this set; the default lifecycle collapses to
# {sent, viewed}. Lets custom signing lifecycles (e.g. [pending, signed,
# withdrawn, expired]) use the GET / POST / resend gates and TR-53 recovery
# without hard-coding ("sent", "viewed") (#1385).
_TERMINAL_SIGNING_STATES = frozenset(
    {"signed", "declined", "withdrawn", "superseded", "expired", "completed", "cancelled"}
)


def _active_signing_states(entity: EntitySpec) -> frozenset[str]:
    """Statuses in which *entity* still accepts a signature / can be renewed.

    Derived from the entity's ``status`` enum minus the framework terminal set;
    falls back to the default ``{"sent", "viewed"}`` when the enum can't be read.
    """
    for field in getattr(entity, "fields", None) or []:
        if getattr(field, "name", None) == "status":
            values = getattr(getattr(field, "type", None), "enum_values", None)
            if values:
                active = frozenset(v for v in values if v not in _TERMINAL_SIGNING_STATES)
                if active:
                    return active
            break
    return frozenset({"sent", "viewed"})


async def _handle_get(
    *,
    entity_name: str,
    record_id: UUID,
    request: Request,
    signable: dict[str, EntitySpec],
    repositories: dict[str, Any],
    project_root: Path | None = None,
    support_contact: str = "",
    resend_hook: str = "",
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
        verified_id, signer_email = verify_token(token)
    except InvalidTokenError as exc:
        log.info("Signing link validation failed for %s/%s: %s", entity_name, record_id, exc)
        # Distinguish an *expired-but-genuine* link from a tampered one
        # (TR-53). A valid HMAC over an elapsed expiry means the bearer
        # once held a real link for this record — offer a recovery path
        # instead of a dead end. A bad signature gets the plain error.
        if _is_expired_but_valid(token, record_id):
            body = _expired_recovery_page(
                entity_name=entity_name,
                record_id=str(record_id),
                token=token,
                support_contact=support_contact,
                resend_hook=resend_hook,
            )
            return HTMLResponse(body, status_code=403)  # nosemgrep
        body = _error_page("Invalid or expired link", support_contact=support_contact)
        return HTMLResponse(body, status_code=403)  # nosemgrep

    if verified_id != str(record_id):
        body = _error_page("Token does not match record")
        return HTMLResponse(body, status_code=403)  # nosemgrep

    row = await repo.read(record_id)
    if row is None:
        body = _error_page("Document not found")
        return HTMLResponse(body, status_code=404)  # nosemgrep

    status = _row_get(row, "status")
    if status not in _active_signing_states(entity):
        # #1571 / TR-49: a signatory reopening their ORIGINAL link after signing
        # must not land on the dead-end "Document unavailable" terminal page.
        # Gate on status=signed + the exact credential that signed (token_hash).
        # The durable download CTA is shown when signed_document is present;
        # when the best-effort upload failed at sign time we still show a
        # completion page (not a terminal dead end) so the signatory knows
        # the document is signed and how to recover a copy.
        if status == "signed" and token_hash(token) == _row_get(row, "signing_token_hash"):
            body = _signed_completion_page(
                entity_name=entity.name,
                record_id=str(record_id),
                token=token,
                support_contact=support_contact,
                has_copy=bool(_row_get(row, "signed_document")),
            )
            return HTMLResponse(body, status_code=200)  # nosemgrep
        body = _terminal_page(status)
        return HTMLResponse(body, status_code=200)  # nosemgrep

    # First-view transition (default lifecycle only — a no-op for custom enums
    # without a "sent" state, which is fine: view-tracking is optional).
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
        intended_email=signer_email,
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

    row = require_found(await repo.read(record_id), "Document not found")

    status = _row_get(row, "status")
    if status not in _active_signing_states(entity):
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
            await _invoke_validator(entity.signing_validator, entity=entity, row=row)
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


async def _handle_resend(
    *,
    entity_name: str,
    record_id: UUID,
    request: Request,
    signable: dict[str, EntitySpec],
    repositories: dict[str, Any],
    support_contact: str = "",
    resend_hook: str = "",
) -> HTMLResponse:
    """Request a fresh signing link for an expired one (TR-53).

    Security model: the expired token's *valid HMAC* proves the bearer
    once held a legitimate link for this ``(record, email)`` pair. That
    authorises one thing only — asking the app to deliver a NEW link to
    the original recipient's email through ``resend_hook``. The fresh
    token is never returned to the browser, so possession of an expired
    link can never silently extend it; an attacker who replays a stale
    link only triggers a mail to the genuine signer.
    """
    if not resend_hook:
        # No self-serve channel configured — the GET page wouldn't have
        # shown the form, but guard the endpoint directly too.
        body = _error_page(
            "Self-service link renewal isn't available for this document.",
            support_contact=support_contact,
        )
        return HTMLResponse(body, status_code=404)  # nosemgrep

    form = await request.form()
    token = str(form.get("token", ""))
    try:
        verified_id, email = verify_token_allow_expired(token)
    except InvalidTokenError:
        body = _error_page("Invalid link.", support_contact=support_contact)
        return HTMLResponse(body, status_code=403)  # nosemgrep
    if verified_id != str(record_id):
        body = _error_page("Link does not match document.", support_contact=support_contact)
        return HTMLResponse(body, status_code=403)  # nosemgrep

    # Validate the entity is signable (raises 404 if not); the spec drives the
    # active-state set for the renewal gate (#1385).
    entity = _lookup_signable(entity_name, signable)
    repo = _lookup_repo(entity_name, repositories)
    row = await repo.read(record_id)
    if row is None:
        body = _error_page("Document not found.", support_contact=support_contact)
        return HTMLResponse(body, status_code=404)  # nosemgrep

    status = _row_get(row, "status")
    if status not in _active_signing_states(entity):
        # Already signed/declined/superseded — nothing to renew.
        body = _terminal_page(status)
        return HTMLResponse(body, status_code=200)  # nosemgrep

    # Mint a fresh link and hand it to the project's delivery channel.
    # The new token goes to ``email`` (from the verified token), NEVER
    # into the HTTP response.
    new_token = mint_token(str(record_id), email)
    base = str(request.base_url).rstrip("/")
    signing_url = f"{base}/sign/{entity_name}/{record_id}?token={new_token}"
    try:
        await _invoke_resend_hook(
            resend_hook,
            entity_name=entity_name,
            row=row,
            email=email,
            signing_url=signing_url,
        )
    except Exception as exc:
        # Catch ANYTHING the project hook raises (not just SigningError):
        # a bare exception would otherwise reach FastAPI's handler, whose
        # debug traceback would expose ``signing_url`` — and with it the
        # freshly minted token — in the error output.
        log.warning("resend_hook failed for %s/%s: %s", entity_name, record_id, exc, exc_info=True)
        body = _error_page(
            "We couldn't send a new link right now.",
            support_contact=support_contact,
        )
        return HTMLResponse(body, status_code=500)  # nosemgrep

    body = _resend_confirmation_page(email=email, support_contact=support_contact)
    return HTMLResponse(body, status_code=200)  # nosemgrep


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _is_expired_but_valid(token: str, record_id: UUID) -> bool:
    """True iff *token* has a valid HMAC + matching record but is expired.

    Lets the GET handler offer recovery only for genuine expired links,
    never for tampered/malformed ones (which stay a plain error).
    """
    try:
        verified_id, _email = verify_token_allow_expired(token)
    except InvalidTokenError:
        return False
    return verified_id == str(record_id)


def _lookup_signable(name: str, signable: dict[str, EntitySpec]) -> EntitySpec:
    entity = require_found(signable.get(name), f"No signable entity named {name!r}")
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


async def _invoke_validator(dotted_path: str, *, entity: EntitySpec, row: Any) -> None:
    """Resolve and invoke a project-supplied ``signing_validator``.

    The hook can raise ``SigningError(...)`` to block the signature.
    Sync or async hooks are both supported — an async hook is awaited
    directly on the running request loop (``run_until_complete`` would
    raise ``RuntimeError`` inside the already-running handler loop).
    """
    fn: _ValidatorFn = _resolve_dotted_callable(dotted_path, kind="signing_validator")
    result = fn(entity=entity, row=row)
    if hasattr(result, "__await__"):
        await result


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


async def _invoke_resend_hook(
    dotted_path: str,
    *,
    entity_name: str,
    row: Any,
    email: str,
    signing_url: str,
) -> None:
    """Resolve and invoke a project-supplied ``resend_hook`` (TR-53).

    The hook delivers ``signing_url`` to ``email`` through the app's own
    channel (email, SMS, queue…). Sync or async hooks are both supported
    — an async hook is awaited directly on the running request loop. Its
    return value is ignored — the fresh link must never flow back to the
    browser.
    """
    fn = _resolve_dotted_callable(dotted_path, kind="resend_hook")
    result = fn(entity_name=entity_name, row=row, email=email, signing_url=signing_url)
    if hasattr(result, "__await__"):
        await result


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


def _signing_page(
    *,
    entity_name: str,
    record_id: str,
    token: str,
    document_body: str,
    intended_email: str | None = None,
) -> str:
    import json

    safe_entity = html.escape(entity_name)
    safe_id = html.escape(record_id)
    # Transparency banner (TR-15): a signing link is an unauthenticated
    # bearer credential delivered to the named signatory's email, so the
    # subsystem can't hard-gate on the opener's identity. It CAN, however,
    # show WHO the document is for — a mis-delivered link (wrong inbox) is
    # then visible to the reader before they sign. The token cryptographically
    # binds this email; we surface it verbatim.
    intended_banner = ""
    if intended_email:
        safe_email = html.escape(intended_email)
        intended_banner = (
            '<p class="signing-intended-for" role="note" '
            'style="padding:.75rem 1rem;border:1px solid #d0d7de;border-radius:6px;'
            'background:#f6f8fa;margin:0 0 1rem;">'
            f"This document is intended for <strong>{safe_email}</strong>. "
            "Only sign if this is you — if you received it in error, do not sign."
            "</p>"
        )
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
        f"{intended_banner}"
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


def _support_line(support_contact: str) -> str:
    """An escaped 'contact …' paragraph, or empty when none configured."""
    if not support_contact:
        return ""
    safe = html.escape(support_contact)
    # mailto: only when it parses as a bare email; otherwise show as text
    # (an attacker can't inject markup — value is project config, escaped).
    if "@" in support_contact and "/" not in support_contact and " " not in support_contact:
        link = f'<a href="mailto:{safe}">{safe}</a>'
    else:
        link = safe
    return f"<p>Need help? Contact {link}.</p>"


def _error_page(message: str, *, support_contact: str = "") -> str:
    safe_message = html.escape(message)
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Cannot sign document</title></head>"
        '<body style="font-family: system-ui; max-width: 540px; margin: 2rem auto;">'
        f"<h1>Cannot sign document</h1><p>{safe_message}</p>"
        f"{_support_line(support_contact)}"
        "</body></html>"
    )


def _expired_recovery_page(
    *,
    entity_name: str,
    record_id: str,
    token: str,
    support_contact: str,
    resend_hook: str,
) -> str:
    """The expired-link page with a recovery affordance (TR-53).

    With a ``resend_hook`` it offers a one-click "Request a new signing
    link" form (POSTs the expired token back; the server delivers a fresh
    link to the original recipient). Without one it falls back to the
    support contact, or generic 'contact the sender' guidance — never a
    bare dead end.
    """
    safe_entity = html.escape(entity_name)
    safe_id = html.escape(record_id)
    if resend_hook:
        # The form re-submits the expired token; the server re-verifies
        # its HMAC before delivering a NEW link out-of-band.
        action = f"/sign/{safe_entity}/{safe_id}/resend"
        recovery = (
            f'<form method="post" action="{action}">'
            f'<input type="hidden" name="token" value="{html.escape(token)}">'
            '<button type="submit" '
            'style="font: inherit; padding: 0.6rem 1rem; cursor: pointer;">'
            "Request a new signing link</button>"
            "</form>"
            "<p>We'll email a fresh link to the address this document was sent to.</p>"
        )
    else:
        recovery = _support_line(support_contact) or (
            "<p>Please contact whoever sent you this document to request a new link.</p>"
        )
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Signing link expired</title></head>"
        '<body style="font-family: system-ui; max-width: 540px; margin: 2rem auto;">'
        "<h1>This signing link has expired</h1>"
        "<p>For security, signing links are valid for a limited time.</p>"
        f"{recovery}"
        "</body></html>"
    )


def _resend_confirmation_page(*, email: str, support_contact: str = "") -> str:
    safe_email = html.escape(email)
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>New link sent</title></head>"
        '<body style="font-family: system-ui; max-width: 540px; margin: 2rem auto;">'
        "<h1>New signing link sent</h1>"
        f"<p>We've sent a fresh signing link to {safe_email}. "
        "Please check your inbox (and spam folder).</p>"
        f"{_support_line(support_contact)}"
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


def _signed_completion_page(
    *,
    entity_name: str,
    record_id: str,
    token: str,
    support_contact: str = "",
    has_copy: bool = True,
) -> str:
    """Post-signing landing for the signatory's ORIGINAL link (#1571 / TR-49).

    Prefer a durable signed-copy download when the artifact was persisted at
    sign time. When the best-effort upload failed, still show a completion
    page (never the terminal "Document unavailable" dead end).
    """
    from urllib.parse import quote

    if has_copy:
        copy_href = html.escape(
            f"/sign/{quote(entity_name, safe='')}/{quote(record_id, safe='')}"
            f"/signed-copy?token={quote(token, safe='')}",
            quote=True,
        )
        primary = (
            f'<p><a href="{copy_href}" style="display:inline-block;padding:0.6rem 1.2rem;'
            'background:#111;color:#fff;border-radius:0.4rem;text-decoration:none;">'
            "Download your signed copy</a></p>"
            "<p>Keep this link — it works whenever you need the document again.</p>"
        )
    else:
        primary = (
            "<p>This document has already been signed. A certified copy was produced "
            "at signing time, but a re-download is not available from this link right "
            "now. Contact the sender or support if you need another copy.</p>"
        )
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Document signed</title></head>"
        '<body style="font-family: system-ui; max-width: 540px; margin: 2rem auto;">'
        "<h1>Document signed</h1>"
        "<p>This document has already been signed. A digitally certified copy is "
        "stored securely.</p>"
        f"{primary}"
        f"{_support_line(support_contact)}"
        "</body></html>"
    )


async def _handle_signed_copy(
    *,
    entity_name: str,
    record_id: UUID,
    request: Request,
    signable: dict[str, EntitySpec],
    repositories: dict[str, Any],
    file_service: Any | None,
    support_contact: str = "",
) -> Response:
    """Serve the persisted signed PDF to the bearer of the ORIGINAL signing
    token (#1571). The external signatory has no app session, so this is the
    one place stored signing bytes are served outside an authenticated user
    context — gated by (a) a valid, unexpired token for this record, (b) the
    record being `signed`, and (c) `token_hash(token)` matching the hash
    captured AT sign time, then streamed through the #1551 `serve_bytes` core
    under an explicit `signing_token` decision (ByteAudit'd)."""
    entity = _lookup_signable(entity_name, signable)
    repo = _lookup_repo(entity_name, repositories)

    token = request.query_params.get("token", "")
    if not token:
        return HTMLResponse(_error_page("Missing signing token"), status_code=400)  # nosemgrep

    try:
        verified_id, _email = verify_token(token)
    except InvalidTokenError:
        # Expired-but-genuine links follow the TR-53 posture: expiry never
        # extends; the bearer gets the error/support page, and recovery is the
        # resend flow on the signing link itself.
        body = _error_page("Invalid or expired link", support_contact=support_contact)
        return HTMLResponse(body, status_code=403)  # nosemgrep
    if verified_id != str(record_id):
        return HTMLResponse(
            _error_page("Token does not match record"), status_code=403
        )  # nosemgrep

    row = await repo.read(record_id)
    if row is None:
        return HTMLResponse(_error_page("Document not found"), status_code=404)  # nosemgrep
    if _row_get(row, "status") != "signed":
        return HTMLResponse(
            _error_page("Document is not signed yet"),
            status_code=409,  # nosemgrep
        )
    if token_hash(token) != _row_get(row, "signing_token_hash"):
        return HTMLResponse(
            _error_page("Token does not match the signing credential"),  # nosemgrep
            status_code=403,
        )

    stored = _row_get(row, "signed_document")
    file_id = _extract_file_id(stored)
    if file_service is None or file_id is None:
        # Best-effort upload failed at sign time (the logged-warning branch in
        # _handle_post) — the copy genuinely doesn't exist server-side.
        body = _error_page(
            "Signed copy unavailable — please contact support",
            support_contact=support_contact,
        )
        return HTMLResponse(body, status_code=404)  # nosemgrep

    metadata = await file_service.get_metadata(file_id)
    if metadata is None or (
        (getattr(metadata, "entity_name", None), getattr(metadata, "entity_id", None))
        != (entity.name, str(record_id))
    ):
        # The stored pointer must resolve to a file attached to THIS record —
        # the same entity/record triple check the authenticated file routes
        # apply in _resolve_access.
        body = _error_page(
            "Signed copy unavailable — please contact support",
            support_contact=support_contact,
        )
        return HTMLResponse(body, status_code=404)  # nosemgrep

    decision = AccessDecision(
        user_id=None,
        entity=entity.name,
        record_id=str(record_id),
        field="signed_document",
        matched_policy="signing_token",
        verb="read",
    )
    return await serve_bytes(
        decision=decision,
        file_service=file_service,
        metadata=metadata,
        file_id=file_id,
        range_header=request.headers.get("range"),
        disposition_kind="attachment",
        audit=getattr(getattr(request.app, "state", None), "byte_audit", None),
    )
