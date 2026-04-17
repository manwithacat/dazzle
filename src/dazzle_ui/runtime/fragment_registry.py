"""Fragment registry for composable HTMX fragments.

Provides a static registry of available fragment types so that agents
and tooling can discover fragments without reading template files.

Fragments fall into two categories:

1. **Active** — wired into a real runtime call site (template include
   or Python ``render_fragment()`` call). These are exercised whenever
   the framework renders a page and their coverage is asserted by
   ``dazzle coverage --fail-on-uncovered`` in CI.

2. **Parking-lot primitives** — shipped as canonical renderers for
   downstream consumers to opt into via surface config. They have a
   registry entry so tooling can discover them, but nothing in the
   framework runtime includes them by default. Listed in the
   ``PARKING_LOT_FRAGMENTS`` set below and excluded from the coverage
   requirement so the metric stays honest. A parking-lot fragment
   graduates to "active" when a real include/render site lands — at
   that point, remove it from ``PARKING_LOT_FRAGMENTS``.
"""

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
        "description": "Click-to-edit field with inline event handlers and HTMX save.",
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
    # --- Parking-lot primitives ------------------------------------------
    # Canonical renderers for cross-cutting UI primitives. Consumers
    # include these by name via the registry; include sites in base
    # layouts and region templates opt them into specific surfaces.
    "accordion": {
        "template": "fragments/accordion.html",
        "params": ["sections"],
        "emits": [],
        "listens": [],
        "description": "Collapsible sections — expand/collapse groups of content.",
    },
    "alert_banner": {
        "template": "fragments/alert_banner.html",
        "params": ["message", "level"],
        "emits": [],
        "listens": [],
        "description": "Full-width alert banner for app-level flash messages.",
    },
    "breadcrumbs": {
        "template": "fragments/breadcrumbs.html",
        "params": ["crumbs"],
        "emits": [],
        "listens": [],
        "description": "Breadcrumb navigation trail for multi-level pages.",
    },
    "command_palette": {
        "template": "fragments/command_palette.html",
        "params": ["actions"],
        "emits": [],
        "listens": [],
        "description": "Cmd+K spotlight-style search and action launcher.",
    },
    "context_menu": {
        "template": "fragments/context_menu.html",
        "params": ["menu_id", "items"],
        "emits": [],
        "listens": [],
        "description": "Right-click triggered menu for row/field-level actions.",
    },
    "detail_fields": {
        "template": "fragments/detail_fields.html",
        "params": ["item", "fields"],
        "emits": [],
        "listens": [],
        "description": "Definition-list renderer for detail/view surfaces.",
    },
    "popover": {
        "template": "fragments/popover.html",
        "params": ["trigger_text", "position"],
        "emits": [],
        "listens": [],
        "description": "Anchored floating content panel (click-triggered).",
    },
    "select_result": {
        "template": "fragments/select_result.html",
        "params": ["display_val", "value"],
        "emits": [],
        "listens": [],
        "description": "OOB swap fragment for autofill after search selection.",
    },
    "skeleton_patterns": {
        "template": "fragments/skeleton_patterns.html",
        "params": ["variant"],
        "emits": [],
        "listens": [],
        "description": "Loading-state skeleton shapes for HTMX in-flight requests.",
    },
    "slide_over": {
        "template": "fragments/slide_over.html",
        "params": ["panel_id", "width", "title"],
        "emits": [],
        "listens": [],
        "description": "Right-edge slide-out panel with focus trap for deep edits.",
    },
    "steps_indicator": {
        "template": "fragments/steps_indicator.html",
        "params": ["steps", "current_step"],
        "emits": [],
        "listens": [],
        "description": "Visual progress indicator for multi-step experience flows.",
    },
    "table_sentinel": {
        "template": "fragments/table_sentinel.html",
        "params": ["table"],
        "emits": [],
        "listens": [],
        "description": "Infinite-scroll trigger row for paginated tables.",
    },
    "toast": {
        "template": "fragments/toast.html",
        "params": ["message", "level"],
        "emits": [],
        "listens": [],
        "description": "Auto-dismissing notification emitted via with_toast() helper.",
    },
    "toggle_group": {
        "template": "fragments/toggle_group.html",
        "params": ["name", "options", "value", "multiple"],
        "emits": [],
        "listens": [],
        "description": "Segmented button group — exclusive or multi-select radiogroup.",
    },
    "tooltip_rich": {
        "template": "fragments/tooltip_rich.html",
        "params": ["trigger_text", "content"],
        "emits": [],
        "listens": [],
        "description": "HTML-content tooltip with configurable show/hide delays.",
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
    result: str = FRAGMENT_REGISTRY["search_select"]["template"]
    return result


# The 12 canonical UI primitives shipped by the framework for downstream
# consumers to opt into — they have a template + registry entry but no
# runtime caller wires them in by default. Kept explicit so the coverage
# tool can exclude them from the "every artefact must have a live
# consumer" gate without re-hunting include sites. Audit source:
# grep for ``fragments/<name>`` excluding fragment_registry.py + the
# fragment's own file. Re-run after any template edit and drop names
# from this set as real call sites land. See #794 post-mortem item #91.
PARKING_LOT_FRAGMENTS: frozenset[str] = frozenset(
    {
        "accordion",
        "alert_banner",
        "breadcrumbs",
        "command_palette",
        "context_menu",
        "popover",
        "skeleton_patterns",
        "slide_over",
        "steps_indicator",
        "toast",
        "toggle_group",
        "tooltip_rich",
    }
)
