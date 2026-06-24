"""Pure cell-value formatter for typed-table grids (#1470).

Renders a stored value to a display string by the column's declared *kind*
(plus the Python value type for numeric rounding). No I/O — unit-testable in
isolation. The http fragment adapter (`_format_cell`) calls this in place of
the old `str()`-coerce stub, so FK names, money, rounded floats, Yes/No bools,
title-cased enums and friendly dates render correctly across every grid.

FK display values are already resolved upstream (`fk_display_only`), so a
``ref`` cell's value is already the name — formatting is just safe escaping.

Phase 2 (#1470) adds the explicit ``format:`` override via `override=`.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from dazzle.render.html import esc

# v1 currency symbols; unknown codes fall back to a "<amount> <CODE>" suffix.
_CURRENCY_SYMBOLS = {"GBP": "£", "USD": "$", "EUR": "€"}


@dataclass(frozen=True)
class ResolvedFormat:
    """A resolved format directive — explicit override or inferred default."""

    kind: str
    arg: str | None = None


def _title_case(token: str) -> str:
    return token.replace("_", " ").replace("-", " ").strip().title()


def _currency(minor: Any, code: str) -> str:
    """Format integer minor units (e.g. pence) as a currency string."""
    try:
        major = Decimal(int(minor)) / 100
    except (TypeError, ValueError, InvalidOperation):
        return str(minor)
    symbol = _CURRENCY_SYMBOLS.get(code.upper(), "")
    return f"{symbol}{major:,.2f}" if symbol else f"{major:,.2f} {code}"


def _friendly_dt(value: Any, *, with_time: bool) -> str:
    """Return a friendly (non-ISO) date/datetime string. Raw — caller escapes."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return str(value)
    if isinstance(value, datetime):
        return value.strftime("%-d %b %Y %H:%M" if with_time else "%-d %b %Y")
    if isinstance(value, date):
        return value.strftime("%-d %b %Y")
    return str(value)


def _infer(value: Any, kind: str, currency_code: str) -> str:
    # bool first: catches bool values regardless of the (coarse) column kind.
    if kind == "bool" or isinstance(value, bool):
        return "Yes" if value else "No"
    if kind == "currency":
        # currency output is controlled (symbol/digits/sep) — no escaping needed.
        return _currency(value, currency_code or "GBP")
    if kind == "badge":
        return esc(_title_case(str(value)))
    if kind == "date":
        return esc(_friendly_dt(value, with_time=isinstance(value, datetime)))
    # float/Decimal round to 2dp (the column vocabulary collapses these to "text",
    # so rounding is keyed off the Python value type, not the kind).
    if isinstance(value, (float, Decimal)):
        return esc(f"{float(value):.2f}")
    return esc(str(value))


def format_cell(
    value: Any,
    kind: str,
    *,
    currency_code: str = "",
    override: ResolvedFormat | None = None,
) -> str:
    """Render ``value`` to an HTML-escaped display string.

    ``kind`` is the column's display type (``text``/``bool``/``date``/
    ``currency``/``badge``/``ref``). ``override`` (Phase 2) wins over inference.
    """
    if value is None or value == "":
        return ""
    if override is not None:
        return _apply_override(value, override, currency_code)
    return _infer(value, kind, currency_code)


def _apply_override(value: Any, fmt: ResolvedFormat, currency_code: str) -> str:
    """Apply an explicit ``format:`` override. Implemented in Phase 2 (#1470)."""
    raise NotImplementedError("format: override is wired in #1470 Phase 2")
