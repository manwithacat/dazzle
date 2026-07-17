"""Display locale profile for date/number/currency presentation (#1597).

Product default is **en-GB** + Europe/London + GBP (CyFuture / UK SaaS).
Tenant overrides come from DSL params (`locale.timezone`, `locale.date_format`)
or explicit kwargs — never from browser Accept-Language (that's gettext only).

Resolution order for a cell:

    explicit field ``format:`` → DisplayLocaleProfile → defensive ISO humanise

Storage remains UTC / calendar dates; this module is presentation only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

# Product / system default for vertical SaaS (CyFuture dogfood bar).
PRODUCT_DEFAULT_LOCALE = "en-GB"
PRODUCT_DEFAULT_TIMEZONE = "Europe/London"
PRODUCT_DEFAULT_DATE_FORMAT = "D MMM YYYY"
PRODUCT_DEFAULT_CURRENCY = "GBP"

# CyFuture / DSL enum tokens → (date strftime, datetime strftime, babel locale hint)
_DATE_FORMAT_TABLE: dict[str, tuple[str, str, str]] = {
    "DD/MM/YYYY": ("%d/%m/%Y", "%d/%m/%Y %H:%M", "en-GB"),
    "MM/DD/YYYY": ("%m/%d/%Y", "%m/%d/%Y %H:%M", "en-US"),
    "YYYY-MM-DD": ("%Y-%m-%d", "%Y-%m-%d %H:%M", "en"),
    "D MMM YYYY": ("%d %b %Y", "%d %b %Y %H:%M", "en-GB"),
    # Common aliases
    "DD MMM YYYY": ("%d %b %Y", "%d %b %Y %H:%M", "en-GB"),
    "D/M/YYYY": ("%d/%m/%Y", "%d/%m/%Y %H:%M", "en-GB"),
}


@dataclass(frozen=True, slots=True)
class DisplayLocaleProfile:
    """Presentation profile for lists, detail, related, and exports.

    Attributes:
        locale: BCP-47 tag (en-GB). Drives Babel when installed; not browser locale.
        timezone: IANA zone for **datetime** display only (never shifts pure dates).
        date_format: DSL token (``D MMM YYYY``, ``DD/MM/YYYY``, …).
        currency_default: Fallback currency code when field has none (never converts money).
        week_start: 0=Monday … 6=Sunday (calendars / relative "this week").
    """

    locale: str = PRODUCT_DEFAULT_LOCALE
    timezone: str = PRODUCT_DEFAULT_TIMEZONE
    date_format: str = PRODUCT_DEFAULT_DATE_FORMAT
    currency_default: str = PRODUCT_DEFAULT_CURRENCY
    week_start: int = 0  # Monday — en-GB

    @property
    def date_strftime(self) -> str:
        return _DATE_FORMAT_TABLE.get(self.date_format, _DATE_FORMAT_TABLE["D MMM YYYY"])[0]

    @property
    def datetime_strftime(self) -> str:
        return _DATE_FORMAT_TABLE.get(self.date_format, _DATE_FORMAT_TABLE["D MMM YYYY"])[1]

    def format_date_value(self, value: date | datetime) -> str:
        """Format a calendar date (no timezone shift)."""
        d = value.date() if isinstance(value, datetime) else value
        # %-d is non-portable; build day manually for "D MMM YYYY" friendliness
        fmt = self.date_strftime
        if "%d" in fmt and self.date_format in ("D MMM YYYY", "DD MMM YYYY"):
            # Friendly: "16 Jul 2026" (no leading zero on day)
            return f"{d.day} {d.strftime('%b %Y')}"
        return d.strftime(fmt)

    def format_long_date(self, value: date | datetime) -> str:
        """Long UK-style date for letters/PDF (e.g. ``16 July 2026``).

        Calendar day only — no TZ shift (#1597 D). Same profile as HTML cells.
        """
        d = value.date() if isinstance(value, datetime) else value
        return f"{d.day} {d.strftime('%B %Y')}"

    def format_letter_datetime(self, value: datetime) -> str:
        """Long letter form with time in tenant TZ (e.g. ``16 July 2026 at 01:30``).

        Used by native PDF signing and other export/messaging paths (#1597 D).
        Naive datetimes are treated as UTC (storage convention).
        """
        local = self.to_display_datetime(value)
        return f"{local.day} {local.strftime('%B %Y')} at {local.strftime('%H:%M')}"

    def format_datetime_value(self, value: datetime | date) -> str:
        """Format a datetime in tenant TZ; pure dates stay calendar-only."""
        if isinstance(value, date) and not isinstance(value, datetime):
            return self.format_date_value(value)
        local = self.to_display_datetime(value)
        fmt = self.datetime_strftime
        if self.date_format in ("D MMM YYYY", "DD MMM YYYY"):
            return f"{local.day} {local.strftime('%b %Y %H:%M')}"
        return local.strftime(fmt)

    def to_display_datetime(self, value: datetime) -> datetime:
        """Convert stored datetime to tenant timezone for display.

        Naive datetimes are treated as **UTC** (framework storage convention).
        Pure ``date`` must not be passed here for TZ conversion.
        """
        if not isinstance(value, datetime):
            return value
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(self.timezone)
        except Exception:
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(tz).replace(tzinfo=None)

    def today(self) -> date:
        """Tenant-timezone calendar day (for relative / overdue)."""
        try:
            from zoneinfo import ZoneInfo

            return datetime.now(ZoneInfo(self.timezone)).date()
        except Exception:
            return date.today()


PRODUCT_DEFAULT_PROFILE = DisplayLocaleProfile()

_display_locale_ctx: ContextVar[DisplayLocaleProfile] = ContextVar(
    "dz_display_locale", default=PRODUCT_DEFAULT_PROFILE
)


def get_display_locale() -> DisplayLocaleProfile:
    """Return the display profile for the current request (or product default)."""
    return _display_locale_ctx.get()


def calendar_today() -> date:
    """Tenant-timezone calendar day for expressions / attention / relative.

    Prefer this over ``date.today()`` so overdue rules, ``days_until``, and
    ``format: relative`` share one definition of "today" (#1597 C).
    """
    return get_display_locale().today()


def as_calendar_date(value: Any) -> date | None:
    """Coerce a value to a calendar date for day-delta expressions.

    Pure ``date`` values are returned unchanged (no TZ shift). ``datetime``
    values are converted to the profile timezone, then the wall date is taken.
    ISO strings are parsed best-effort.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return get_display_locale().to_display_datetime(value).date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip().replace("Z", "+00:00")
        try:
            if "T" in raw or " " in raw:
                return as_calendar_date(datetime.fromisoformat(raw))
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    return None


def set_display_locale(profile: DisplayLocaleProfile) -> Token[DisplayLocaleProfile]:
    """Bind *profile* for the current context; return a reset token."""
    return _display_locale_ctx.set(profile)


def reset_display_locale(token: Token[DisplayLocaleProfile]) -> None:
    _display_locale_ctx.reset(token)


def _pick_str(raw: Any, fallback: str) -> str:
    if raw is None:
        return fallback
    s = str(raw).strip()
    return s if s else fallback


def _lookup_sources(
    keys: tuple[str, ...],
    *,
    param_getter: Callable[[str], Any] | None,
    cfg: Mapping[str, Any],
) -> Any:
    """First non-empty value from param_getter / tenant_config for *keys*."""
    for key in keys:
        if param_getter is not None:
            try:
                val = param_getter(key)
            except Exception:
                val = None
            if val is not None and val != "":
                return val
        if key in cfg and cfg[key] not in (None, ""):
            return cfg[key]
        bare = key.split(".", 1)[-1]
        if bare in cfg and cfg[bare] not in (None, ""):
            return cfg[bare]
    return None


def resolve_display_locale(
    *,
    locale: str | None = None,
    timezone: str | None = None,
    date_format: str | None = None,
    currency_default: str | None = None,
    week_start: int | None = None,
    param_getter: Callable[[str], Any] | None = None,
    tenant_config: Mapping[str, Any] | None = None,
) -> DisplayLocaleProfile:
    """Build a profile from explicit args, tenant params, then product defaults.

    *param_getter* should resolve DSL param keys (e.g. ``locale.timezone``).
    *tenant_config* may carry the same keys or a nested ``locale`` dict.
    Browser / Accept-Language is **not** consulted (app shell regulatory rule).
    """
    cfg: dict[str, Any] = dict(tenant_config or {})
    nested = cfg.get("locale")
    if isinstance(nested, dict):
        cfg = {**nested, **cfg}

    loc = _pick_str(
        locale
        if locale is not None
        else _lookup_sources(
            ("locale.language", "locale.locale", "locale"),
            param_getter=param_getter,
            cfg=cfg,
        ),
        PRODUCT_DEFAULT_LOCALE,
    ).replace("_", "-")
    tz = _pick_str(
        timezone
        if timezone is not None
        else _lookup_sources(("locale.timezone", "timezone"), param_getter=param_getter, cfg=cfg),
        PRODUCT_DEFAULT_TIMEZONE,
    )
    df = _pick_str(
        date_format
        if date_format is not None
        else _lookup_sources(
            ("locale.date_format", "date_format"), param_getter=param_getter, cfg=cfg
        ),
        PRODUCT_DEFAULT_DATE_FORMAT,
    )
    if df not in _DATE_FORMAT_TABLE:
        df = PRODUCT_DEFAULT_DATE_FORMAT
    if loc.lower() == "en":
        loc = _DATE_FORMAT_TABLE[df][2]
    cur = _pick_str(
        currency_default
        if currency_default is not None
        else _lookup_sources(
            ("locale.currency_default", "currency_default"),
            param_getter=param_getter,
            cfg=cfg,
        ),
        PRODUCT_DEFAULT_CURRENCY,
    )
    if week_start is None:
        raw_ws = _lookup_sources(
            ("locale.week_start", "week_start"), param_getter=param_getter, cfg=cfg
        )
        try:
            week_start = int(raw_ws) if raw_ws is not None else 0
        except (TypeError, ValueError):
            week_start = 0
    return DisplayLocaleProfile(
        locale=loc,
        timezone=tz,
        date_format=df,
        currency_default=cur.upper() if cur else PRODUCT_DEFAULT_CURRENCY,
        week_start=int(week_start) % 7,
    )


def profile_from_param_resolver(
    resolver: Any,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> DisplayLocaleProfile:
    """Resolve profile via :class:`~dazzle.http.runtime.param_store.ParamResolver`."""

    def getter(key: str) -> Any:
        if resolver is None:
            return None
        try:
            value, _source = resolver.resolve(key, tenant_id=tenant_id, user_id=user_id)
            return value
        except KeyError:
            return None

    return resolve_display_locale(param_getter=getter)


def bind_display_locale_for_request(
    request: Any,
    *,
    param_resolver: Any = None,
    tenant_id: str | None = None,
) -> Token[DisplayLocaleProfile]:
    """Resolve + bind profile on *request* and the ContextVar.

    Call from request middleware after tenant is known. Safe with no resolver
    (binds product default).
    """
    tid = tenant_id
    if tid is None:
        tid = getattr(getattr(request, "state", None), "tenant_id", None)
    profile = profile_from_param_resolver(param_resolver, tenant_id=tid)
    if hasattr(request, "state"):
        request.state.display_locale = profile
    return set_display_locale(profile)
