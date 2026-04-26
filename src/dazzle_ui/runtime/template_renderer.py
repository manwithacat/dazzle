"""
Jinja2 template renderer for server-rendered DNR pages.

Sets up the Jinja2 environment with custom filters, globals, and
template loading from the templates/ directory.
"""

from __future__ import annotations

import threading
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PrefixLoader, select_autoescape
from markupsafe import Markup

if TYPE_CHECKING:
    from dazzle_ui.runtime.template_context import (
        PageContext,
        Site404Context,
        SiteAuthContext,
        SitePageContext,
    )

# Template directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


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

    from dazzle.core.ir.money import get_currency_scale

    scale = get_currency_scale(currency)
    if minor:
        amount = amount / (10**scale)

    symbols: dict[str, str] = {
        "GBP": "\u00a3",
        "USD": "$",
        "EUR": "\u20ac",
        "AUD": "A$",
        "CAD": "C$",
        "CHF": "CHF",
        "CNY": "\u00a5",
        "INR": "\u20b9",
        "NZD": "NZ$",
        "SGD": "S$",
        "HKD": "HK$",
        "SEK": "kr",
        "NOK": "kr",
        "DKK": "kr",
        "ZAR": "R",
        "MXN": "MX$",
        "BRL": "R$",
        "JPY": "\u00a5",
        "KRW": "\u20a9",
        "VND": "\u20ab",
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


# Canonical semantic tones for status badges. The macro at
# `templates/macros/status_badge.html` maps these to design-system tokens.
# Cycle 238 defined the tones; cycle 321 removed the deprecated
# `badge_class` filter (0 template consumers) leaving only `badge_tone`.
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
    """Format an aggregate metric value for display in a metric tile.

    Cycle 239 (UX-042 metrics-region contract).

    - Integers: rendered with locale-independent thousands separator
      (e.g. ``1234`` → ``"1,234"``, ``1500000`` → ``"1,500,000"``).
    - Floats: rendered to 1 decimal place with thousands separator
      when >= 1 (e.g. ``3.1415`` → ``"3.1"``), or the full value for
      sub-unit values (e.g. ``0.25`` → ``"0.25"``).
    - Strings: returned verbatim — the DSL author may have pre-formatted.
    - None / missing: rendered as ``"0"``.

    The macro at ``workspace/regions/metrics.html`` always calls this
    filter, so every metric tile across every Dazzle app renders with
    consistent number formatting, regardless of what shape the backend
    aggregate evaluator returned.
    """
    if value is None:
        return "0"
    if isinstance(value, bool):
        # bools are subclass of int — handle before int to avoid surprises
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if abs(value) >= 1:
            return f"{value:,.1f}"
        return f"{value}"
    return str(value)


def _badge_tone_filter(value: Any) -> str:
    """Map a status value to a semantic tone name.

    Returns one of: ``neutral`` | ``success`` | ``warning`` | ``info`` |
    ``destructive``. Used by the ``status_badge`` macro (see
    ``templates/macros/status_badge.html``) to pick the correct design-system
    token variant.
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
    """Format a datetime as relative time (e.g. '2 hours ago').

    Postgres ``TIMESTAMP WITH TIME ZONE`` columns return tz-aware
    datetimes via psycopg; mixing those with ``datetime.now()`` (naive)
    raised ``TypeError`` and 500'd region renders (#852). Strategy:
    keep both sides naive for the subtraction — convert any tz-aware
    input to local-naive so the comparison matches the existing
    convention that callers pass naive local values.
    """
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
            # Python <3.11 doesn't parse the trailing `Z` — normalise it
            # to the explicit UTC offset before fromisoformat.
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if dt is None:
        return str(value)
    if dt.tzinfo is not None:
        # Convert tz-aware inputs (DB columns) to local-naive so they can
        # subtract from naive `now` without raising. This is the smallest
        # fix that closes #852 and keeps every existing local-naive call
        # site working.
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
    import re

    if value is None:
        return ""
    text = str(value).lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _basename_or_url_filter(value: Any) -> str:
    """Extract filename from a URL or path, or return the value as-is."""
    if value is None:
        return ""
    text = str(value)
    # Try to extract filename from URL path
    if "/" in text:
        return text.rsplit("/", 1)[-1].split("?")[0] or text
    return text


def _humanize_filter(value: Any) -> str:
    """Convert snake_case or slug values to human-readable Title Case.

    E.g. ``in_progress`` → ``In Progress``, ``needs_review`` → ``Needs Review``.
    """
    if value is None:
        return ""
    text = str(value)
    return text.replace("_", " ").title()


def _ref_display_name(value: Any, fallback: str = "") -> str:
    """Extract a human-readable display name from a ref dict.

    Priority chain:
    0. Explicit display_field override (__display__ key, set by relation loader from entity DSL)
    1. Well-known fields: name, company_name, first+last, forename+surname, title, label, email
    2. First non-id string value (catches entity-specific fields like component_name, question_text)
    3. id (UUID fallback)

    This is the canonical ref display chain — used by the ref_display filter,
    truncate_text filter, and table_rows.html template.
    """
    if not isinstance(value, dict):
        return str(value) if value else fallback
    # Explicit display_field override from entity DSL (#555)
    _explicit = value.get("__display__")
    if _explicit:
        return str(_explicit)
    # Well-known fields
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
    # Fallback: first non-id, non-empty string value (#479)
    _skip = {"id", "created_at", "updated_at", "deleted_at"}
    for k, v in value.items():
        if k not in _skip and isinstance(v, str) and v and len(v) < 200:
            return v
    return str(value.get("id", fallback))


def _ref_display_filter(value: Any) -> str:
    """Jinja filter: extract display name from a ref value (dict or scalar)."""
    return _ref_display_name(value)


def _resolve_fk_id_filter(value: Any) -> str:
    """Jinja filter: extract the id from a FK value that may be dict or scalar.

    v0.61.7 (#861): when a region's ``action:`` points at a foreign entity,
    the row's FK column (e.g. ``student_profile``) is used to parameterise
    the detail URL. ``_inject_display_names`` may have expanded that column
    into ``{"id": "<uuid>", "display": "Alice"}`` — in that case templates
    rendering ``item[field] | string`` would emit the dict repr, producing
    a broken URL. This filter resolves both shapes:

        {"id": "abc"} | resolve_fk_id  → "abc"
        "abc"         | resolve_fk_id  → "abc"
        None          | resolve_fk_id  → ""
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        # Prefer explicit id; fall back to other identity keys.
        for key in ("id", "ID", "uuid", "value"):
            if key in value and value[key] is not None:
                return str(value[key])
        return ""
    return str(value)


def _truncate_filter(value: Any, length: int = 50) -> str:
    """Truncate text to a given length."""
    if value is None:
        return ""
    # Ref fields may arrive as dicts — extract a display name instead of repr
    if isinstance(value, dict):
        text = _ref_display_name(value)
    else:
        text = str(value)
    if len(text) <= length:
        return text
    return text[:length] + "..."


def create_jinja_env(project_templates_dir: Path | None = None) -> Environment:
    """Create and configure the Jinja2 environment.

    Args:
        project_templates_dir: Optional path to project-level templates.
            When provided, project templates take priority over framework
            templates.  Framework originals remain accessible via the
            ``dz://`` prefix (e.g. ``{% extends "dz://layouts/app_shell.html" %}``).
    """
    framework_loader = FileSystemLoader(str(TEMPLATES_DIR))

    if project_templates_dir and project_templates_dir.is_dir():
        project_loader = FileSystemLoader(str(project_templates_dir))
        # Project templates searched first, framework as fallback
        main_loader = ChoiceLoader([project_loader, framework_loader])
    else:
        main_loader = ChoiceLoader([framework_loader])

    # "dz://" prefix always resolves to framework templates, allowing
    # project overrides to extend the originals they replace:
    #   {% extends "dz://layouts/app_shell.html" %}
    loader = PrefixLoader({"dz": framework_loader}, delimiter="://")
    # Combine: unprefixed paths go through ChoiceLoader, "dz://" goes to framework
    combined = ChoiceLoader([loader, main_loader])

    env = Environment(
        loader=combined,
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Dazzle version + CDN toggle
    from dazzle import __version__ as _dz_version

    env.globals["_dazzle_version"] = _dz_version
    env.globals["_use_cdn"] = False  # local-first; opt-in via [ui] cdn = true

    # Theme variant — resolved per-request by ThemeVariantMiddleware
    # (src/dazzle_ui/runtime/theme.py). Templates call `{{
    # theme_variant() }}` in `<html data-theme="…">` so the correct
    # attribute renders on first paint and returning dark-mode users
    # don't see a flash-of-light. Falls back to "light" when called
    # outside a request context (e.g. unit-test rendering).
    from dazzle_ui.runtime.theme import get_theme_variant

    env.globals["theme_variant"] = get_theme_variant

    # Global: detect if compiled Tailwind CSS bundle exists
    static_dir = Path(__file__).parent / "static"
    bundled = (static_dir / "css" / "dazzle-bundle.css").exists()
    # Also check project static dir (sibling of project templates dir)
    if not bundled and project_templates_dir:
        project_static = project_templates_dir.parent / "static"
        bundled = (project_static / "css" / "dazzle-bundle.css").exists()
    env.globals["_tailwind_bundled"] = bundled

    # Asset fingerprinting manifest — content-hash cache busting (#711)
    from dazzle_ui.runtime.asset_fingerprint import build_asset_manifest, static_url_filter

    manifest_dirs = [static_dir]
    if project_templates_dir:
        project_static = project_templates_dir.parent / "static"
        if project_static.is_dir():
            manifest_dirs.insert(0, project_static)
    _asset_manifest = build_asset_manifest(*manifest_dirs)
    env.globals["_asset_manifest"] = _asset_manifest
    env.filters["static_url"] = lambda path: static_url_filter(path, _asset_manifest)

    # Custom filters
    env.filters["currency"] = _currency_filter
    env.filters["dateformat"] = _date_filter
    env.filters["badge_tone"] = _badge_tone_filter
    env.filters["metric_number"] = _metric_number_filter
    env.filters["bool_icon"] = _bool_icon_filter
    env.filters["truncate_text"] = _truncate_filter
    env.filters["timeago"] = _timeago_filter
    env.filters["slugify"] = _slugify_filter
    env.filters["basename_or_url"] = _basename_or_url_filter
    env.filters["ref_display"] = _ref_display_filter
    env.filters["resolve_fk_id"] = _resolve_fk_id_filter
    env.filters["humanize"] = _humanize_filter

    return env


# Module-level singleton (guarded by lock for thread safety)
_env: Environment | None = None
_env_lock = threading.Lock()


def get_jinja_env() -> Environment:
    """Get the shared Jinja2 environment (lazy singleton)."""
    global _env  # noqa: PLW0603
    if _env is not None:
        return _env
    with _env_lock:
        if _env is None:
            _env = create_jinja_env()
    return _env


def configure_project_templates(project_templates_dir: Path) -> None:
    """Reconfigure the Jinja2 environment with project-level template overrides.

    Call this during app startup to enable project templates that override
    framework defaults.  Framework templates remain accessible via ``dz://``.
    """
    global _env  # noqa: PLW0603
    with _env_lock:
        _env = create_jinja_env(project_templates_dir)


def add_theme_template_dirs(theme_template_dirs: list[Path]) -> None:
    """Prepend theme-template directories to the Jinja loader chain.

    Phase C Patch 2: when a theme ships templates at
    ``themes/<name>/templates/<path>.html``, those overrides win over
    project + framework templates. Pass the dirs in cascade order
    (root → leaf, so the leaf wins for same-name templates).

    Idempotent — safe to call multiple times during startup. Skips
    directories that don't exist on disk so opt-in themes (no
    ``templates/`` subdir) cost nothing.
    """
    global _env  # noqa: PLW0603
    if not theme_template_dirs:
        return
    valid = [d for d in theme_template_dirs if d.is_dir()]
    if not valid:
        return
    with _env_lock:
        if _env is None:
            _env = create_jinja_env()
        # Prepend a new ChoiceLoader-of-themes to the existing loader.
        # Theme templates win over project + framework. Within the
        # themes list, LATER directories win (because of how the
        # caller orders them: root → leaf). ChoiceLoader picks the
        # FIRST match, so we reverse to get leaf-first matching.
        theme_loader = ChoiceLoader([FileSystemLoader(str(d)) for d in reversed(valid)])
        # Defensive: env.loader is always set when the env is constructed
        # via create_jinja_env above; the cast satisfies mypy.
        existing = _env.loader
        if existing is None:
            existing = create_jinja_env().loader  # pragma: no cover — unreachable
        assert existing is not None
        _env.loader = ChoiceLoader([theme_loader, existing])


def render_page(
    context: PageContext,
    *,
    partial: bool = False,
    content_only: bool = False,
) -> str:
    """
    Render a full page from a PageContext.

    Renders the component template, then wraps it in the layout using
    a dynamically constructed wrapper template that extends the layout
    and injects the rendered content into the content block.

    Args:
        context: Page context with all data needed for rendering.
        partial: When True, injects ``_htmx_partial=True`` into template
            variables so ``base.html`` omits the ``<html><head>`` wrapper.
        content_only: When True, renders only the content template without
            the layout wrapper — used for htmx fragment targeting.

    Returns:
        Rendered HTML string.
    """
    env = get_jinja_env()

    # Build template variables from context
    template_vars = context.model_dump()
    if partial:
        template_vars["_htmx_partial"] = True

    # Render the content template first (standalone fragment)
    content_template = env.get_template(context.template)
    rendered_content = content_template.render(**template_vars)

    # Fragment targeting: return just the content, no layout wrapper
    if content_only:
        return rendered_content

    # Select layout
    layout_map = {
        "app_shell": "layouts/app_shell.html",
        "single_column": "layouts/single_column.html",
    }
    layout_template_name = layout_map.get(context.layout, "layouts/app_shell.html")

    # Build a wrapper template string that extends the layout and injects content
    # Use % formatting because the string contains Jinja2 delimiters that conflict with f-strings
    wrapper_source = (  # noqa: UP031
        "{%% extends '%s' %%}{%% block content %%}%s{%% endblock %%}"
    ) % (layout_template_name, rendered_content)

    wrapper_template = env.from_string(wrapper_source)
    return wrapper_template.render(**template_vars)


def render_site_page(
    template_name: str,
    context: SitePageContext | SiteAuthContext | Site404Context,
) -> str:
    """Render a site page from a context model.

    Args:
        template_name: Template path relative to templates/ (e.g. "site/page.html").
        context: Pydantic context model.

    Returns:
        Rendered HTML string.
    """
    env = get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**context.model_dump())


def render_fragment(template_name: str, **kwargs: Any) -> str:
    """
    Render an HTML fragment (for HTMX partial responses).

    Args:
        template_name: Template path relative to templates/.
        **kwargs: Template variables.

    Returns:
        Rendered HTML fragment string.
    """
    env = get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**kwargs)
