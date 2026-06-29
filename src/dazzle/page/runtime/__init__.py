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
    # (ADR-0049 Phase 2) The #1297 generic-detail delegation helper moved to
    # the http layer — custom VIEW renderers now delegate via
    # `from dazzle.http.runtime.renderers.fragment_adapter import render_generic_detail`
    # (substrate-backed). The legacy page-layer `render_detail_view` is deleted.
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
