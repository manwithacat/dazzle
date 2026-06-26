"""Pure value-formatting helpers shared by render, back, and ui layers.

These were Jinja2 filters originally (post-#1044 they're imported directly
by the typed renderers). They have no FastAPI / Jinja / RuntimeServices
dependencies — pure functions over IR/data values returning strings or
markup — so they live in `dazzle.render` to break the back↔ui import
cycle (issue #1090 / parent #1086).
"""

from __future__ import annotations

import re as _re
from datetime import date, datetime
from typing import Any

from markupsafe import Markup

from dazzle.core.ir.money import get_currency_scale


def _currency_filter(value: Any, currency: str = "GBP", minor: bool = True) -> str:
    """Format a number as currency.

    Args:
        value: The numeric value.
        currency: ISO 4217 currency code (default GBP).
        minor: If True, value is in minor units (pence/cents) and will be
            divided by the correct ISO 4217 scale before display.
            Defaults to True to match the ``_minor`` column convention.
    """
    if value is None:
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)

    scale = get_currency_scale(currency)
    if minor:
        amount = amount / (10**scale)

    symbols: dict[str, str] = {
        "GBP": "£",
        "USD": "$",
        "EUR": "€",
        "JPY": "¥",
        "CHF": "CHF ",
        "AUD": "A$",
        "CAD": "C$",
    }
    symbol = symbols.get(currency, currency + " ")
    return f"{symbol}{amount:,.{scale}f}"


def _date_filter(value: Any, fmt: str = "%d %b %Y") -> str:
    """Format a date or datetime."""
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return str(value)
    if isinstance(value, (date, datetime)):
        return value.strftime(fmt)
    return str(value)


# Canonical semantic tones for status badges. Cycle 238 defined the
# tones; cycle 321 removed the deprecated `badge_class` filter (0
# template consumers) leaving only `badge_tone`.
_STATUS_TONE_MAP: dict[str, str] = {
    # Success — things that reached a positive terminal state
    "active": "success",
    "done": "success",
    "completed": "success",
    "approved": "success",
    "resolved": "success",
    "closed": "success",
    "published": "success",
    "passed": "success",
    # Info — things actively in motion / neutral-positive
    "in_progress": "info",
    "open": "info",
    "running": "info",
    "started": "info",
    "processing": "info",
    # Warning — attention needed / awaiting action
    "review": "warning",
    "pending": "warning",
    "on_hold": "warning",
    "waiting": "warning",
    "blocked": "warning",
    "escalated": "warning",
    # Destructive — failure / negative terminal state, or top-urgency
    "inactive": "destructive",
    "overdue": "destructive",
    "cancelled": "destructive",
    "rejected": "destructive",
    "failed": "destructive",
    "critical": "destructive",
    "error": "destructive",
    "urgent": "destructive",
    # Priority / severity "high" — warning (below destructive)
    "high": "warning",
    "major": "warning",
    # Priority / severity "medium" — info
    "medium": "info",
    # Neutral fallbacks for unstarted / draft / low-priority states
    "todo": "neutral",
    "draft": "neutral",
    "new": "neutral",
    "backlog": "neutral",
    "low": "neutral",
    "minor": "neutral",
}


def _metric_number_filter(value: Any) -> str:
    """Format an aggregate metric value for display in a metric tile."""
    if value is None:
        return "0"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if abs(value) >= 1:
            return f"{value:,.1f}"
        # Sub-1.0 floats (ratios, averages like avg(confidence)) round to 2dp
        # — matching the #1470 `format_cell` cell layer — rather than leaking
        # full precision (#1479: avg_confidence -> 0.8850441412520064).
        return f"{value:.2f}"
    return str(value)


def _badge_tone_filter(value: Any) -> str:
    """Map a status value to a semantic tone name.

    Returns one of: ``neutral`` | ``success`` | ``warning`` | ``info`` |
    ``destructive``.
    """
    if value is None:
        return "neutral"
    status = str(value).lower().replace(" ", "_")
    return _STATUS_TONE_MAP.get(status, "neutral")


