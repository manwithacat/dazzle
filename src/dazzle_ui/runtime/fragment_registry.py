"""Fragment registry for composable HTMX fragments.

Provides a static registry of available fragment types so that agents
and tooling can discover fragments without reading template files.
"""

from __future__ import annotations

from typing import Any

FRAGMENT_REGISTRY: dict[str, dict[str, Any]] = {
    "search_select": {
        "template": "fragments/search_select.html",
        "params": [
            "field.name",
            "field.label",
            "field.placeholder",
            "field.source.endpoint",
            "field.source.debounce_ms",
            "field.source.min_chars",
        ],
        "emits": ["itemSelected"],
        "listens": [],
        "description": "Debounced search input with dropdown selection and autofill.",
    },
    "search_results": {
        "template": "fragments/search_results.html",
        "params": [
            "items",
            "display_key",
            "value_key",
            "secondary_key",
            "field_name",
            "query",
            "min_chars",
            "select_endpoint",
        ],
        "emits": [],
        "listens": [],
        "description": "Result items returned by the search endpoint.",
    },
    "search_input": {
        "template": "fragments/search_input.html",
        "params": ["endpoint", "target", "placeholder"],
        "emits": [],
        "listens": [],
        "description": "Debounced search text input with loading indicator and clear button.",
    },
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
        "description": "Click-to-edit field with Alpine.js state and HTMX save.",
    },
    "bulk_actions": {
        "template": "fragments/bulk_actions.html",
        "params": ["entity_name", "actions_endpoint"],
        "emits": [],
        "listens": ["selected"],
        "description": "Toolbar for bulk update/delete on selected table rows.",
    },
    "status_badge": {
        "template": "fragments/status_badge.html",
        "params": ["value"],
        "emits": [],
        "listens": [],
        "description": "Coloured badge for status values with automatic formatting.",
    },
    "form_errors": {
        "template": "fragments/form_errors.html",
        "params": ["form_errors"],
        "emits": [],
        "listens": [],
        "description": "Validation error alert with single or multiple error messages.",
    },
}


def get_fragment_registry() -> dict[str, dict[str, Any]]:
    """Return the full fragment registry."""
    return FRAGMENT_REGISTRY


def get_fragment_info(name: str) -> dict[str, Any] | None:
    """Return info for a single fragment type, or None if not found."""
    return FRAGMENT_REGISTRY.get(name)


def get_template_for_source(source: Any) -> str:
    """Return the fragment template name for a field with a dynamic source.

    Args:
        source: A ``FieldSourceContext`` (or any object with an ``endpoint`` attr).

    Returns:
        Template name string, e.g. ``"fragments/search_select.html"``.
    """
    # Fields with an external data source always render as search_select
    return FRAGMENT_REGISTRY["search_select"]["template"]
