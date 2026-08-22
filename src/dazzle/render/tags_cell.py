"""Clerk-facing tag cells for list/queue/detail (oral #171).

Kept out of ``filters.py`` so that module's maintainability index stays A.
"""

from __future__ import annotations

from html import escape as _html_escape
from typing import Any

_TAGS_FIELD_KEYS = frozenset({"tags", "labels", "keywords"})


def tags_field_name(name: Any) -> bool:
    """True when ``name`` is a tags bag (not a singular ``label``)."""
    key = str(name or "").strip().lower()
    return key in _TAGS_FIELD_KEYS


def clerk_tags_tokens(value: Any) -> tuple[str, ...]:
    """Split a tags bag into tokens. Leftover junk stays a token."""
    if value is None or value == "":
        return ()
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value]
    else:
        parts = [part.strip() for part in str(value).replace("\r", "\n").split(",")]
        extra: list[str] = []
        for part in parts:
            extra.extend(p.strip() for p in part.split("\n"))
        parts = extra
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part:
            continue
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return tuple(out)


def clerk_tags_join(value: Any) -> str:
    """CSV / related-table text: comma-joined tokens, not ``str(list)``."""
    return ", ".join(clerk_tags_tokens(value))


def clerk_tags_cell_html(value: Any) -> str:
    """Read-only HM tag chips. Empty invents nothing. Leftover ``zzz`` stays a chip."""
    tokens = clerk_tags_tokens(value)
    if not tokens:
        return ""
    chips: list[str] = []
    for token in tokens:
        escaped = _html_escape(token)
        attr = _html_escape(token, quote=True)
        chips.append(
            f'<span class="dz-tags-chip" role="listitem" data-dz-value="{attr}">'
            f'<span class="dz-tags-chip-label">{escaped}</span></span>'
        )
    return (
        '<span class="dz-tags dz-tags--readonly">'
        f'<span class="dz-tags-list" role="list">{"".join(chips)}</span></span>'
    )
