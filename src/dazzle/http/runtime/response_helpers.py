"""
HTMX OOB swap response helpers.

Provides utilities for appending out-of-band HTML fragments to any
HTMLResponse, enabling server-driven toasts, breadcrumbs, and other
UI updates without client-side logic.
"""

from __future__ import annotations

from html import escape

from starlette.responses import HTMLResponse


def with_toast(
    response: HTMLResponse,
    message: str,
    level: str = "info",
    duration: str = "5s",
) -> HTMLResponse:
    """Append an auto-dismissing toast to an HTMX response via OOB swap.

    The toast is OOB-prepended into the shell's ``#dz-toast`` stack and auto-dismissed by
    the ``dz-toast.js`` bridge (``data-dz-remove-after``) — replacing the
    htmx-2 ``remove-me`` extension, dropped in the htmx 4 migration.

    Args:
        response: The original HTMLResponse to augment.
        message: Toast message text (HTML-escaped automatically).
        level: Toast severity — ``success``, ``error``, ``warning``, ``info``.
            Set on the rendered toast as ``data-dz-toast-level``; the
            ``site-sections.css`` rules tone-tint per level.
        duration: Auto-dismiss delay (e.g., ``"5s"``).
    """
    safe_message = escape(message)
    safe_level = escape(level, quote=True)
    # OOB target = the shell's toast stack (`#dz-toast`, _render_shell) —
    # the wrapper div is consumed by the swap, its children prepended.
    # (Historically targeted `#dz-toast-container`, an id no layout ever
    # rendered, so every toast silently missed — caught in the C3 sweep.)
    toast_html = (
        f'<div hx-swap-oob="afterbegin:#dz-toast">'
        f'<div class="dz-toast" data-dz-toast-level="{safe_level}" data-dz-remove-after="{duration}">'
        f"<span>{safe_message}</span>"
        f"</div>"
        f"</div>"
    )
    return _append_html(response, toast_html)


def with_oob(
    response: HTMLResponse,
    target_id: str,
    html: str,
    swap: str = "innerHTML",
) -> HTMLResponse:
    """Append an OOB swap fragment to an HTMX response.

    Args:
        response: The original HTMLResponse to augment.
        target_id: The ``id`` of the target element.
        html: The HTML content to swap in.
        swap: The swap strategy (``innerHTML``, ``outerHTML``, ``afterbegin``, etc.).
    """
    oob_html = f'<div id="{target_id}" hx-swap-oob="{swap}">{html}</div>'
    return _append_html(response, oob_html)


def _append_html(response: HTMLResponse, fragment: str) -> HTMLResponse:
    """Append HTML fragment to an existing HTMLResponse, preserving headers and status."""
    existing_body = bytes(response.body).decode("utf-8")
    new_body = existing_body + fragment
    new_response = HTMLResponse(
        content=new_body,
        status_code=response.status_code,
        media_type=response.media_type,
    )
    for key, value in response.headers.items():
        if key.lower() != "content-length":
            new_response.headers[key] = value
    return new_response
