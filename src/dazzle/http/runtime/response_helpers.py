"""
HTMX OOB swap response helpers.

Provides utilities for appending out-of-band HTML fragments to any
HTMLResponse, enabling server-driven toasts, breadcrumbs, and other
UI updates without client-side logic.

Toast emission follows stem **ssr-client-slot-parity**: one slot model
(``ToastSlots`` / ``toast_unit_html``) for OOB HTML; client ``showToast``
detail mirrors the same fields in ``dz-toast.js``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from typing import Any

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


def _toast_avatar_html(actor_name: str, actor_avatar: str | None) -> str:
    """Person composition leading media (decision 0011 phase E)."""
    if actor_avatar:
        return (
            f'<img class="dz-toast__avatar" src="{escape(actor_avatar, quote=True)}" '
            f'alt="" width="32" height="32" decoding="async" />'
        )
    # Initials fallback — first grapheme cluster-ish (ASCII-safe slice).
    initial = (actor_name.strip()[:1] or "?").upper()
    return (
        f'<span class="dz-toast__avatar dz-toast__avatar--fallback" '
        f'aria-hidden="true">{escape(initial)}</span>'
    )


@dataclass(frozen=True, slots=True)
class ToastSlots:
    """Shared SSR/client slot model for toast units (stem ssr-client-slot-parity).

    Client ``showToast`` detail should use the same field names
    (``message``, ``type``/``level``, ``title``, ``actions``, ``actor``,
    ``duration``, ``sound``).
    """

    message: str
    level: str = "info"
    duration: str | None = None
    title: str | None = None
    actions: Sequence[tuple[str, str]] | None = None
    actor_name: str | None = None
    actor_avatar: str | None = None
    sound: bool = False


def _toast_default_duration(level: str, duration: str | None) -> str:
    """Decision 0011 defaults: 10s for error, 8s otherwise."""
    if duration is not None:
        return duration
    return "10s" if level == "error" else "8s"


def _toast_actions_html(actions: Sequence[tuple[str, str]]) -> str:
    """Action row: link when href set, dismiss button when empty."""
    parts = ['<div class="dz-toast__actions">']
    for label, href in actions:
        safe_label = escape(label)
        if href:
            parts.append(
                f'<a class="dz-toast__action" href="{escape(href, quote=True)}">{safe_label}</a>'
            )
        else:
            parts.append(
                f'<button type="button" class="dz-toast__action" '
                f"data-dz-toast-dismiss>{safe_label}</button>"
            )
    parts.append("</div>")
    return "".join(parts)


def _toast_body_html(slots: ToastSlots, *, is_person: bool, safe_message: str) -> str:
    """Title / actor / message / actions inside ``.dz-toast__body``."""
    parts: list[str] = ['<div class="dz-toast__body">']
    if is_person:
        parts.append(
            f'<div class="dz-toast__title dz-toast__actor">{escape(slots.actor_name or "")}</div>'
        )
        if slots.title:
            parts.append(f'<div class="dz-toast__subtitle">{escape(slots.title)}</div>')
    elif slots.title:
        parts.append(f'<div class="dz-toast__title">{escape(slots.title)}</div>')
    parts.append(f'<div class="dz-toast__message">{safe_message}</div>')
    if slots.actions:
        parts.append(_toast_actions_html(slots.actions))
    parts.append("</div>")
    return "".join(parts)


def toast_unit_html(slots: ToastSlots) -> str:
    """Render one ``.dz-toast`` unit (no OOB wrapper) from shared slots."""
    level = slots.level if slots.level in _TOAST_ICON_PATHS else "info"
    duration = _toast_default_duration(level, slots.duration)
    is_person = bool(slots.actor_name and slots.actor_name.strip())
    leading = (
        _toast_avatar_html(slots.actor_name or "", slots.actor_avatar)
        if is_person
        else _toast_icon_html(level)
    )
    body_html = _toast_body_html(slots, is_person=is_person, safe_message=escape(slots.message))
    composition = ' data-dz-toast-composition="person"' if is_person else ""
    sound_attr = ' data-dz-toast-sound="on"' if slots.sound else ""
    return (
        f'<div class="dz-toast" data-dz-toast-level="{escape(level, quote=True)}" '
        f'data-dz-remove-after="{escape(duration, quote=True)}" '
        f'role="{"alert" if level == "error" else "status"}"'
        f"{composition}{sound_attr}>"
        f"{leading}{body_html}"
        f'<button type="button" class="dz-toast__close" '
        f'data-dz-toast-dismiss aria-label="Dismiss"></button>'
        f"</div>"
    )


def toast_detail_dict(slots: ToastSlots) -> dict[str, Any]:
    """JSON-serialisable detail for ``HX-Trigger: showToast`` / client parity."""
    level = slots.level if slots.level in _TOAST_ICON_PATHS else "info"
    duration = _toast_default_duration(level, slots.duration)
    detail: dict[str, Any] = {
        "message": slots.message,
        "type": level,
        "duration": duration,
    }
    if slots.title:
        detail["title"] = slots.title
    if slots.actions:
        detail["actions"] = [
            {"label": label, "href": href or None} for label, href in slots.actions
        ]
    if slots.actor_name:
        actor: dict[str, str] = {"name": slots.actor_name}
        if slots.actor_avatar:
            actor["avatar"] = slots.actor_avatar
        detail["actor"] = actor
    if slots.sound:
        detail["sound"] = True
    return detail


def with_toast(
    response: HTMLResponse,
    message: str,
    level: str = "info",
    duration: str | None = None,
    *,
    title: str | None = None,
    actions: Sequence[tuple[str, str]] | None = None,
    actor_name: str | None = None,
    actor_avatar: str | None = None,
    sound: bool = False,
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
        actor_name: Optional person composition (phase E) — avatar + name.
        actor_avatar: Optional image URL for the actor (decorative alt="").
        sound: Request an enter cue (phase F); page must opt in via
            ``meta dz-sound`` or ``data-dz-cue-sound=on`` (stem chrome-cue-opt-in).
    """
    unit = toast_unit_html(
        ToastSlots(
            message=message,
            level=level,
            duration=duration,
            title=title,
            actions=actions,
            actor_name=actor_name,
            actor_avatar=actor_avatar,
            sound=sound,
        )
    )
    toast_html = f'<div hx-swap-oob="afterbegin:#dz-toast">{unit}</div>'
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


__all__ = [
    "ToastSlots",
    "toast_detail_dict",
    "toast_unit_html",
    "with_oob",
    "with_toast",
]
