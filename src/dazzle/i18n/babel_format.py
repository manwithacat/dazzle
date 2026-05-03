"""Locale-aware date / number / currency formatting (#955 cycle 4).

Wraps `babel.dates` / `babel.numbers` so templates can write::

    {{ created_at | format_date }}     {# uses request locale #}
    {{ created_at | format_date("full") }}
    {{ amount | format_currency("USD") }}
    {{ count | format_number }}

…and the output flips per the user's locale as resolved by the cycle-1
`LocaleMiddleware`. Without Babel installed (the `[i18n]` extra), these
helpers fall back to locale-independent ISO/ASCII output so templates
keep rendering — they just stop following locale conventions.

Babel uses ``en_US``-style locale codes (underscore). The middleware
emits BCP-47 (``en-US``). This module normalises both forms so callers
don't have to think about it.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Any

from dazzle.i18n import get_current_locale

logger = logging.getLogger(__name__)


def _to_babel_locale(locale: str) -> str:
    """Convert a BCP-47 tag (en-US) to Babel's underscore form (en_US).

    Babel accepts both forms in newer versions, but normalising up
    front keeps error messages consistent and avoids per-call probes.
    """
    return (locale or "").replace("-", "_")


def _coerce_date(value: Any) -> date | datetime | None:
    """Best-effort date/datetime coercion. Returns None when unparseable."""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _coerce_time(value: Any) -> time | datetime | None:
    if value is None:
        return None
    if isinstance(value, (time, datetime)):
        return value
    if isinstance(value, str):
        # Try ISO datetime first (covers "2026-05-03T14:30:00") then
        # bare time strings.
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            try:
                return time.fromisoformat(value)
            except ValueError:
                return None
    return None


def _coerce_decimal(value: Any) -> Any:
    """Coerce to a Babel-friendly numeric type. ``None`` and bools
    return ``None`` to skip formatting (caller decides fallback)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return value  # let babel try


def format_date(value: Any, fmt: str = "medium", locale: str | None = None) -> str:
    """Format a date / datetime per *locale* (default: current request locale).

    *fmt* is a Babel format key — ``"short"`` / ``"medium"`` / ``"long"``
    / ``"full"`` — or a custom skeleton like ``"yyyy-MM-dd"``.

    Falls back to ISO date string when Babel is unavailable, or the
    raw value when coercion fails (so misshapen input doesn't blow
    up the page render).
    """
    target = _coerce_date(value)
    if target is None:
        return "" if value is None else str(value)
    try:
        from babel.dates import format_date as _babel_format_date  # type: ignore[import-not-found]
    except ImportError:
        # Fallback: locale-independent ISO date
        if isinstance(target, datetime):
            return target.date().isoformat()
        return target.isoformat()
    locale_code = _to_babel_locale(locale or get_current_locale())
    try:
        return _babel_format_date(target, format=fmt, locale=locale_code)
    except Exception as exc:
        logger.debug("format_date failed for locale=%s fmt=%s: %s", locale_code, fmt, exc)
        if isinstance(target, datetime):
            return target.date().isoformat()
        return target.isoformat()


def format_datetime(value: Any, fmt: str = "medium", locale: str | None = None) -> str:
    """Format a datetime per *locale*. Same fmt vocabulary as format_date."""
    target = _coerce_date(value)
    if target is None:
        return "" if value is None else str(value)
    try:
        from babel.dates import (  # type: ignore[import-not-found]
            format_datetime as _babel_format_datetime,
        )
    except ImportError:
        return (
            target.isoformat() if isinstance(target, datetime) else target.isoformat() + "T00:00:00"
        )
    locale_code = _to_babel_locale(locale or get_current_locale())
    try:
        return _babel_format_datetime(target, format=fmt, locale=locale_code)
    except Exception as exc:
        logger.debug("format_datetime failed for locale=%s fmt=%s: %s", locale_code, fmt, exc)
        return (
            target.isoformat() if isinstance(target, datetime) else target.isoformat() + "T00:00:00"
        )


