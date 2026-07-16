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

FK display: prefer an already-resolved name string; when the value is still a
hydrated dict (related-group path, #1615), resolve via ``_ref_display_name``
(``__display__`` / name heuristics). Never dump ``str(dict)`` into the UI.
Phase 2 (#1470) adds the explicit ``format:`` override via `override=`.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from dazzle.i18n.display_locale import DisplayLocaleProfile, get_display_locale

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


def _profile(profile: DisplayLocaleProfile | None = None) -> DisplayLocaleProfile:
    if profile is not None:
        return profile
    return get_display_locale()


def _friendly_dt(
    value: Any, *, with_time: bool, profile: DisplayLocaleProfile | None = None
) -> str:
    """Return a locale-profile date/datetime string (raw).

    Pure ``date`` values never TZ-shift. ``datetime`` values display in the
    profile timezone (#1597).
    """
    prof = _profile(profile)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if isinstance(value, datetime) and with_time:
        return prof.format_datetime_value(value)
    if isinstance(value, (datetime, date)):
        # date-only (or datetime column treated as date): calendar day, no TZ
        d = value.date() if isinstance(value, datetime) else value
        return prof.format_date_value(d)
    return str(value)


def _infer(
    value: Any,
    kind: str,
    currency_code: str,
    profile: DisplayLocaleProfile | None = None,
) -> str:
    prof = _profile(profile)
    # bool first: catches bool values regardless of the (coarse) column kind.
    if kind == "bool" or isinstance(value, bool):
        return "Yes" if value else "No"
    if kind == "currency":
        # money(CODE) is authoritative; profile only supplies fallback code
        return _currency(value, currency_code or prof.currency_default or "GBP")
    if kind == "badge":
        # Hydrated enum/ref dicts must not dump as str(dict) (#1615).
        if isinstance(value, dict):
            from dazzle.render.filters import _ref_display_name

            return _title_case(_ref_display_name(value))
        return _title_case(str(value))
    # #1615: related-group path passes hydrated FK dicts with kind=ref (or
    # sometimes text). Lists already use _ref_display_name; format_cell must
    # match so detail related tables never show Python dict repr.
    if kind == "ref" or isinstance(value, dict):
        from dazzle.render.filters import _ref_display_name

        if isinstance(value, dict):
            return _ref_display_name(value)
        return str(value)
    if kind == "date":
        return _friendly_dt(value, with_time=False, profile=prof)
    if kind == "datetime":
        # Strings that parse as datetime keep the time; pure date values stay
        # date-only. Previously only kind=="date" was handled, so datetime
        # columns fell through to raw ISO (often with microseconds).
        return _friendly_dt(value, with_time=True, profile=prof)
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
    profile: DisplayLocaleProfile | None = None,
) -> str:
    """Render ``value`` to a RAW (unescaped) display string.

    ``kind`` is the column's display type (``text``/``bool``/``date``/
    ``currency``/``badge``/``ref``). ``override`` (Phase 2) wins over inference.
    ``profile`` (#1597) is the display locale; defaults to the request-bound
    :func:`~dazzle.i18n.display_locale.get_display_locale` (product en-GB).
    The renderer escapes the result at emit time — do not escape here.
    """
    if value is None or value == "":
        return ""
    if override is not None:
        return _apply_override(value, override, currency_code, profile=profile)
    return _infer(value, kind, currency_code, profile=profile)


def _coerce_dt(value: Any) -> datetime | date | None:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value if isinstance(value, (datetime, date)) else None


def _format_temporal(
    value: Any,
    kind: str,
    arg: str | None,
    profile: DisplayLocaleProfile | None = None,
) -> str:
    dtv = _coerce_dt(value)
    if dtv is None:
        return str(value)
    if arg == "iso":
        return dtv.isoformat()
    if arg == "long":
        d = dtv.date() if isinstance(dtv, datetime) else dtv
        return f"{d.day} {d.strftime('%B %Y')}"
    return _friendly_dt(dtv, with_time=(kind == "datetime"), profile=profile)


def _relative(value: Any, profile: DisplayLocaleProfile | None = None) -> str:
    """Relative day labels using tenant-timezone ``today`` (#1597)."""
    dtv = _coerce_dt(value)
    if dtv is None:
        return str(value)
    # Calendar dates: no TZ. Datetimes: convert to tenant TZ before taking date.
    prof = _profile(profile)
    if isinstance(dtv, datetime):
        d = prof.to_display_datetime(dtv).date()
    else:
        d = dtv
    delta = (d - prof.today()).days
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


def _apply_override(
    value: Any,
    fmt: ResolvedFormat,
    currency_code: str,
    profile: DisplayLocaleProfile | None = None,
) -> str:
    """Apply an explicit ``format:`` override (#1470 Phase 2). Returns RAW.

    Validation (`_format_kind_error`) has already rejected unknown kinds and
    type mismatches, so this dispatches the v1 vocabulary directly.
    """
    prof = _profile(profile)
    kind, arg = fmt.kind, fmt.arg
    if kind == "currency":
        # Explicit format: currency(CODE) or field currency wins; never convert.
        return _currency_major(value, arg or currency_code or prof.currency_default or "GBP")
    if kind == "percent":
        return f"{float(value) * 100:,.{_dp(arg)}f}%"
    if kind == "round":
        return f"{float(value):,.{_dp(arg)}f}"
    if kind in ("date", "datetime"):
        return _format_temporal(value, kind, arg, profile=prof)
    if kind == "relative":
        return _relative(value, profile=prof)
    transform = _SIMPLE_OVERRIDES.get(kind)
    if transform is not None:
        return str(transform(value))
    return str(value)  # defensive (validation rejects unknown kinds)
