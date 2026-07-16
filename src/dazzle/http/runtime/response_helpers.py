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

# Inline SVG glyphs (lucide-shaped) — self-contained so OOB toasts work
# without a page icon sprite. Decorative only (aria-hidden on the wrapper).
_TOAST_ICON_PATHS: dict[str, str] = {
    "info": ('<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>'),
    "success": ('<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>'),
    "warning": (
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>'
        '<path d="M12 9v4"/><path d="M12 17h.01"/>'
    ),
    "error": ('<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>'),
}


def _toast_icon_html(level: str) -> str:
    """Decorative level icon for a toast unit (decision 0011 phase D)."""
    paths = _TOAST_ICON_PATHS.get(level) or _TOAST_ICON_PATHS["info"]
    return (
        '<span class="dz-toast__icon" aria-hidden="true">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f"{paths}</svg></span>"
    )


def with_toast(
    response: HTMLResponse,
    message: str,
    level: str = "info",
    duration: str | None = None,
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
        duration: Auto-dismiss delay (e.g., ``"8s"``). When omitted: **8s**
            for info/success/warning, **10s** for error (decision 0011).
        title: Optional heading above the message.
        actions: Optional ``(label, href)`` pairs. Empty href renders a
            dismiss button (``data-dz-toast-dismiss``); non-empty href is a
            link. Labels and hrefs are escaped.
    """
    if duration is None:
        duration = "10s" if level == "error" else "8s"
    safe_message = escape(message)
    safe_level = escape(level, quote=True)
    safe_duration = escape(duration, quote=True)
    role = "alert" if level == "error" else "status"
    icon_html = _toast_icon_html(level if level in _TOAST_ICON_PATHS else "info")

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
        f"{icon_html}{body_html}"
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
