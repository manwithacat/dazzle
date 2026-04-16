"""Route override discovery for project-level custom handlers (v0.29.0).

Scans project ``routes/`` for Python files with declaration headers
and loads custom FastAPI route handlers that replace generated routes.

Route override files use declaration headers::

    # dazzle:route-override GET /app/tasks/create
    from fastapi import Request
    from fastapi.responses import HTMLResponse

    async def handler(request: Request):
        return HTMLResponse("<h1>Custom Task Wizard</h1>")

When project routes are registered before generated routes,
FastAPI's first-match behavior ensures the project handler wins.
"""

import importlib.util
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# Declaration header pattern: # dazzle:route-override METHOD /path
_ROUTE_OVERRIDE_RE = re.compile(
    r"#\s*dazzle:route-override\s+(GET|POST|PUT|PATCH|DELETE)\s+(\S+)", re.IGNORECASE
)

# Valid Python module path: dotted identifier segments only.
# Enforces that extension router specs from dazzle.toml resolve to
# real package paths and prevents injection via the config value.
_MODULE_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_ATTR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class RouteOverrideDescriptor:
    """Metadata about a discovered route override."""

    method: str  # HTTP method (GET, POST, PUT, PATCH, DELETE)
    path: str  # Route path (e.g. /app/tasks/create)
    source_path: Path
    handler: Callable[..., Any]


def discover_route_overrides(routes_dir: Path) -> list[RouteOverrideDescriptor]:
    """Scan a project routes directory for override declarations.

    Args:
        routes_dir: Path to the project's ``routes/`` directory.

    Returns:
        List of route override descriptors.
    """
    overrides: list[RouteOverrideDescriptor] = []

    if not routes_dir.is_dir():
        return overrides

    for py_file in sorted(routes_dir.rglob("*.py")):
        if py_file.name.startswith("_"):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
        except OSError:
            continue

        match = _ROUTE_OVERRIDE_RE.search(content)
        if not match:
            continue

        method = match.group(1).upper()
        path = match.group(2).strip()

        handler = _load_handler(py_file)
        if handler is None:
            logger.warning("No callable 'handler' function found in %s", py_file)
            continue

        overrides.append(
            RouteOverrideDescriptor(
                method=method,
                path=path,
                source_path=py_file,
                handler=handler,
            )
        )
        logger.info("Discovered route override: %s %s from %s", method, path, py_file)

    return overrides


def _load_handler(py_file: Path) -> Callable[..., Any] | None:
    """Load a Python file and extract the ``handler`` function."""
    module_name = f"dazzle_routes.{py_file.stem}"
    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception:
        logger.warning("Failed to load route override %s", py_file, exc_info=True)
        del sys.modules[module_name]
        return None

    func: Callable[..., Any] | None = getattr(module, "handler", None)
    if func is None or not callable(func):
        del sys.modules[module_name]
        return None

    return func


def load_extension_routers(
    project_root: Path,
    router_specs: list[str],
) -> list[APIRouter]:
    """Import FastAPI ``APIRouter`` objects declared in ``dazzle.toml`` (#786).

    Each entry in ``router_specs`` is a ``module:attr`` string — e.g.
    ``app.routes.graph:router``. The module is imported with
    ``project_root`` on ``sys.path`` so apps can place routers under
    their own package without a wheel install.

    Returns the list of successfully resolved routers. Malformed specs
    and import failures are logged and skipped so a single broken
    router never takes the whole app down.
    """
    routers: list[APIRouter] = []
    if not router_specs:
        return routers

    import importlib

    root_str = str(project_root)
    added_to_path = False
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
        added_to_path = True

    try:
        for spec in router_specs:
            if ":" not in spec:
                logger.warning("Invalid extension router spec %r — expected 'module:attr'", spec)
                continue
            module_path, attr_name = spec.split(":", 1)
            module_path = module_path.strip()
            attr_name = attr_name.strip()
            if not _MODULE_PATH_RE.match(module_path) or not _ATTR_NAME_RE.match(attr_name):
                # Reject anything that isn't a plain dotted identifier —
                # no path traversal, no shell chars, no dynamic expressions.
                logger.warning("Invalid extension router spec %r", spec)
                continue

            try:
                # Module path is whitelisted to plain dotted identifiers by
                # _MODULE_PATH_RE above and sourced from the project's own
                # dazzle.toml — not external request input.
                module = importlib.import_module(  # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
                    module_path
                )
            except Exception:
                logger.warning(
                    "Failed to import extension router module %r", module_path, exc_info=True
                )
                continue

            router = getattr(module, attr_name, None)
            if router is None:
                logger.warning("Extension router %r not found in module %r", attr_name, module_path)
                continue
            if not isinstance(router, APIRouter):
                logger.warning(
                    "Extension %s.%s is not a FastAPI APIRouter (got %s)",
                    module_path,
                    attr_name,
                    type(router).__name__,
                )
                continue

            routers.append(router)
            logger.info("Loaded extension router %s:%s", module_path, attr_name)
    finally:
        if added_to_path:
            try:
                sys.path.remove(root_str)
            except ValueError:
                pass

    return routers


def build_override_router(routes_dir: Path) -> APIRouter | None:
    """Build a FastAPI router from discovered route overrides.

    Args:
        routes_dir: Path to the project's ``routes/`` directory.

    Returns:
        APIRouter with project routes, or None if no overrides found.
    """
    overrides = discover_route_overrides(routes_dir)
    if not overrides:
        return None

    router = APIRouter(tags=["Project Overrides"])
    method_map = {
        "GET": router.get,
        "POST": router.post,
        "PUT": router.put,
        "PATCH": router.patch,
        "DELETE": router.delete,
    }

    for override in overrides:
        decorator = method_map.get(override.method)
        if decorator:
            decorator(override.path)(override.handler)
            logger.info(
                "Registered route override: %s %s -> %s",
                override.method,
                override.path,
                override.source_path.name,
            )

    return router
