"""
DNR-UI Runtime

Server-rendered UI runtime using Jinja2 templates, HTMX, and Alpine.js.

This module provides:
- Template renderer (AppSpec -> Jinja2 -> HTML)
- Template context models (PageContext, TableContext, etc.)
- Page routes for server-rendered pages
- Static preview generator
- Development server with hot reload
- HTMX fragment endpoints for dynamic interactions

Example usage:
    >>> from dazzle_ui.runtime import run_combined_server
    >>>
    >>> # Run combined server (backend + template-rendered frontend)
    >>> run_combined_server(backend_spec, ui_spec, appspec=appspec)
    >>>
    >>> # Generate static preview files
    >>> from dazzle_ui.runtime.static_preview import generate_preview_files
    >>> generate_preview_files(appspec, "preview/")
"""

from dazzle_ui.runtime.combined_server import (
    DNRCombinedHandler,
    DNRCombinedServer,
    run_backend_only,
    run_combined_server,
    run_frontend_only,
)
from dazzle_ui.runtime.dev_server import (
    DNRDevServer,
    run_dev_server,
    run_dev_server_from_dict,
    run_dev_server_from_json,
)
from dazzle_ui.runtime.docker_runner import (
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
    "DNRDevServer",
    "run_dev_server",
    "run_dev_server_from_dict",
    "run_dev_server_from_json",
    # Combined server (backend + frontend)
    "DNRCombinedServer",
    "DNRCombinedHandler",
    "run_combined_server",
    "run_frontend_only",
    "run_backend_only",
    # Docker runner (docker-first infrastructure)
    "DockerRunner",
    "DockerRunConfig",
    "is_docker_available",
    "run_in_docker",
    "stop_docker_container",
]
