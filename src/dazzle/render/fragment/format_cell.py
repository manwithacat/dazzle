"""Pure cell-value formatter for typed-table grids (#1470).

Renders a stored value to a display string by the column's declared *kind*
(plus the Python value type for numeric rounding). No I/O — unit-testable in
isolation. The http fragment adapter (`_format_cell`) calls this in place of
the old `str()`-coerce stub, so FK names, money, rounded floats, Yes/No bools,
title-cased enums and friendly dates render correctly across every grid.

**Returns RAW (unescaped) strings.** The renderer owns HTML escaping — both
consumers (`Table` cells via `_render_tables`, `Text` via `_emit_text`) call
`ctx.escape(...)` at emit time, so this formatter must NOT pre-escape or values
would be double-encoded (e.g. `&` → `&amp;amp;`). This mirrors the old stub's
raw `str(value)` contract.

FK display values are already resolved upstream (`fk_display_only`), so a
``ref`` cell's value is already the name. Phase 2 (#1470) adds the explicit
``format:`` override via `override=`.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

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
    """Format integer minor units (e.g. pence) as a currency string (raw)."""
    try:
        major = Decimal(int(minor)) / 100
    except (TypeError, ValueError, InvalidOperation):
        return str(minor)
    symbol = _CURRENCY_SYMBOLS.get(code.upper(), "")
    return f"{symbol}{major:,.2f}" if symbol else f"{major:,.2f} {code}"


def _friendly_dt(value: Any, *, with_time: bool) -> str:
    """Return a friendly (non-ISO) date/datetime string (raw)."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return str(value)
    if isinstance(value, (datetime, date)):
        # `value.day` avoids the non-portable `%-d` strftime directive.
        tail = (
            value.strftime("%b %Y %H:%M")
            if isinstance(value, datetime) and with_time
            else value.strftime("%b %Y")
        )
        return f"{value.day} {tail}"
    return str(value)


def _infer(value: Any, kind: str, currency_code: str) -> str:
    # bool first: catches bool values regardless of the (coarse) column kind.
    if kind == "bool" or isinstance(value, bool):
        return "Yes" if value else "No"
    if kind == "currency":
        return _currency(value, currency_code or "GBP")
    if kind == "badge":
        return _title_case(str(value))
    if kind == "date":
        return _friendly_dt(value, with_time=isinstance(value, datetime))
    # float/Decimal round to 2dp (the column vocabulary collapses these to "text",
    # so rounding is keyed off the Python value type, not the kind).
    if isinstance(value, (float, Decimal)):
        return f"{float(value):.2f}"
    return str(value)


def format_cell(
    value: Any,
    kind: str,
    *,
    currency_code: str = "",
    override: ResolvedFormat | None = None,
) -> str:
    """Render ``value`` to a RAW (unescaped) display string.

    ``kind`` is the column's display type (``text``/``bool``/``date``/
    ``currency``/``badge``/``ref``). ``override`` (Phase 2) wins over inference.
    The renderer escapes the result at emit time — do not escape here.
    """
    if value is None or value == "":
        return ""
    if override is not None:
        return _apply_override(value, override, currency_code)
    return _infer(value, kind, currency_code)


def _apply_override(value: Any, fmt: ResolvedFormat, currency_code: str) -> str:
    """Apply an explicit ``format:`` override. Implemented in Phase 2 (#1470)."""
    raise NotImplementedError("format: override is wired in #1470 Phase 2")
