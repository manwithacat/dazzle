"""
Jinja2 template renderer for server-rendered DNR pages.

Sets up the Jinja2 environment with custom filters, globals, and
template loading from the templates/ directory.
"""

from __future__ import annotations

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


def _badge_filter(value: Any) -> str:
    """Map a status value to a DaisyUI badge class."""
    if value is None:
        return ""
    status = str(value).lower().replace(" ", "_")
    badge_map = {
        "active": "badge-success",
        "done": "badge-success",
        "completed": "badge-success",
        "approved": "badge-success",
        "in_progress": "badge-info",
        "open": "badge-info",
        "review": "badge-warning",
        "pending": "badge-warning",
        "on_hold": "badge-warning",
        "todo": "badge-ghost",
        "draft": "badge-ghost",
        "new": "badge-ghost",
        "inactive": "badge-error",
        "overdue": "badge-error",
        "cancelled": "badge-error",
        "rejected": "badge-error",
        "failed": "badge-error",
    }
    css_class = badge_map.get(status, "badge-ghost")
    return css_class


def _bool_icon_filter(value: Any) -> Markup:
    """Render a boolean as a check or cross icon."""
    if value:
        return Markup('<span class="text-success">&#10003;</span>')
    return Markup('<span class="text-base-content/30">&#10005;</span>')


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
            dt = datetime.fromisoformat(value)
        except ValueError:
            return str(value)
    if dt is None:
        return str(value)
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


def _truncate_filter(value: Any, length: int = 50) -> str:
    """Truncate text to a given length."""
    if value is None:
        return ""
    # Ref fields may arrive as dicts — extract a display name instead of repr
    if isinstance(value, dict):
        text = str(
            value.get("name")
            or value.get("title")
            or value.get("label")
            or value.get("email")
            or value.get("id", "")
        )
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
    env.globals["_use_cdn"] = True  # default; overridden from [ui] cdn in dazzle.toml

    # Global: detect if compiled Tailwind CSS bundle exists
    static_dir = Path(__file__).parent / "static"
    bundled = (static_dir / "css" / "dazzle-bundle.css").exists()
    # Also check project static dir (sibling of project templates dir)
    if not bundled and project_templates_dir:
        project_static = project_templates_dir.parent / "static"
        bundled = (project_static / "css" / "dazzle-bundle.css").exists()
    env.globals["_tailwind_bundled"] = bundled

    # Custom filters
    env.filters["currency"] = _currency_filter
    env.filters["dateformat"] = _date_filter
    env.filters["badge_class"] = _badge_filter
    env.filters["bool_icon"] = _bool_icon_filter
    env.filters["truncate_text"] = _truncate_filter
    env.filters["timeago"] = _timeago_filter
    env.filters["slugify"] = _slugify_filter
    env.filters["basename_or_url"] = _basename_or_url_filter

    return env


# Module-level singleton
_env: Environment | None = None


def get_jinja_env() -> Environment:
    """Get the shared Jinja2 environment (lazy singleton)."""
    global _env
    if _env is None:
        _env = create_jinja_env()
    return _env


def configure_project_templates(project_templates_dir: Path) -> None:
    """Reconfigure the Jinja2 environment with project-level template overrides.

    Call this during app startup to enable project templates that override
    framework defaults.  Framework templates remain accessible via ``dz://``.
    """
    global _env
    _env = create_jinja_env(project_templates_dir)


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
