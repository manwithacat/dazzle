"""Fragment registry — informational catalog (post-#1044).

Pre-#1044 this listed Jinja templates under
``src/dazzle/page/templates/fragments/`` that downstream agents and
tooling could discover. After the #1044 jinja2 retirement the
framework no longer ships any Jinja templates — every fragment is
emitted by a Python renderer in ``dazzle.page.runtime``. The registry
stays so the MCP ``status`` / ``coverage`` tooling that reads
``get_fragment_registry()`` has a stable, queryable list of the
fragment-rendering call sites.

Each entry maps a logical fragment name → the Python renderer module
that emits it. The ``params`` / ``description`` fields are kept
unchanged from the legacy registry so existing consumers don't break.
"""

from typing import Any

FRAGMENT_REGISTRY: dict[str, dict[str, Any]] = {
    "table_rows": {
        "module": "dazzle.page.runtime.table_renderer",
        "params": [
            "table.rows",
            "table.columns",
            "table.entity_name",
            "table.detail_url_template",
            "table.api_endpoint",
        ],
        "emits": [],
        "listens": [],
        "description": "Table body rows with typed cell rendering and row-level actions.",
    },
    "table_pagination": {
        "module": "dazzle.page.runtime.table_renderer",
        "params": ["table.total", "table.page_size", "table.page", "table.api_endpoint"],
        "emits": [],
        "listens": [],
        "description": "Page navigation buttons for paginated tables.",
    },
    "inline_edit": {
        "module": "dazzle.page.runtime.table_renderer",
        "params": ["field_name", "field_value", "endpoint", "field_type"],
        "emits": [],
        "listens": [],
        "description": "Click-to-edit field with inline event handlers and HTMX save.",
    },
    "form_errors": {
        "module": "dazzle.page.runtime.form_renderer",
        "params": ["form_errors"],
        "emits": [],
        "listens": [],
        "description": "Validation error alert with single or multiple error messages.",
    },
    "detail_fields": {
        "module": "dazzle.page.runtime.detail_renderer",
        "params": ["item", "fields"],
        "emits": [],
        "listens": [],
        "description": "Definition-list renderer for detail/view surfaces.",
    },
    "table_sentinel": {
        "module": "dazzle.page.runtime.table_renderer",
        "params": ["table"],
        "emits": [],
        "listens": [],
        "description": "Infinite-scroll trigger row for paginated tables.",
    },
}


def get_fragment_registry() -> dict[str, dict[str, Any]]:
    """Return the full fragment registry."""
    return FRAGMENT_REGISTRY


def get_fragment_info(name: str) -> dict[str, Any] | None:
    """Return info for a single fragment type, or None if not found."""
    return FRAGMENT_REGISTRY.get(name)


# Post-#1044: the parking-lot tier was retired entirely. The frozenset
# stays empty so existing imports (cli/coverage.py) keep working.
PARKING_LOT_FRAGMENTS: frozenset[str] = frozenset()
