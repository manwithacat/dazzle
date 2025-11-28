"""
DNR-UI Runtime

Native UI runtime implementation (pure JavaScript + signals).

This module provides:
- JavaScript generator (UISpec -> pure JS)
- Vite bundler (UISpec -> ES module Vite project)
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
    >>> # Generate static files (single HTML or split)
    >>> generate_js_app(spec, "output/")
    >>>
    >>> # Generate Vite project (production-ready bundling)
    >>> from dazzle_dnr_ui.runtime import generate_vite_app
    >>> generate_vite_app(spec, "vite-output/")
    >>> # Then: cd vite-output && npm install && npm run dev
    >>>
    >>> # Or run development server
    >>> run_dev_server(spec, port=3000)
"""

from dazzle_dnr_ui.runtime.js_generator import (
    JSGenerator,
    generate_js_app,
    generate_single_html,
    get_runtime_js,
)

from dazzle_dnr_ui.runtime.js_loader import (
    load_js_module,
    load_js_modules,
    generate_iife_bundle,
    generate_esm_bundle,
)

from dazzle_dnr_ui.runtime.realtime_client import (
    get_realtime_client_js,
    generate_realtime_init_js,
)

from dazzle_dnr_ui.runtime.dev_server import (
    DNRDevServer,
    run_dev_server,
    run_dev_server_from_dict,
    run_dev_server_from_json,
)

from dazzle_dnr_ui.runtime.vite_generator import (
    ViteGenerator,
    generate_vite_app,
    generate_es_modules,
)

from dazzle_dnr_ui.runtime.combined_server import (
    DNRCombinedServer,
    DNRCombinedHandler,
    run_combined_server,
    run_frontend_only,
)


__all__ = [
    # JavaScript generator (single file / split)
    "JSGenerator",
    "generate_js_app",
    "generate_single_html",
    "get_runtime_js",
    # JavaScript loader (modular JS files)
    "load_js_module",
    "load_js_modules",
    "generate_iife_bundle",
    "generate_esm_bundle",
    # Realtime client
    "get_realtime_client_js",
    "generate_realtime_init_js",
    # Vite generator (ES modules / bundled)
    "ViteGenerator",
    "generate_vite_app",
    "generate_es_modules",
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
]
