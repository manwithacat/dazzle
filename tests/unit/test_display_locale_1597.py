"""#1597 DisplayLocaleProfile — product en-GB default + tenant param resolve."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from dazzle.i18n.display_locale import (
    PRODUCT_DEFAULT_PROFILE,
    DisplayLocaleProfile,
    resolve_display_locale,
)
from dazzle.render.fragment.format_cell import ResolvedFormat, format_cell

pytestmark = pytest.mark.gate


def test_product_default_is_en_gb_london_gbp() -> None:
    p = PRODUCT_DEFAULT_PROFILE
    assert p.locale == "en-GB"
    assert p.timezone == "Europe/London"
    assert p.currency_default == "GBP"
    assert p.date_format == "D MMM YYYY"
    assert p.week_start == 0  # Monday


def test_resolve_from_param_getter_cyfuture_shape() -> None:
    params = {
        "locale.timezone": "Europe/London",
        "locale.date_format": "DD/MM/YYYY",
    }
    p = resolve_display_locale(param_getter=params.get)
    assert p.timezone == "Europe/London"
    assert p.date_format == "DD/MM/YYYY"
    assert p.format_date_value(date(2026, 7, 16)) == "16/07/2026"


def test_date_never_tz_shifts() -> None:
    """Calendar dates must not move with timezone (filing deadlines)."""
    p = DisplayLocaleProfile(timezone="America/New_York", date_format="D MMM YYYY")
    # Pure date
    assert p.format_date_value(date(2026, 1, 31)) == "31 Jan 2026"
    # datetime treated as date-only path via format_date_value
    assert p.format_date_value(datetime(2026, 1, 31, 23, 0, tzinfo=UTC)) == "31 Jan 2026"


def test_datetime_displays_in_tenant_tz() -> None:
    p = DisplayLocaleProfile(timezone="Europe/London", date_format="D MMM YYYY")
    # 2026-07-16 00:30 UTC → 01:30 BST in London
    utc = datetime(2026, 7, 16, 0, 30, tzinfo=UTC)
    out = p.format_datetime_value(utc)
    assert "16" in out and "Jul" in out and "2026" in out
    assert "01:30" in out


def test_format_cell_uses_profile() -> None:
    us = DisplayLocaleProfile(locale="en-US", date_format="MM/DD/YYYY", timezone="UTC")
    out = format_cell(date(2026, 7, 16), "date", profile=us)
    assert out == "07/16/2026"
    gb = DisplayLocaleProfile(date_format="DD/MM/YYYY")
    assert format_cell(date(2026, 7, 16), "date", profile=gb) == "16/07/2026"


def test_format_cell_default_profile_friendly_uk() -> None:
    """No profile arg → product default D MMM YYYY (existing UK-friendly cells)."""
    out = format_cell(datetime(2026, 6, 24, 9, 30), "datetime")
    assert "2026" in out and "Jun" in out and "T" not in out
    assert "24" in out


def test_relative_uses_tenant_today() -> None:
    # Force profile with known "today" by using relative override against fixed dates
    p = DisplayLocaleProfile(timezone="UTC", date_format="D MMM YYYY")
    today = p.today()
    out = format_cell(today, "date", override=ResolvedFormat("relative"), profile=p)
    assert out == "today"


def test_money_code_not_overridden_by_profile_currency() -> None:
    """money(GBP) stays GBP even if profile.currency_default is USD."""
    p = DisplayLocaleProfile(currency_default="USD")
    # minor units: 12345 → £123.45 when currency_code=GBP
    assert format_cell(12345, "currency", currency_code="GBP", profile=p) == "£123.45"


def test_expression_today_and_days_until_use_tenant_calendar() -> None:
    """#1597 C: attention/days_until share DisplayLocaleProfile.today()."""
    from dazzle.core.expression_lang.evaluator import evaluate
    from dazzle.core.expression_lang.parser import parse_expr
    from dazzle.i18n.display_locale import (
        calendar_today,
        reset_display_locale,
        set_display_locale,
    )

    # Fixed profile so wall clock is stable across host TZ
    p = DisplayLocaleProfile(timezone="UTC", date_format="D MMM YYYY")
    token = set_display_locale(p)
    try:
        from datetime import timedelta

        assert evaluate(parse_expr("today()"), {}) == calendar_today()
        due = calendar_today() + timedelta(days=5)
        assert evaluate(parse_expr("days_until(due)"), {"due": due}) == 5
        # datetime target: UTC noon so date is unambiguous under UTC profile
        dt_due = datetime(due.year, due.month, due.day, 12, 0, tzinfo=UTC)
        assert evaluate(parse_expr("days_until(due)"), {"due": dt_due}) == 5
    finally:
        reset_display_locale(token)


def test_format_letter_datetime_tenant_tz() -> None:
    """#1597 D: letter/PDF signed-at uses tenant TZ, not hard-coded UTC label."""
    p = DisplayLocaleProfile(timezone="Europe/London", date_format="D MMM YYYY")
    # 2026-07-16 00:30 UTC → 01:30 BST
    utc = datetime(2026, 7, 16, 0, 30, tzinfo=UTC)
    assert p.format_long_date(utc) == "16 July 2026"
    assert p.format_letter_datetime(utc) == "16 July 2026 at 01:30"


def test_date_filter_uses_display_locale() -> None:
    """#1597 D: Jinja/legacy _date_filter follows profile (not fixed %d %b %Y)."""
    from dazzle.i18n.display_locale import reset_display_locale, set_display_locale
    from dazzle.render.filters import _date_filter

    us = DisplayLocaleProfile(locale="en-US", date_format="MM/DD/YYYY", timezone="UTC")
    token = set_display_locale(us)
    try:
        assert _date_filter(date(2026, 7, 16)) == "07/16/2026"
        # Explicit fmt still wins
        assert _date_filter(date(2026, 7, 16), fmt="%Y-%m-%d") == "2026-07-16"
    finally:
        reset_display_locale(token)


def test_letter_date_strings_london_bst() -> None:
    """#1597 D: signing letter dates convert UTC clock → tenant display."""
    from dazzle.i18n.display_locale import reset_display_locale, set_display_locale
    from dazzle.signing.service import _letter_date_strings

    p = DisplayLocaleProfile(timezone="Europe/London", date_format="D MMM YYYY")
    token = set_display_locale(p)
    try:
        header, signed = _letter_date_strings(datetime(2026, 7, 16, 0, 30, tzinfo=UTC))
        assert header == "16 July 2026"
        assert signed == "16 July 2026 at 01:30"
        assert "UTC" not in signed
    finally:
        reset_display_locale(token)
