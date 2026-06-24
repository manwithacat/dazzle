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


def _currency_str(major: Decimal, code: str) -> str:
    symbol = _CURRENCY_SYMBOLS.get(code.upper(), "")
    return f"{symbol}{major:,.2f}" if symbol else f"{major:,.2f} {code}"


def _currency(minor: Any, code: str) -> str:
    """Format integer MINOR units (e.g. pence) as currency — the money-type
    inference path (the money column stores minor units in ``<name>_minor``)."""
    try:
        major = Decimal(int(minor)) / 100
    except (TypeError, ValueError, InvalidOperation):
        return str(minor)
    return _currency_str(major, code)


def _currency_major(value: Any, code: str) -> str:
    """Format a MAJOR-unit numeric as currency — the explicit ``format: currency``
    override on a decimal/float field (which stores the amount as-is, not minor)."""
    try:
        major = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return str(value)
    return _currency_str(major, code)


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


def _coerce_dt(value: Any) -> datetime | date | None:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return value if isinstance(value, (datetime, date)) else None


def _format_temporal(value: Any, kind: str, arg: str | None) -> str:
    dtv = _coerce_dt(value)
    if dtv is None:
        return str(value)
    if arg == "iso":
        return dtv.isoformat()
    if arg == "long":
        return f"{dtv.day} {dtv.strftime('%B %Y')}"
    return _friendly_dt(dtv, with_time=(kind == "datetime"))


def _relative(value: Any) -> str:
    dtv = _coerce_dt(value)
    if dtv is None:
        return str(value)
    d = dtv.date() if isinstance(dtv, datetime) else dtv
    delta = (d - date.today()).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta == -1:
        return "yesterday"
    return f"{-delta} days ago" if delta < 0 else f"in {delta} days"


def _dp(arg: str | None) -> int:
    """Decimal-places argument (default 0)."""
    return int(arg) if arg and arg.isdigit() else 0


# Simple value→string transforms keyed by override kind (no arg/currency needed).
_SIMPLE_OVERRIDES: dict[str, Any] = {
    "raw": str,
    "upper": lambda v: str(v).upper(),
    "lower": lambda v: str(v).lower(),
    "title_case": lambda v: _title_case(str(v)),
    "yes_no": lambda v: "Yes" if v else "No",
    "display_name": str,
}


def _apply_override(value: Any, fmt: ResolvedFormat, currency_code: str) -> str:
    """Apply an explicit ``format:`` override (#1470 Phase 2). Returns RAW.

    Validation (`_format_kind_error`) has already rejected unknown kinds and
    type mismatches, so this dispatches the v1 vocabulary directly.
    """
    kind, arg = fmt.kind, fmt.arg
    if kind == "currency":
        return _currency_major(value, arg or currency_code or "GBP")
    if kind == "percent":
        return f"{float(value) * 100:,.{_dp(arg)}f}%"
    if kind == "round":
        return f"{float(value):,.{_dp(arg)}f}"
    if kind in ("date", "datetime"):
        return _format_temporal(value, kind, arg)
    if kind == "relative":
        return _relative(value)
    transform = _SIMPLE_OVERRIDES.get(kind)
    if transform is not None:
        return str(transform(value))
    return str(value)  # defensive (validation rejects unknown kinds)
