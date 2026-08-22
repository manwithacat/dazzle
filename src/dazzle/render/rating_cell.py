"""Clerk-facing 1–5 rating cells for list/queue/detail/CSV (oral #172).

Kept out of ``filters.py`` so that module's maintainability index stays A.
"""

from __future__ import annotations

from html import escape as _html_escape
from typing import Any

_RATING_FIELD_KEYS = frozenset({"rating", "quality_score"})
_RATING_MAX = 5
_LEFTOVER_TOKENS = frozenset({"zzz", "2abc", "1e2", "ghost"})


def rating_field_name(name: Any) -> bool:
    """True when ``name`` is a 1–5 rating (not a generic ``*_score``)."""
    key = str(name or "").strip().lower()
    return key in _RATING_FIELD_KEYS


def _leftover_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if text.lower() in _LEFTOVER_TOKENS:
        return text
    return None


def clerk_rating_value(value: Any) -> int | None:
    """Parse a 1–5 rating. Leftover junk and out-of-range stay None."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    if _leftover_text(value) is not None:
        return None
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    if 1 <= number <= _RATING_MAX:
        return number
    return None


def clerk_rating_display(value: Any) -> str:
    """CSV / related text: ``4/5`` not bare ``4``. Leftover stays put."""
    if value is None or value == "":
        return ""
    leftover = _leftover_text(value)
    if leftover is not None:
        return leftover
    parsed = clerk_rating_value(value)
    if parsed is None:
        return str(value)
    return f"{parsed}/{_RATING_MAX}"


def clerk_rating_cell_html(value: Any) -> str:
    """Read-only star row. Empty invents nothing. Leftover ``zzz`` stays put."""
    if value is None or value == "":
        return ""
    leftover = _leftover_text(value)
    if leftover is not None:
        return _html_escape(leftover)
    parsed = clerk_rating_value(value)
    if parsed is None:
        return _html_escape(str(value))
    filled = "★" * parsed
    empty = "☆" * (_RATING_MAX - parsed)
    label = f"{parsed} out of {_RATING_MAX}"
    return (
        f'<span class="dz-rating" role="img" aria-label="{_html_escape(label, quote=True)}">'
        f'<span class="dz-rating-filled" aria-hidden="true">{filled}</span>'
        f'<span class="dz-rating-empty" aria-hidden="true">{empty}</span>'
        "</span>"
    )
