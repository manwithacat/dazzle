"""Server-side validator for the `widget=rich_text` field type.

Spec: dev_docs/2026-05-04-dz-richtext-spec.md (#977 cycle 4 §8).

The dz-richtext editor's client-side schema enforcement is a UX layer.
`clean_rich_text()` is meant to be the server-side boundary, using
`bleach` with the IR-sourced allowlist; drift between the client and
server allowlists is caught by `tests/unit/test_richtext_allowlist_parity.py`.

**Not yet wired** (found in flense ships H/K, 2026-10-13): no write path
calls `clean_rich_text()`. `widget=rich_text` is a surface hint on a plain
`text` field, so the create/update handlers in
`handlers/write_handlers.py` persist the posted HTML unchanged. The edit
form escapes the stored value into its textarea
(`_render_forms._emit_rich_text`) and `dz-richtext.js` re-sanitises on
load, but JSON API readers receive the raw HTML and any display path that
emits a text value as `RawHTML` without escaping would be a stored XSS. Wiring it (per-entity rich-text field set derived from
surfaces, threaded like `file_fields` through `route_generator` into
`create_create_handler` / `create_update_handler`) is a dedicated ship.

The function is deliberately small and dependency-light: take a
string, return a sanitised string, raise `ValueError` if too long.
"""

from __future__ import annotations

import re
from html import unescape

import bleach  # type: ignore[import-untyped,unused-ignore]

from dazzle.core.ir.richtext import (
    RICH_TEXT_ALLOWED_ATTRS,
    RICH_TEXT_ALLOWED_TAGS,
    RICH_TEXT_MAX_LENGTH_DEFAULT,
    RICH_TEXT_PROTOCOL_PATTERN,
    is_safe_href,
)

# nbsp / ZWSP / whitespace after bleach strips every tag. The
# contenteditable empty shell is ``<p><br></p>``. That must not
# persist as a filled required value (cycle 2128 — same honesty
# class as money inventing 0). Cycle 2129: bleach, not ``<[^>]+>``
# (CodeQL js/incomplete-multi-character-sanitization #226 twin).
_EMPTY_TOKEN = re.compile(
    r"(?:&nbsp;|&#160;|&#x0*a0;|[\s\u00a0\u200b])+",
    re.IGNORECASE,
)


def _attr_filter(tag: str, name: str, value: str) -> bool:
    """bleach attribute callback — enforces the IR per-tag attr map
    and re-validates href against the protocol regex."""
    allowed = RICH_TEXT_ALLOWED_ATTRS.get(tag)
    if not allowed or name not in allowed:
        return False
    if tag == "a" and name == "href":
        return is_safe_href(value)
    return True


# Protocols bleach permits at the URI level. Belt-and-braces with the
# attribute callback above — both must accept the href for it to land.
_BLEACH_PROTOCOLS = ["http", "https", "mailto"]


def is_visually_empty_rich_text(html: str) -> bool:
    """True when markup has no user-visible text.

    The editor SSRs ``<p><br></p>`` as the caret host. Required fields
    and persistence must treat that (and whitespace-only siblings) as
    empty, not as a filled paragraph.
    """
    if not html or not str(html).strip():
        return True
    text = unescape(
        bleach.clean(
            str(html),
            tags=[],
            strip=True,
            strip_comments=True,
        )
    )
    return not _EMPTY_TOKEN.sub("", text)


def clean_rich_text(
    raw: str,
    *,
    max_length: int | None = None,
) -> str:
    """Sanitise a rich-text string for persistence.

    Strips every tag/attribute outside the IR allowlist, re-validates
    href protocols, and enforces a length cap on the result.

    Args:
        raw: Untrusted HTML from the form post.
        max_length: Override the default character cap.
            None → `RICH_TEXT_MAX_LENGTH_DEFAULT`.

    Returns:
        Sanitised HTML safe to store and re-render.

    Raises:
        ValueError: If the sanitised output exceeds `max_length`.
    """
    if is_visually_empty_rich_text(raw):
        return ""
    cleaned: str = bleach.clean(
        raw,
        tags=RICH_TEXT_ALLOWED_TAGS,
        attributes=_attr_filter,
        protocols=_BLEACH_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )
    cap = max_length if max_length is not None else RICH_TEXT_MAX_LENGTH_DEFAULT
    if len(cleaned) > cap:
        raise ValueError(f"rich-text value exceeds {cap} characters (got {len(cleaned)})")
    return cleaned


__all__ = [
    "RICH_TEXT_PROTOCOL_PATTERN",
    "clean_rich_text",
    "is_visually_empty_rich_text",
]
