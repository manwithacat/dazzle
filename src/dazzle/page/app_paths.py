"""Single source of truth for ``/app/*`` page-route path construction (#1426).

Route *registration* (``compile_appspec_to_templates`` → ``create_page_routes``)
and every outbound *link* (``detail_url`` / row drill-down / nav href / CTA) used to
re-derive the same ``/app/<slug>/{id}`` formula independently — the slug rule
(``name.lower().replace("_","-")``) plus the per-mode path shape were copied across
~15 inline f-strings. When the two derivations drift, a link references a route that
isn't mounted → a silent dead link (the #1421 / #1426 footgun class).

This module is that one formula. Both the route table and the link layer derive
paths from here, so the path *rule* cannot diverge. A drift gate
(``tests/unit/test_app_paths_ssot.py``) forbids raw ``/app/.../{id}`` literals
re-creeping into the page layer, and a boot validator
(``route_validator.validate_app_links``) flags any residual link→route mismatch.

Pure: no I/O, no framework deps. ``id`` defaults to the literal ``"{id}"`` so the
same function yields both a registration template (``/app/task/{id}``) and a
concrete link (``/app/task/abc-123``).
"""

# The canonical slug rule lives in ``core`` so every layer shares one formula
# (#1440); re-exported here as the page-link entry point (#1426).
from dazzle.core.strings import entity_slug  # noqa: E402

__all__ = ["create_path", "detail_path", "edit_path", "entity_slug", "list_path"]


def list_path(app_prefix: str, slug: str) -> str:
    """List page: ``{app_prefix}/{slug}``."""
    return f"{app_prefix}/{slug}"


def create_path(app_prefix: str, slug: str) -> str:
    """Create page: ``{app_prefix}/{slug}/create``."""
    return f"{app_prefix}/{slug}/create"


def detail_path(app_prefix: str, slug: str, id: str = "{id}") -> str:
    """Detail (VIEW) page: ``{app_prefix}/{slug}/{id}``. ``id`` defaults to the
    literal ``{id}`` template segment used for route registration."""
    return f"{app_prefix}/{slug}/{id}"


def edit_path(app_prefix: str, slug: str, id: str = "{id}") -> str:
    """Edit page: ``{app_prefix}/{slug}/{id}/edit``."""
    return f"{app_prefix}/{slug}/{id}/edit"
