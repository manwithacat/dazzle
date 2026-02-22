"""
DNR-UI Runtime

Server-rendered UI runtime using Jinja2 templates, HTMX, and dz.js micro-runtime.

This module provides:
- Template renderer (AppSpec -> Jinja2 -> HTML)
- Template context models (PageContext, TableContext, etc.)
- Page routes for server-rendered pages
- Static preview generator
- Unified server (single-port FastAPI with API + UI)
- HTMX fragment endpoints for dynamic interactions

Example usage:
    >>> from dazzle_ui.runtime import run_unified_server
    >>>
    >>> # Run unified server (backend + page routes on one port)
    >>> run_unified_server(appspec)
    >>>
    >>> # Generate static preview files
    >>> from dazzle_ui.runtime.static_preview import generate_preview_files
    >>> generate_preview_files(appspec, "preview/")
"""

from dazzle_ui.runtime.combined_server import (
    run_backend_only,
    run_unified_server,
)
from dazzle_ui.runtime.dev_server import (
    DazzleDevServer,
    run_dev_server,
    run_dev_server_from_dict,
    run_dev_server_from_json,
)
from dazzle_ui.runtime.docker import (
    DockerRunConfig,
    DockerRunner,
    is_docker_available,
    run_in_docker,
    stop_docker_container,
)
from dazzle_ui.runtime.realtime_client import (
    generate_realtime_init_js,
    get_realtime_client_js,
)
from dazzle_ui.runtime.template_context import (
    ColumnContext,
    DetailContext,
    FieldContext,
    FormContext,
    NavItemContext,
    PageContext,
    TableContext,
)
from dazzle_ui.runtime.template_renderer import (
    render_fragment,
    render_page,
)

__all__ = [
    # Template rendering
    "render_page",
    "render_fragment",
    "PageContext",
    "TableContext",
    "FormContext",
    "DetailContext",
    "ColumnContext",
    "FieldContext",
    "NavItemContext",
    # Realtime client
    "get_realtime_client_js",
    "generate_realtime_init_js",
    # Development server
    "DazzleDevServer",
    "run_dev_server",
    "run_dev_server_from_dict",
    "run_dev_server_from_json",
    # Unified server (single-port FastAPI)
    "run_unified_server",
    "run_backend_only",
    # Docker runner (docker-first infrastructure)
    "DockerRunner",
    "DockerRunConfig",
    "is_docker_available",
    "run_in_docker",
    "stop_docker_container",
]
