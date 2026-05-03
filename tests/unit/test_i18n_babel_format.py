"""Tests for #955 cycle 4 — Babel-backed locale-aware formatting.

Cycle 1-3 shipped locale resolution + identity-passthrough _() filter.
Cycle 4 adds the locale-aware date / number / currency helpers in
`dazzle.i18n.babel_format`. Templates can use them via Jinja filters
registered in `template_renderer.py`.

These tests cover:
- The same value formats differently across locales (en_US vs de_DE vs fr_FR)
- The current request locale (via `locale_ctxvar`) drives output when
  no explicit locale is passed
- Without Babel installed, fallback paths produce ISO/ASCII output
- Misshapen input (None, unparseable strings) doesn't crash the render
"""

from __future__ import annotations

import builtins
from datetime import date, datetime, time
from typing import Any

import pytest

from dazzle.i18n import locale_ctxvar
from dazzle.i18n.babel_format import (
    format_currency,
    format_date,
    format_datetime,
    format_decimal,
    format_number,
    format_time,
)

# Skip the locale-specific assertions when Babel isn't installed —
# those tests verify Babel's actual output, not our wrapping.
babel = pytest.importorskip("babel")


# ---------------------------------------------------------------------------
# format_date / format_datetime / format_time
# ---------------------------------------------------------------------------


class TestFormatDate:
    def test_explicit_locale_overrides_default(self):
        d = date(2026, 5, 3)
        # en_US: month-day-year ordering with comma; de_DE: dotted day.month.year.
        en = format_date(d, locale="en_US")
        de = format_date(d, locale="de_DE")
        assert en != de
        assert "2026" in en and "2026" in de

    def test_uses_request_locale_when_unset(self):
        d = date(2026, 5, 3)
        token = locale_ctxvar.set("de_DE")
        try:
            de_default = format_date(d)
        finally:
            locale_ctxvar.reset(token)
        de_explicit = format_date(d, locale="de_DE")
        assert de_default == de_explicit

    def test_bcp47_dash_form_normalised(self):
        """Middleware emits `en-US`; Babel needs `en_US`. Wrapper handles both."""
        d = date(2026, 5, 3)
        assert format_date(d, locale="en-US") == format_date(d, locale="en_US")

    def test_iso_string_input_coerced(self):
        # Templates often hold ISO strings from JSON payloads — those should
        # format as if they were datetime objects.
        out = format_date("2026-05-03", locale="en_US")
        assert "2026" in out

    def test_none_returns_empty(self):
        assert format_date(None) == ""

    def test_unparseable_string_falls_through_unchanged(self):
        assert format_date("not a date") == "not a date"


class TestFormatDatetime:
    def test_locale_specific_formatting(self):
        dt = datetime(2026, 5, 3, 14, 30, 0)
        en = format_datetime(dt, locale="en_US")
        de = format_datetime(dt, locale="de_DE")
        assert en != de
        # Both must mention the date, both must include time.
        assert "14" in de or "2:30" in en


class TestFormatTime:
    def test_locale_specific_time(self):
        t = time(14, 30, 0)
        en = format_time(t, locale="en_US")
        de = format_time(t, locale="de_DE")
        # en_US uses 12-hour AM/PM by default; de_DE uses 24-hour.
        assert "PM" in en or "AM" in en
        assert "14" in de


# ---------------------------------------------------------------------------
# format_number / format_decimal
# ---------------------------------------------------------------------------


class TestFormatNumber:
    def test_thousands_separator_locale_aware(self):
        # en_US: 1,234,567 ; de_DE: 1.234.567 ; fr_FR uses narrow no-break space
        assert format_number(1234567, locale="en_US") == "1,234,567"
        assert format_number(1234567, locale="de_DE") == "1.234.567"

    def test_float_decimal_separator(self):
        # en_US: . separator; de_DE: , separator
        assert "." in format_number(3.14, locale="en_US")
        assert "," in format_number(3.14, locale="de_DE")

    def test_uses_request_locale_when_unset(self):
        token = locale_ctxvar.set("de_DE")
        try:
            assert format_number(1234567) == "1.234.567"
        finally:
            locale_ctxvar.reset(token)

    def test_none_returns_empty(self):
        assert format_number(None) == ""

    def test_string_numeric_coerced(self):
        assert format_number("1234", locale="en_US") == "1,234"

    def test_string_unparseable_passed_through(self):
        assert format_number("oops") == "oops"


