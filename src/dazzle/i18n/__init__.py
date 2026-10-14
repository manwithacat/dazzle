"""Display-locale profile for date/number/currency presentation (#1597).

The package carries one live concern: the per-request
:class:`DisplayLocaleProfile` that ``LocaleMiddleware`` binds from the
app's ``locale.*`` params (and the tenant's per-tenant config), read by
every renderer that formats a date, datetime or currency.

String translation (the message catalogue, ``.po``/``.mo`` loading,
Babel format helpers and the ``dazzle i18n`` CLI) was retired in flense
ship AB (ADR-0057) because no consumer shipped a catalogue and no
renderer called it; the parked design and its restore commit are in
``docs/decisions/DD-012-string-translation-catalogue.md``.
"""

from __future__ import annotations

from dazzle.i18n.display_locale import (
    PRODUCT_DEFAULT_LOCALE,
    PRODUCT_DEFAULT_PROFILE,
    DisplayLocaleProfile,
    as_calendar_date,
    bind_display_locale_for_request,
    calendar_today,
    get_display_locale,
    profile_from_param_resolver,
    reset_display_locale,
    resolve_display_locale,
    set_display_locale,
)

__all__ = [
    "DisplayLocaleProfile",
    "PRODUCT_DEFAULT_LOCALE",
    "PRODUCT_DEFAULT_PROFILE",
    "as_calendar_date",
    "bind_display_locale_for_request",
    "calendar_today",
    "get_display_locale",
    "profile_from_param_resolver",
    "reset_display_locale",
    "resolve_display_locale",
    "set_display_locale",
]
