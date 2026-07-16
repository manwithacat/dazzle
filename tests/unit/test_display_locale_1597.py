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
