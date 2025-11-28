"""
DNR-UI Runtime

Native UI runtime implementation (pure JavaScript + signals).

This module provides:
- JavaScript generator (UISpec -> pure JS)
- Development server with hot reload
- DOM rendering engine (built into runtime)
- Signals-based state management (built into runtime)

Example usage:
    >>> from dazzle_dnr_ui.specs import UISpec
    >>> from dazzle_dnr_ui.runtime import generate_js_app, run_dev_server
    >>>
    >>> # Create spec (from DSL conversion or manual)
    >>> spec = UISpec(name="my_app", ...)
    >>>
    >>> # Generate static files
    >>> generate_js_app(spec, "output/")
    >>>
    >>> # Or run development server
    >>> run_dev_server(spec, port=3000)
"""

from dazzle_dnr_ui.runtime.js_generator import (
    JSGenerator,
    generate_js_app,
    generate_single_html,
)

from dazzle_dnr_ui.runtime.dev_server import (
    DNRDevServer,
    run_dev_server,
    run_dev_server_from_dict,
    run_dev_server_from_json,
)


__all__ = [
    # JavaScript generator
    "JSGenerator",
    "generate_js_app",
    "generate_single_html",
    # Development server
    "DNRDevServer",
    "run_dev_server",
    "run_dev_server_from_dict",
    "run_dev_server_from_json",
]
