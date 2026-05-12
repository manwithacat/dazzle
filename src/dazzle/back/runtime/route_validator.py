"""
Route conflict detection for FastAPI applications.

Inspects registered routes after all routers are mounted and warns
about duplicate method+path combinations that FastAPI silently overwrites.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("dazzle.routes")


def validate_routes(app: FastAPI, *, strict: bool = False) -> list[str]:
    """Check for duplicate route registrations and log warnings.

    Iterates ``app.routes``, groups ``APIRoute`` entries by path pattern,
    and flags paths where the same HTTP method is registered more than once.

    Non-API routes (mounts, static files, websockets) are ignored.

    Args:
        app: FastAPI application whose routes to inspect.
        strict: When *True*, raise ``RuntimeError`` on the first conflict
            instead of just logging.  Useful in tests.

    Returns:
        List of human-readable conflict descriptions (empty means clean).
    """
    from starlette.routing import Mount

    # (path, method) → list of route names/endpoints
    seen: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for route in app.routes:
        # Skip non-API routes (static file mounts, websocket routes, etc.)
        if isinstance(route, Mount):
            continue
        # Only inspect APIRoute (has .methods and .path)
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue

        name = getattr(route, "name", None) or str(getattr(route, "endpoint", "unknown"))
        for method in methods:
            seen[path][method].append(name)

    conflicts: list[str] = []
    for path, methods in sorted(seen.items()):
        for method, names in sorted(methods.items()):
            if len(names) > 1:
                desc = f"{method} {path} registered {len(names)} times: {', '.join(names)}"
                conflicts.append(desc)

    if conflicts:
        for c in conflicts:
            logger.warning("Route conflict: %s", c)
        if strict:
            raise RuntimeError(
                f"Route conflicts detected ({len(conflicts)}):\n" + "\n".join(conflicts)
            )

    return conflicts
