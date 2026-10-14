"""Server-side validator for the `widget=rich_text` field type.

Spec: dev_docs/2026-05-04-dz-richtext-spec.md (#977 cycle 4 §8).

The dz-richtext editor's client-side schema enforcement is a UX layer.
`clean_rich_text()` is meant to be the server-side boundary, using
`bleach` with the IR-sourced allowlist; drift between the client and
server allowlists is caught by `tests/unit/test_richtext_allowlist_parity.py`.

**Where it runs** (wired in flense ship T, ADR-0057): every write path
that persists a rich-text field calls it before validation.

- ``rich_text_fields_by_entity()`` derives, per entity, the fields that
  any surface renders with ``widget=rich_text`` (and that field's
  effective length cap). There is no rich-text field *type* in the IR —
  the widget hint on a ``text`` field is the only signal — so surfaces are
  the source of truth.
- ``server.py`` passes that map to ``RouteGenerator`` as
  ``entity_rich_text_fields``, threaded like ``entity_file_fields`` into
  ``create_create_handler`` / ``create_update_handler``
  (``handlers/write_handlers.py``), whose ``_core`` calls
  ``sanitise_rich_text_values()`` on the parsed body. The experience-form
  POST creates through the same ``_core`` (the ``_inprocess_create``
  invoker), so it is covered by the same call.
- A value whose *sanitised* form exceeds the cap is rejected with 422
  (never truncated, never stored). A visually empty value (the editor's
  ``<p><br></p>`` shell) becomes ``None``, the same as an empty textarea.

The function is deliberately small and dependency-light: take a
string, return a sanitised string, raise `ValueError` if too long.
"""

from __future__ import annotations

import re
from html import unescape
from typing import TYPE_CHECKING, Any

import bleach  # type: ignore[import-untyped,unused-ignore]

from dazzle.core.ir.richtext import (
    RICH_TEXT_ALLOWED_ATTRS,
    RICH_TEXT_ALLOWED_TAGS,
    RICH_TEXT_MAX_LENGTH_DEFAULT,
    RICH_TEXT_PROTOCOL_PATTERN,
    is_safe_href,
)

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec

# The surface option value that marks a field as rich text.
RICH_TEXT_WIDGET = "rich_text"

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


def _surface_cap(options: dict[str, Any]) -> int:
    """Effective cap for one surface element: its ``rich_text_max_length``
    option when it is a positive int, else the IR default."""
    raw = options.get("rich_text_max_length")
    try:
        cap = int(raw) if raw is not None else RICH_TEXT_MAX_LENGTH_DEFAULT
    except (TypeError, ValueError):
        return RICH_TEXT_MAX_LENGTH_DEFAULT
    return cap if cap > 0 else RICH_TEXT_MAX_LENGTH_DEFAULT


def rich_text_fields_by_entity(appspec: AppSpec) -> dict[str, dict[str, int]]:
    """Map entity name → {field name → length cap} for rich-text fields.

    A field is rich text when any surface over its entity renders it with
    ``widget=rich_text``. When several surfaces declare the field with
    different ``rich_text_max_length`` caps, the largest wins, so a value
    any of those editors accepts is also accepted by the write path.
    """
    out: dict[str, dict[str, int]] = {}
    for surface in appspec.surfaces:
        entity = surface.entity_ref
        if not entity:
            continue
        for section in surface.sections:
            for element in section.elements:
                if element.options.get("widget") != RICH_TEXT_WIDGET:
                    continue
                fields = out.setdefault(entity, {})
                cap = _surface_cap(element.options)
                fields[element.field_name] = max(fields.get(element.field_name, 0), cap)
    return out


def sanitise_rich_text_values(
    body: dict[str, Any],
    rich_text_fields: dict[str, int],
) -> None:
    """Sanitise every rich-text field present in ``body``, in place.

    Non-string values (absent, ``None``) are left alone. A visually empty
    value becomes ``None`` — the same as an empty textarea after the write
    path's empty-string normalisation.

    Raises:
        RichTextTooLongError: If a sanitised value exceeds its field's cap.
    """
    for name, cap in rich_text_fields.items():
        value = body.get(name)
        if not isinstance(value, str):
            continue
        try:
            cleaned = clean_rich_text(value, max_length=cap)
        except ValueError as exc:
            raise RichTextTooLongError(name, str(exc)) from exc
        body[name] = cleaned or None


class RichTextTooLongError(ValueError):
    """A rich-text value exceeded its length cap after sanitisation."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


__all__ = [
    "RICH_TEXT_PROTOCOL_PATTERN",
    "RICH_TEXT_WIDGET",
    "RichTextTooLongError",
    "clean_rich_text",
    "is_visually_empty_rich_text",
    "rich_text_fields_by_entity",
    "sanitise_rich_text_values",
]
