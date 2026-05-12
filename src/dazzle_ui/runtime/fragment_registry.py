"""Fragment registry for composable HTMX fragments.

Provides a static registry of the active framework fragments so that
agents and tooling can discover them without reading template files.

Post-#1044 (v0.67.90+): the parking-lot tier was retired entirely
along with all 14 dormant Jinja templates that backed it. The remaining
5 fragments are framework-internal — each is wired into a real Python
renderer (form_renderer / detail_renderer / table_renderer) and the
``.html`` template on disk is the historical Jinja shape kept for the
parking-lot fragment test suite that gates the final ``jinja2`` drop.
"""

from typing import Any

FRAGMENT_REGISTRY: dict[str, dict[str, Any]] = {
    "table_rows": {
        "template": "fragments/table_rows.html",
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
        "template": "fragments/table_pagination.html",
        "params": ["table.total", "table.page_size", "table.page", "table.api_endpoint"],
        "emits": [],
        "listens": [],
        "description": "Page navigation buttons for paginated tables.",
    },
    "inline_edit": {
        "template": "fragments/inline_edit.html",
        "params": ["field_name", "field_value", "endpoint", "field_type"],
        "emits": [],
        "listens": [],
        "description": "Click-to-edit field with inline event handlers and HTMX save.",
    },
    "form_errors": {
        "template": "fragments/form_errors.html",
        "params": ["form_errors"],
        "emits": [],
        "listens": [],
        "description": "Validation error alert with single or multiple error messages.",
    },
    "detail_fields": {
        "template": "fragments/detail_fields.html",
        "params": ["item", "fields"],
        "emits": [],
        "listens": [],
        "description": "Definition-list renderer for detail/view surfaces.",
    },
    "table_sentinel": {
        "template": "fragments/table_sentinel.html",
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


# Post-#1044: the parking-lot tier is empty. The frozenset stays so
# existing imports keep working; cli/coverage.py still references it
# to compute the "every counted fragment has a real caller" gate.
PARKING_LOT_FRAGMENTS: frozenset[str] = frozenset()
