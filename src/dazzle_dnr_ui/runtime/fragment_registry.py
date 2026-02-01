"""Fragment registry for composable HTMX fragments.

Provides a static registry of available fragment types so that agents
and tooling can discover fragments without reading template files.
"""

from __future__ import annotations

from typing import Any

FRAGMENT_REGISTRY: dict[str, dict[str, Any]] = {
    "search_select": {
        "template": "fragments/search_select.html",
        "params": ["label", "name", "search_endpoint", "placeholder"],
        "emits": ["itemSelected"],
        "listens": [],
        "description": "Debounced search input with dropdown selection and autofill.",
    },
    "search_results": {
        "template": "fragments/search_results.html",
        "params": ["items", "display_key", "value_key", "secondary_key"],
        "emits": [],
        "listens": [],
        "description": "Result items returned by the search endpoint.",
    },
}


def get_fragment_registry() -> dict[str, dict[str, Any]]:
    """Return the full fragment registry."""
    return FRAGMENT_REGISTRY


def get_fragment_info(name: str) -> dict[str, Any] | None:
    """Return info for a single fragment type, or None if not found."""
    return FRAGMENT_REGISTRY.get(name)
