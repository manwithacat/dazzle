"""Build and render a LIST surface through the page-route dispatch path.

The path under test is the one a list page takes: a ``TableContext`` (what
the page route assembles) -> ``_build_dispatch_ctx`` (the page-route seam
every surface renderer shares) -> ``FragmentSurfaceAdapter.build`` ->
``FragmentRenderer``. Calling tests override the table and assert on the
ctx dict or the rendered HTML.
"""

from typing import Any

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.context import ColumnContext, TableContext
from dazzle.render.fragment import FragmentRenderer


class ContactListSurface:
    """The minimal surface shape the adapter reads (name, title, mode, entity)."""

    name = "contact_list"
    title = "Contacts"
    mode = SurfaceMode.LIST
    entity_ref = "Contact"


class _RenderContext:
    def __init__(self, table: TableContext) -> None:
        self.table = table
        self.form = None
        self.detail = None


def contact_table(**overrides: Any) -> TableContext:
    """A one-column, zero-row Contact table; override any TableContext field."""
    base: dict[str, Any] = {
        "entity_name": "Contact",
        "title": "Contacts",
        "columns": [ColumnContext(key="name", label="Name")],
        "api_endpoint": "/api/contacts",
        "rows": [],
        "total": 0,
        "table_id": "contact_table",
    }
    base.update(overrides)
    return TableContext(**base)


def list_ctx(table: TableContext, surface: Any = None) -> dict[str, Any]:
    """The dispatch ctx the page route hands the adapter for ``table``."""
    return _build_dispatch_ctx(_RenderContext(table), surface or ContactListSurface())


def render_list(ctx: dict[str, Any]) -> str:
    """Render the Contact list surface for an already-built dispatch ctx."""
    return FragmentRenderer().render(FragmentSurfaceAdapter().build(ContactListSurface(), ctx))
