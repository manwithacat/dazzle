"""
Dazzle UI Runtime

Server-rendered UI runtime: typed Fragment primitives (rendered to HTML
via pure Python — no Jinja2 since ADR-0023), HTMX, and Alpine.js.

This module provides:
- Template renderer (AppSpec -> typed Fragment tree -> HTML)
- Template context models (PageContext, TableContext, etc.)
- Page routes for server-rendered pages
- Static preview generator
- Unified server (single-port FastAPI with API + UI)
- HTMX fragment endpoints for dynamic interactions

Example usage:
    >>> # The unified server is the back+ui composition root; it lives in the
    >>> # back layer (ui must not import back — the composition root may import both):
    >>> from dazzle.http.runtime.combined_server import run_unified_server
    >>> run_unified_server(appspec)
    >>>
    >>> # Generate static preview files
    >>> from dazzle.page.runtime.static_preview import generate_preview_files
    >>> generate_preview_files(appspec, "preview/")
"""

from dazzle.page.runtime.detail_renderer import render_detail_view
from dazzle.page.runtime.dev_server import (
    DazzleDevServer,
    run_dev_server,
    run_dev_server_from_dict,
    run_dev_server_from_json,
)
from dazzle.page.runtime.template_renderer import render_page
from dazzle.render.context import (
    ColumnContext,
    DetailContext,
    FieldContext,
    FormContext,
    NavItemContext,
    PageContext,
    PdfViewerContext,
    TableContext,
)

__all__ = [
    # Template rendering
    "render_page",
    # Canonical delegation helper for custom per-entity detail viewers
    # (#1297): a `render: <name>` renderer on a VIEW surface can render
    # the standard detail body via `render_detail_view(ctx["detail_context"])`
    # and then wrap/append its own chrome. Replaces the removed (ADR-0023)
    # Jinja `components/detail_view.html` override + `dz://` fall-through.
    "render_detail_view",
    "PageContext",
    "TableContext",
    "FormContext",
    "DetailContext",
    "PdfViewerContext",
    "ColumnContext",
    "FieldContext",
    "NavItemContext",
    # Development server
    "DazzleDevServer",
    "run_dev_server",
    "run_dev_server_from_dict",
    "run_dev_server_from_json",
    # Unified server (single-port FastAPI) moved to dazzle.http.runtime.combined_server
    # (#smells 2026-06-19 — ui must not import back; the composition root lives in back).
]
