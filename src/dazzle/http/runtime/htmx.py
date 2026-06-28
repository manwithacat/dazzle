"""
HTMX-aware response utilities.

Provides helpers for building HTMLResponse objects with HX-* headers
for server-client event coordination (triggers, retarget, reswap, redirect).

This is the canonical location for HTMX presentation logic.  The
``dazzle.http.runtime.htmx_response`` module re-exports from here for
backward compatibility.
"""

from __future__ import annotations  # required: forward reference

import json
from dataclasses import dataclass
from typing import Any

from fastapi.responses import HTMLResponse, JSONResponse


@dataclass(frozen=True, slots=True)
class HtmxDetails:
    """Parsed HTMX request headers -- single source of truth.

    Parses all 8 HX-* request headers sent by htmx:
    https://htmx.org/reference/#request_headers
    """

    is_htmx: bool = False
    is_boosted: bool = False
    current_url: str = ""
    is_history_restore: bool = False
    prompt: str = ""
    target: str = ""
    trigger_id: str = ""
    trigger_name: str = ""

    @classmethod
    def from_request(cls, request: Any) -> HtmxDetails:
        """Construct from a Starlette/FastAPI request."""
        if not hasattr(request, "headers"):
            return cls()
        h = request.headers
        return cls(
            is_htmx=h.get("HX-Request") == "true",
            is_boosted=h.get("HX-Boosted") == "true",
            current_url=h.get("HX-Current-URL", ""),
            is_history_restore=h.get("HX-History-Restore-Request") == "true",
            prompt=h.get("HX-Prompt", ""),
            target=h.get("HX-Target", ""),
            trigger_id=h.get("HX-Trigger", ""),
            trigger_name=h.get("HX-Trigger-Name", ""),
        )

    @property
    def wants_partial(self) -> bool:
        """Boosted navigation that is NOT a history restore -> body-only."""
        return self.is_boosted and not self.is_history_restore

    @property
    def wants_fragment(self) -> bool:
        """Navigation targeting #main-content -> content-only response."""
        return self.is_htmx and self.target == "main-content" and not self.is_history_restore

    @property
    def wants_drawer(self) -> bool:
        """Navigation targeting detail drawer -> content-only response."""
        return self.is_htmx and self.target == "dz-detail-drawer-content"


def htmx_response(
    content: str,
    *,
    status_code: int = 200,
    triggers: dict[str, Any] | list[str] | None = None,
    trigger_after_swap: dict[str, Any] | list[str] | None = None,
    retarget: str | None = None,
    reswap: str | None = None,
    redirect: str | None = None,
) -> HTMLResponse:
    """Create an HTMLResponse with HTMX headers.

    Args:
        content: HTML body content.
        status_code: HTTP status code (default 200).
        triggers: Events to fire on the client via HX-Trigger.
            - list[str]: simple event names (no payload)
            - dict[str, Any]: event names with JSON payloads
        trigger_after_swap: Events fired after the swap completes.
        retarget: CSS selector to override the triggering element's hx-target.
        reswap: Override the triggering element's hx-swap strategy.
        redirect: URL to redirect the client to via HX-Redirect.

    Returns:
        HTMLResponse with appropriate HX-* headers set.
    """
    headers: dict[str, str] = {}

    if triggers:
        headers["HX-Trigger"] = _encode_trigger(triggers)
    if trigger_after_swap:
        headers["HX-Trigger-After-Swap"] = _encode_trigger(trigger_after_swap)
    if retarget:
        headers["HX-Retarget"] = retarget
    if reswap:
        headers["HX-Reswap"] = reswap
    if redirect:
        headers["HX-Redirect"] = redirect

    return HTMLResponse(content=content, status_code=status_code, headers=headers)


def htmx_trigger_headers(
    entity_name: str,
    action: str,
    message: str | None = None,
) -> dict[str, str]:
    """Build HX-Trigger header dict for entity mutation responses.

    Args:
        entity_name: Name of the entity (e.g. "Task").
        action: Mutation action ("created", "updated", "deleted").
        message: Optional toast message. If None, auto-generated.

    Returns:
        Dictionary with "HX-Trigger" key ready to pass to Response headers.
    """
    event_name = f"entity{action.capitalize()}"
    toast_message = message or f"{entity_name} {action} successfully"
    trigger = {
        event_name: {"entity": entity_name},
        "showToast": {"message": toast_message, "type": "success"},
    }
    return {"HX-Trigger": json.dumps(trigger)}


def is_htmx_request(request: Any) -> bool:
    """Check if the incoming request is from HTMX."""
    return HtmxDetails.from_request(request).is_htmx


def is_peek_request(request: Any) -> bool:
    """Whether this is a #1494 row-peek fetch (`peek: expand`).

    The list-row chevron loads an entity's detail *body* into an inline panel
    via ``hx-get="<detail-url>?peek=1"``. Such a request must return the
    content-only body (no app chrome, and crucially no ``dz:titleUpdate``
    trigger — expanding a row must not retitle the page). A direct browser GET
    of the same URL (no ``HX-Request``) is an ordinary full-page detail view.
    """
    if not is_htmx_request(request):
        return False
    params = getattr(request, "query_params", None)
    if params is None:
        return False
    return bool(params.get("peek") == "1")