def format_time(value: Any, fmt: str = "medium", locale: str | None = None) -> str:
    """Format a time per *locale*."""
    target = _coerce_time(value)
    if target is None:
        return "" if value is None else str(value)
    try:
        from babel.dates import format_time as _babel_format_time  # type: ignore[import-not-found]
    except ImportError:
        if isinstance(target, datetime):
            return target.time().isoformat(timespec="seconds")
        return target.isoformat(timespec="seconds")
    locale_code = _to_babel_locale(locale or get_current_locale())
    try:
        return _babel_format_time(target, format=fmt, locale=locale_code)
    except Exception as exc:
        logger.debug("format_time failed for locale=%s fmt=%s: %s", locale_code, fmt, exc)
        if isinstance(target, datetime):
            return target.time().isoformat(timespec="seconds")
        return target.isoformat(timespec="seconds")


def format_number(value: Any, locale: str | None = None) -> str:
    """Format an integer or float with locale-aware thousands separator
    + decimal point (e.g. ``1,234.5`` in ``en_US`` vs ``1.234,5`` in
    ``de_DE``)."""
    target = _coerce_decimal(value)
    if target is None:
        return "" if value is None else str(value)
    try:
        from babel.numbers import format_decimal  # type: ignore[import-not-found]
    except ImportError:
        # Fallback: locale-independent thousands separator only
        if isinstance(target, int):
            return f"{target:,}"
        if isinstance(target, float):
            return f"{target:,.6f}".rstrip("0").rstrip(".") if "." in f"{target}" else f"{target:,}"
        return str(target)
    locale_code = _to_babel_locale(locale or get_current_locale())
    try:
        return format_decimal(target, locale=locale_code)
    except Exception as exc:
        logger.debug("format_number failed for locale=%s: %s", locale_code, exc)
        return str(target)


def format_decimal(value: Any, fmt: str | None = None, locale: str | None = None) -> str:
    """Format a decimal with an explicit pattern (e.g. ``"#,##0.00"``).

    Without a pattern, equivalent to :func:`format_number`. With a pattern,
    callers control digit grouping + precision while still getting
    locale-correct separators.
    """
    target = _coerce_decimal(value)
    if target is None:
        return "" if value is None else str(value)
    try:
        from babel.numbers import (
            format_decimal as _babel_format_decimal,  # type: ignore[import-not-found]
        )
    except ImportError:
        return format_number(value, locale=locale)
    locale_code = _to_babel_locale(locale or get_current_locale())
    try:
        if fmt is None:
            return _babel_format_decimal(target, locale=locale_code)
        return _babel_format_decimal(target, format=fmt, locale=locale_code)
    except Exception as exc:
        logger.debug("format_decimal failed for locale=%s fmt=%s: %s", locale_code, fmt, exc)
        return str(target)


def format_currency(value: Any, currency: str = "USD", locale: str | None = None) -> str:
    """Format an amount as currency per *locale*.

    The same value+currency pair renders differently per locale —
    e.g. ``1234.5`` + ``"USD"`` is ``$1,234.50`` in ``en_US`` and
    ``1.234,50 $`` in ``de_DE``. Without Babel: falls back to a
    minimal locale-independent ``USD 1,234.50``-style string.
    """
    target = _coerce_decimal(value)
    if target is None:
        return "" if value is None else str(value)
    try:
        from babel.numbers import (  # type: ignore[import-not-found]
            format_currency as _babel_format_currency,
        )
    except ImportError:
        if isinstance(target, int):
            return f"{currency} {target:,}"
        if isinstance(target, float):
            return f"{currency} {target:,.2f}"
        return f"{currency} {target}"
    locale_code = _to_babel_locale(locale or get_current_locale())
    try:
        return _babel_format_currency(target, currency, locale=locale_code)
    except Exception as exc:
        logger.debug(
            "format_currency failed for locale=%s currency=%s: %s",
            locale_code,
            currency,
            exc,
        )
        if isinstance(target, (int, float)):
            return f"{currency} {target}"
        return str(target)


__all__ = [
    "format_currency",
    "format_date",
    "format_datetime",
    "format_decimal",
    "format_number",
    "format_time",
]