def _bool_icon_filter(value: Any) -> Markup:
    """Render a boolean as a check or cross icon."""
    if value:
        return Markup('<span class="text-[hsl(var(--success))]">&#10003;</span>')
    return Markup('<span class="text-[hsl(var(--muted-foreground)/0.3)]">&#10005;</span>')


def _timeago_filter(value: Any) -> str:
    """Format a datetime as relative time (e.g. '2 hours ago')."""
    if value is None:
        return ""
    now = datetime.now()
    dt: datetime | None = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if dt is None:
        return str(value)
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds} seconds ago" if seconds != 1 else "1 second ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minutes ago" if minutes != 1 else "1 minute ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hours ago" if hours != 1 else "1 hour ago"
    days = hours // 24
    if days < 30:
        return f"{days} days ago" if days != 1 else "1 day ago"
    months = days // 30
    if months < 12:
        return f"{months} months ago" if months != 1 else "1 month ago"
    years = days // 365
    return f"{years} years ago" if years != 1 else "1 year ago"


def _slugify_filter(value: Any) -> str:
    """Slugify a string for use as an HTML id attribute."""
    if value is None:
        return ""
    text = str(value).lower().strip()
    text = _re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _basename_or_url_filter(value: Any) -> str:
    """Extract filename from a URL or path, or return the value as-is."""
    if value is None:
        return ""
    text = str(value)
    if "/" in text:
        return text.rsplit("/", 1)[-1].split("?")[0] or text
    return text


def _humanize_filter(value: Any) -> str:
    """Convert snake_case or slug values to human-readable Title Case."""
    if value is None:
        return ""
    text = str(value)
    return text.replace("_", " ").title()


def _ref_display_name(value: Any, fallback: str = "") -> str:
    """Extract a human-readable display name from a ref dict."""
    if not isinstance(value, dict):
        return str(value) if value else fallback
    _explicit = value.get("__display__")
    if _explicit:
        return str(_explicit)
    result = (
        value.get("name")
        or value.get("company_name")
        or (
            ((value.get("first_name", "") or "") + " " + (value.get("last_name", "") or "")).strip()
            or None
        )
        or (
            ((value.get("forename", "") or "") + " " + (value.get("surname", "") or "")).strip()
            or None
        )
        or value.get("title")
        or value.get("label")
        or value.get("email")
    )
    if result:
        return str(result)
    _skip = {"id", "created_at", "updated_at", "deleted_at"}
    for k, v in value.items():
        if k not in _skip and isinstance(v, str) and v and len(v) < 200:
            return v
    return str(value.get("id", fallback))


def _ref_display_filter(value: Any) -> str:
    """Filter form of ``_ref_display_name`` for legacy import sites."""
    return _ref_display_name(value)


def _resolve_fk_id_filter(value: Any) -> str:
    """Extract the id from a FK value that may be dict or scalar."""
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("id", "ID", "uuid", "value"):
            if key in value and value[key] is not None:
                return str(value[key])
        return ""
    return str(value)


def _truncate_filter(value: Any, length: int = 50) -> str:
    """Truncate text to a given length."""
    if value is None:
        return ""
    if isinstance(value, dict):
        text = _ref_display_name(value)
    else:
        text = str(value)
    if len(text) <= length:
        return text
    return text[:length] + "..."


def _gettext(message: str, **kwargs: Any) -> str:
    """gettext helper — translates against the per-request locale."""
    from dazzle.i18n import get_catalogue, get_current_locale

    locale = get_current_locale()
    translation = get_catalogue().lookup(locale, message) if locale else None
    out = translation if translation is not None else message
    if not kwargs:
        return out
    try:
        return out.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return out


def _pagination_pages(current: int, total: int, window: int = 2) -> list[int | None]:
    """Ellipsis-collapsed list of page numbers for pagination controls (#984)."""
    if total <= 0:
        return []
    if total == 1:
        return [1]

    explicit_count = 2 * window + 3
    if total <= explicit_count + 2:
        return list(range(1, total + 1))

    pages: list[int | None] = [1]
    win_start = max(2, current - window)
    win_end = min(total - 1, current + window)

    if win_start > 2:
        pages.append(None)
    pages.extend(range(win_start, win_end + 1))
    if win_end < total - 1:
        pages.append(None)
    pages.append(total)
    return pages