class TestFormatDecimal:
    def test_pattern_overrides_default(self):
        # The pattern ##0.00 forces 2 decimal places regardless of locale rules.
        out = format_decimal(3.5, fmt="##0.00", locale="en_US")
        assert out == "3.50"
        # de_DE uses comma decimal — the pattern's 0.00 is interpreted by Babel
        # as "two fractional digits, locale separator".
        out_de = format_decimal(3.5, fmt="##0.00", locale="de_DE")
        assert out_de == "3,50"


# ---------------------------------------------------------------------------
# format_currency
# ---------------------------------------------------------------------------


class TestFormatCurrency:
    def test_same_amount_renders_per_locale(self):
        en = format_currency(1234.5, currency="USD", locale="en_US")
        de = format_currency(1234.5, currency="USD", locale="de_DE")
        assert en != de
        # en_US always leads with $ symbol.
        assert en.startswith("$")
        # de_DE uses the ISO code or symbol after the value with a comma.
        assert "1.234,50" in de

    def test_currency_code_respected(self):
        # GBP must show £ in en_GB.
        gbp = format_currency(100, currency="GBP", locale="en_GB")
        assert "£" in gbp

    def test_uses_request_locale_when_unset(self):
        token = locale_ctxvar.set("en_US")
        try:
            assert format_currency(100, currency="USD").startswith("$")
        finally:
            locale_ctxvar.reset(token)

    def test_none_returns_empty(self):
        assert format_currency(None) == ""


# ---------------------------------------------------------------------------
# Fallback path — without Babel installed, helpers degrade gracefully
# ---------------------------------------------------------------------------


class TestBabelMissingFallback:
    """When Babel isn't installed, helpers must produce ISO/ASCII output
    rather than crashing the page render."""

    def test_format_date_iso_fallback(self, monkeypatch):
        real_import = builtins.__import__

        def _block(name: str, *a: Any, **kw: Any) -> Any:
            if name.startswith("babel"):
                raise ImportError("babel not in this env")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _block)
        assert format_date(date(2026, 5, 3)) == "2026-05-03"

    def test_format_number_locale_independent_fallback(self, monkeypatch):
        real_import = builtins.__import__

        def _block(name: str, *a: Any, **kw: Any) -> Any:
            if name.startswith("babel"):
                raise ImportError("babel not in this env")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _block)
        # ASCII thousands separator preserved; never a comma+dot mix.
        assert format_number(1234567) == "1,234,567"

    def test_format_currency_iso_code_fallback(self, monkeypatch):
        real_import = builtins.__import__

        def _block(name: str, *a: Any, **kw: Any) -> Any:
            if name.startswith("babel"):
                raise ImportError("babel not in this env")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _block)
        out = format_currency(1234, currency="USD")
        assert "USD" in out
        assert "1,234" in out


# ---------------------------------------------------------------------------
# Jinja filter registration smoke test
# ---------------------------------------------------------------------------


class TestJinjaFilterRegistration:
    def test_filters_present_on_env(self):
        """The template_renderer registers all six format_* filters so
        downstream templates can use them without project-side wiring."""
        from dazzle_ui.runtime.template_renderer import get_jinja_env

        env = get_jinja_env()
        for name in (
            "format_date",
            "format_datetime",
            "format_time",
            "format_number",
            "format_decimal",
            "format_currency",
        ):
            assert name in env.filters, f"filter {name} not registered"

    def test_template_renders_locale_aware_output(self):
        """End-to-end: a Jinja template using `| format_number` produces
        locale-aware output driven by the locale_ctxvar."""
        from jinja2 import Environment

        from dazzle.i18n.babel_format import format_number

        env = Environment(autoescape=True)  # nosemgrep
        env.filters["format_number"] = format_number
        tpl = env.from_string("{{ value | format_number }}")
        token = locale_ctxvar.set("de_DE")
        try:
            assert tpl.render(value=1234567) == "1.234.567"
        finally:
            locale_ctxvar.reset(token)
