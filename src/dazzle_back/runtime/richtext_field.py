"""Server-side validator for the `widget=rich_text` field type.

Spec: dev_docs/2026-05-04-dz-richtext-spec.md (#977 cycle 4 §8).

The dz-richtext editor's client-side schema enforcement is a UX layer.
The security boundary is here: every persisted rich-text value passes
through `clean_rich_text()`, which uses `bleach` with the IR-sourced
allowlist. Drift between the client and server allowlists is caught
by `tests/unit/test_richtext_allowlist_parity.py`.

The function is deliberately small and dependency-light: take a
string, return a sanitised string, raise `ValueError` if too long.
"""

from __future__ import annotations

import bleach  # type: ignore[import-untyped,unused-ignore]

from dazzle.core.ir.richtext import (
    RICH_TEXT_ALLOWED_ATTRS,
    RICH_TEXT_ALLOWED_TAGS,
    RICH_TEXT_MAX_LENGTH_DEFAULT,
    RICH_TEXT_PROTOCOL_PATTERN,
    is_safe_href,
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
    if not raw:
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
]
