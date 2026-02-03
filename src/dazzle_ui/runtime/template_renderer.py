"""
Jinja2 template renderer for server-rendered DNR pages.

Sets up the Jinja2 environment with custom filters, globals, and
template loading from the templates/ directory.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

if TYPE_CHECKING:
    from dazzle_ui.runtime.template_context import PageContext

# Template directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _currency_filter(value: Any, currency: str = "GBP") -> str:
    """Format a number as currency."""
    if value is None:
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    symbols = {"GBP": "\u00a3", "USD": "$", "EUR": "\u20ac"}
    symbol = symbols.get(currency, currency + " ")
    return f"{symbol}{amount:,.2f}"


def _date_filter(value: Any, fmt: str = "%d %b %Y") -> str:
    """Format a date or datetime."""
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
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


def _truncate_filter(value: Any, length: int = 50) -> str:
    """Truncate text to a given length."""
    if value is None:
        return ""
    text = str(value)
    if len(text) <= length:
        return text
    return text[:length] + "..."


def create_jinja_env() -> Environment:
    """Create and configure the Jinja2 environment."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Custom filters
    env.filters["currency"] = _currency_filter
    env.filters["dateformat"] = _date_filter
    env.filters["badge_class"] = _badge_filter
    env.filters["bool_icon"] = _bool_icon_filter
    env.filters["truncate_text"] = _truncate_filter

    return env


# Module-level singleton
_env: Environment | None = None


def get_jinja_env() -> Environment:
    """Get the shared Jinja2 environment (lazy singleton)."""
    global _env
    if _env is None:
        _env = create_jinja_env()
    return _env


def render_page(context: PageContext) -> str:
    """
    Render a full page from a PageContext.

    Renders the component template, then wraps it in the layout using
    a dynamically constructed wrapper template that extends the layout
    and injects the rendered content into the content block.

    Args:
        context: Page context with all data needed for rendering.

    Returns:
        Rendered HTML string.
    """
    env = get_jinja_env()

    # Select layout
    layout_map = {
        "app_shell": "layouts/app_shell.html",
        "single_column": "layouts/single_column.html",
    }
    layout_template_name = layout_map.get(context.layout, "layouts/app_shell.html")

    # Build template variables from context
    template_vars = context.model_dump()

    # Render the content template first (standalone fragment)
    content_template = env.get_template(context.template)
    rendered_content = content_template.render(**template_vars)

    # Build a wrapper template string that extends the layout and injects content
    # Use % formatting because the string contains Jinja2 delimiters that conflict with f-strings
    wrapper_source = (  # noqa: UP031
        "{%% extends '%s' %%}{%% block content %%}%s{%% endblock %%}"
    ) % (layout_template_name, rendered_content)

    wrapper_template = env.from_string(wrapper_source)
    return wrapper_template.render(**template_vars)


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
