"""Clerk-facing reachable-channel cells for list/queue/detail (oral #173).

Email and phone must be tappable (``mailto:`` / ``tel:``), not dead text.
Kept out of ``filters.py`` so that module's maintainability index stays A.
Render-layer only — no ``http/`` import (ADR-0038).
"""

from __future__ import annotations

from html import escape as _html_escape
from typing import Any

from dazzle.core.mailbox_shape import is_mailbox_shape

_EMAIL_FIELD_KEYS = frozenset({"email"})
_PHONE_FIELD_KEYS = frozenset(
    {
        "phone",
        "mobile",
        "telephone",
        "tel",
        "phone_number",
        "mobile_number",
        "work_phone",
        "home_phone",
        "cell",
        "cellphone",
    }
)
_LEFTOVER_TOKENS = frozenset({"zzz", "2abc", "1e2", "ghost"})
_PHONE_MIN_DIGITS = 7
_PHONE_SEP = frozenset(" ()-./")


def email_field_name(name: Any) -> bool:
    """True when ``name`` is a reachable mailbox (not ``email_count``)."""
    key = str(name or "").strip().lower()
    if key in _EMAIL_FIELD_KEYS:
        return True
    return key.endswith("_email")


def phone_field_name(name: Any) -> bool:
    """True when ``name`` is a reachable phone (not ``channel``)."""
    key = str(name or "").strip().lower()
    if key in _PHONE_FIELD_KEYS:
        return True
    return key.endswith("_phone") or key.endswith("_mobile") or key.endswith("_tel")


def clerk_channel_display(value: Any) -> str:
    """CSV / related text: the clerk-facing channel string. Leftover stays put."""
    if value is None or value == "":
        return ""
    return str(value).strip()


clerk_email_display = clerk_channel_display
clerk_phone_display = clerk_channel_display


def _leftover_channel(value: Any) -> bool:
    if value is None or value == "":
        return False
    return str(value).strip().lower() in _LEFTOVER_TOKENS


def clerk_email_href(value: Any) -> str | None:
    """``mailto:`` href, or None when leftover / empty / not a mailbox."""
    if value is None or value == "" or _leftover_channel(value):
        return None
    text = str(value).strip()
    if not is_mailbox_shape(text):
        return None
    return f"mailto:{text}"


def clerk_phone_href(value: Any) -> str | None:
    """``tel:`` href (digits / leading +), or None when leftover / junk."""
    if value is None or value == "" or _leftover_channel(value):
        return None
    text = str(value).strip()
    plus = False
    digits: list[str] = []
    for ch in text:
        if ch.isdigit():
            digits.append(ch)
        elif ch in _PHONE_SEP:
            continue
        elif ch == "+" and not digits and not plus:
            plus = True
        else:
            return None
    if len(digits) < _PHONE_MIN_DIGITS:
        return None
    body = "".join(digits)
    return f"tel:+{body}" if plus else f"tel:{body}"


def _channel_cell_html(value: Any, href: str | None, kind: str) -> str:
    if value is None or value == "":
        return ""
    label = clerk_channel_display(value)
    if href is None:
        return _html_escape(label)
    safe_href = _html_escape(href, quote=True)
    return (
        f'<a href="{safe_href}" class="dz-channel-link dz-channel-link--{kind}">'
        f"{_html_escape(label)}</a>"
    )


def clerk_email_cell_html(value: Any) -> str:
    """Read-only mailto link. Empty invents nothing. Leftover ``zzz`` stays put."""
    return _channel_cell_html(value, clerk_email_href(value), "email")


def clerk_phone_cell_html(value: Any) -> str:
    """Read-only tel link. Empty invents nothing. Leftover ``zzz`` stays put."""
    return _channel_cell_html(value, clerk_phone_href(value), "phone")