def htmx_error_response(
    errors: list[str],
    *,
    status_code: int = 422,
) -> HTMLResponse:
    """Create an HTMX-aware validation error response.

    Phase 4 (v0.67.61): inline-rendered with the same CSS classes the
    legacy `fragments/form_errors.html` template emitted, so existing
    styles continue to apply unchanged. Returns the rendered HTML with
    HX-Retarget/#form-errors so HTMX swaps the error into the correct
    container instead of replacing the entire page body.

    Args:
        errors: List of human-readable error messages.
        status_code: HTTP status code (default 422).

    Returns:
        HTMLResponse targeting #form-errors with reswap.
    """
    if errors:
        items_html = "".join(f"<li>{_escape(str(e))}</li>" for e in errors)
        html = (
            '<div class="dz-form-errors" role="alert" aria-live="assertive" data-dazzle-error>'
            '<svg xmlns="http://www.w3.org/2000/svg" class="dz-form-errors-icon" '
            'fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" '
            'aria-hidden="true">'
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 '
            "2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 "
            '0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />'
            "</svg>"
            '<div class="dz-form-errors-body">'
            '<h3 class="dz-form-errors-title">Validation Error</h3>'
            f'<ul class="dz-form-errors-list" role="list">{items_html}</ul>'
            "</div>"
            "</div>"
        )
    else:
        html = ""

    return htmx_response(
        html,
        status_code=status_code,
        retarget="#form-errors",
        reswap="innerHTML",
        triggers={"showToast": {"message": "Please fix the errors below", "type": "error"}},
    )


def _encode_trigger(value: dict[str, Any] | list[str]) -> str:
    """Encode trigger value to HX-Trigger header format."""
    if isinstance(value, list):
        # Simple event names -- join with commas
        if all(isinstance(v, str) for v in value):
            return ", ".join(value)
        return json.dumps(value)
    return json.dumps(value)


def _escape(s: str) -> str:
    """Minimal HTML escape for error messages."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def json_or_htmx_error(
    request: Any,
    errors: list[dict[str, Any]],
    error_type: str = "validation_error",
) -> HTMLResponse | JSONResponse:
    """Return HTMX error response for HTMX requests, JSON for API clients.

    For form-submission contexts (POST/PUT/PATCH), retargets to
    `#form-errors` so the form's error region renders the messages
    in place — the create/edit form pattern.

    For read contexts (GET — sort, filter, list paging), there's
    no form on the page so the form-errors retarget would trigger
    htmx:targetError. Returns a toast-only response (200 with an
    HX-Trigger showToast) so the user sees the error without the
    htmx machinery breaking. Closes #994.

    Args:
        request: The incoming request.
        errors: Pydantic-style error dicts.
        error_type: Error type string for JSON response.

    Returns:
        HTMLResponse with HX-Retarget for form contexts, toast-only
        HTMLResponse for read contexts, JSONResponse for API clients.
    """
    if is_htmx_request(request):
        messages = _errors_to_messages(errors)
        method = (getattr(request, "method", "") or "").upper()
        # Form-context detection: only retarget #form-errors when the
        # request originated from a form input. Pre-fix, any non-GET
        # request 422'd with HX-Retarget #form-errors regardless of
        # whether the page actually had that element. Chaos-monkey
        # clicks on non-form hx-post buttons (bulk actions, toggles,
        # nav buttons) flooded the console with htmx:targetError on
        # pages without forms.
        #
        # `HX-Trigger-Name` is the `name` attribute of the triggering
        # element. Form inputs always have a `name` (it's how form
        # data is keyed); non-form buttons / hx-* triggers usually
        # don't. Fall back to the toast path when the signal is missing.
        headers = getattr(request, "headers", None)
        trigger_name = ""
        if headers is not None:
            trigger_name = headers.get("HX-Trigger-Name") or headers.get("hx-trigger-name") or ""
        is_form_context = bool(trigger_name) and method != "GET"
        if not is_form_context:
            return htmx_toast_error_response(messages)
        return htmx_error_response(messages)
    return JSONResponse(
        status_code=422,
        content={"detail": errors, "type": error_type},
    )


def htmx_toast_error_response(errors: list[str]) -> HTMLResponse:
    """Surface validation errors via toast, no retarget (#994).

    Used when an HTMX request hits a validation snag in a context
    that has no form-errors target on the page (sort, filter, list
    paging). Returning a 422 with an `HX-Retarget: #form-errors`
    triggers ``htmx:targetError`` because the selector doesn't exist
    — the browser console fills with errors and the user sees
    nothing change.

    Returns 200 with an empty body, no retarget, and an HX-Trigger
    that fires the standard ``showToast`` event. The toast component
    is in the global app shell, so it always exists regardless of
    where the request came from.
    """
    message = "; ".join(errors) if errors else "Request was not accepted"
    return htmx_response(
        "",
        status_code=200,
        triggers={"showToast": {"message": message, "type": "error"}},
    )


def _errors_to_messages(errors: list[dict[str, Any]]) -> list[str]:
    """Convert Pydantic error dicts to human-readable messages."""
    messages = []
    for err in errors:
        loc = err.get("loc", [])
        msg = err.get("msg", str(err))
        field = ".".join(str(p) for p in loc if p != "body") if loc else ""
        if field:
            messages.append(f"{field}: {msg}")
        else:
            messages.append(msg)
    return messages
