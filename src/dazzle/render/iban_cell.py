"""Clerk-facing IBAN cells for list/queue/detail/CSV (oral #176).

Vendor bank-ref queues dumped ``GB82WEST12345698765432`` as a blob.
ISO 13616 paper form is groups of four. Kept out of ``filters.py`` so
that module's maintainability index stays A.
Do not map generic account numbers, sort codes, or leftover tokens.
"""

from __future__ import annotations

from html import escape as _html_escape
from typing import Any

from dazzle.render.filters import _LEFTOVER_STAGE_TOKENS

_IBAN_FIELD_KEYS = frozenset({"iban", "iban_number"})
_IBAN_MIN_LEN = 15
_IBAN_MAX_LEN = 34


def iban_field_name(name: Any) -> bool:
    """True when ``name`` is an IBAN (not ``iban_count`` / ``liban``)."""
    key = str(name or "").strip().lower()
    if not key or key.endswith("_count"):
        return False
    if key in _IBAN_FIELD_KEYS:
        return True
    return key.endswith("_iban")


def _leftover_iban(value: Any) -> bool:
    if value is None or value == "":
        return False
    return str(value).strip().lower() in _LEFTOVER_STAGE_TOKENS


def clerk_iban_compact(value: Any) -> str | None:
    """Electronic IBAN (no spaces) when the value is ISO-shaped, else None."""
    if value is None or value == "" or _leftover_iban(value):
        return None
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return None
    compact = "".join(ch for ch in str(value).strip() if ch not in " \t-")
    if len(compact) < _IBAN_MIN_LEN or len(compact) > _IBAN_MAX_LEN:
        return None
    if not compact.isalnum():
        return None
    country = compact[:2]
    check = compact[2:4]
    if not country.isalpha() or not check.isdigit():
        return None
    return compact.upper()


def clerk_iban_display(value: Any) -> str:
    """CSV / related text: ``GB82 WEST 1234 5698 7654 32``. Leftover stays put."""
    if value is None or value == "":
        return ""
    compact = clerk_iban_compact(value)
    if compact is None:
        return str(value).strip() if isinstance(value, str) else str(value)
    return " ".join(compact[i : i + 4] for i in range(0, len(compact), 4))


def clerk_iban_cell_html(value: Any) -> str:
    """Read-only grouped IBAN. Empty invents nothing. Leftover ``zzz`` stays put."""
    if value is None or value == "":
        return ""
    if _leftover_iban(value):
        return _html_escape(str(value).strip())
    compact = clerk_iban_compact(value)
    if compact is None:
        return _html_escape(str(value).strip() if isinstance(value, str) else str(value))
    display = clerk_iban_display(value)
    return f'<span class="dz-iban">{_html_escape(display)}</span>'
