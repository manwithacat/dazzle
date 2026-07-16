"""
HTMX OOB swap response helpers.

Provides utilities for appending out-of-band HTML fragments to any
HTMLResponse, enabling server-driven toasts, breadcrumbs, and other
UI updates without client-side logic.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from starlette.responses import HTMLResponse


def with_toast(
    response: HTMLResponse,
    message: str,
    level: str = "info",
    duration: str = "8s",
    *,
    title: str | None = None,
    actions: Sequence[tuple[str, str]] | None = None,
) -> HTMLResponse:
    """Append an auto-dismissing toast to an HTMX response via OOB swap.

    The toast is OOB-prepended into the shell's ``#dz-toast`` stack and
    auto-dismissed by the ``dz-toast.js`` host (``data-dz-remove-after``) —
    hover/focus pauses the timer; optional title + action row are slots.

    Args:
        response: The original HTMLResponse to augment.
        message: Toast body text (HTML-escaped automatically).
        level: Toast severity — ``success``, ``error``, ``warning``, ``info``.
            Set on the rendered toast as ``data-dz-toast-level``.
        duration: Auto-dismiss delay (e.g., ``"8s"``).
        title: Optional heading above the message.
        actions: Optional ``(label, href)`` pairs. Empty href renders a
            dismiss button (``data-dz-toast-dismiss``); non-empty href is a
            link. Labels and hrefs are escaped.
    """
    safe_message = escape(message)
    safe_level = escape(level, quote=True)
    safe_duration = escape(duration, quote=True)
    role = "alert" if level == "error" else "status"

    body_parts: list[str] = ['<div class="dz-toast__body">']
    if title:
        body_parts.append(f'<div class="dz-toast__title">{escape(title)}</div>')
    body_parts.append(f'<div class="dz-toast__message">{safe_message}</div>')

    if actions:
        body_parts.append('<div class="dz-toast__actions">')
        for label, href in actions:
            safe_label = escape(label)
            if href:
                body_parts.append(
                    f'<a class="dz-toast__action" href="{escape(href, quote=True)}">'
                    f"{safe_label}</a>"
                )
            else:
                body_parts.append(
                    f'<button type="button" class="dz-toast__action" '
                    f"data-dz-toast-dismiss>{safe_label}</button>"
                )
        body_parts.append("</div>")

    body_parts.append("</div>")
    body_html = "".join(body_parts)

    # OOB target = the shell's toast stack (`#dz-toast`, _render_shell) —
    # the wrapper div is consumed by the swap, its children prepended.
    toast_html = (
        f'<div hx-swap-oob="afterbegin:#dz-toast">'
        f'<div class="dz-toast" data-dz-toast-level="{safe_level}" '
        f'data-dz-remove-after="{safe_duration}" role="{role}">'
        f"{body_html}"
        f'<button type="button" class="dz-toast__close" '
        f'data-dz-toast-dismiss aria-label="Dismiss"></button>'
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
