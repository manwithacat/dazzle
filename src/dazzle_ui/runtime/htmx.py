"""
HTMX-aware response utilities.

Provides helpers for building HTMLResponse objects with HX-* headers
for server-client event coordination (triggers, retarget, reswap, redirect).

This is the canonical location for HTMX presentation logic.  The
``dazzle_back.runtime.htmx_response`` module re-exports from here for
backward compatibility.
"""

from __future__ import annotations

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


def htmx_error_response(
    errors: list[str],
    *,
    status_code: int = 422,
) -> HTMLResponse:
    """Create an HTMX-aware validation error response.

    Renders form_errors.html and returns it with HX-Retarget/#form-errors
    so HTMX swaps the error into the correct container instead of replacing
    the entire page body.

    Args:
        errors: List of human-readable error messages.
        status_code: HTTP status code (default 422).

    Returns:
        HTMLResponse targeting #form-errors with reswap.
    """
    try:
        from dazzle_ui.runtime.template_renderer import render_fragment

        html = render_fragment("fragments/form_errors.html", form_errors=errors)
    except ImportError:
        # Template renderer not available -- fall back to simple HTML
        items = "".join(f"<li>{_escape(e)}</li>" for e in errors)
        html = (
            f'<div class="alert alert-error mb-4">'
            f"<div><h3>Validation Error</h3><ul>{items}</ul></div></div>"
        )

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

    Args:
        request: The incoming request.
        errors: Pydantic-style error dicts.
        error_type: Error type string for JSON response.

    Returns:
        HTMLResponse with HX-Retarget for HTMX, JSONResponse for API.
    """
    if is_htmx_request(request):
        # Convert structured errors to readable messages
        messages = _errors_to_messages(errors)
        return htmx_error_response(messages)
    return JSONResponse(
        status_code=422,
        content={"detail": errors, "type": error_type},
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
