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

    # #1140: both `server._setup_routes` (post-build, line ~1505) and
    # `app_factory.assemble_post_build_routes` (#1140 follow-up) call
    # `validate_routes` on the same app — guard with a state flag so
    # the second call short-circuits instead of double-emitting every
    # conflict warning.
    if getattr(app.state, "dazzle_routes_validated", False):
        return getattr(app.state, "dazzle_route_conflicts", [])

    # (path, method) → list of (name, module_qualname) pairs. Carrying
    # the endpoint module + qualname lets the conflict message tell
    # the operator *where* each duplicate came from — fixing the
    # diagnostic gap called out in #1140 (filing this issue required
    # the user to patch APIRouter.add_api_route by hand to recover
    # the same provenance).
    seen: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))

    for route in app.routes:
        if isinstance(route, Mount):
            continue
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue

        name = getattr(route, "name", None) or str(getattr(route, "endpoint", "unknown"))
        endpoint = getattr(route, "endpoint", None)
        module = getattr(endpoint, "__module__", "?")
        qualname = getattr(endpoint, "__qualname__", getattr(endpoint, "__name__", "?"))
        provenance = f"{module}.{qualname}"
        for method in methods:
            seen[path][method].append((name, provenance))

    conflicts: list[str] = []
    for path, methods in sorted(seen.items()):
        for method, entries in sorted(methods.items()):
            if len(entries) > 1:
                names = ", ".join(n for n, _ in entries)
                provenances = "; ".join(f"{n} <- {p}" for n, p in entries)
                desc = f"{method} {path} registered {len(entries)} times: {names} [{provenances}]"
                conflicts.append(desc)

    if conflicts:
        for c in conflicts:
            logger.warning("Route conflict: %s", c)
        if strict:
            raise RuntimeError(
                f"Route conflicts detected ({len(conflicts)}):\n" + "\n".join(conflicts)
            )

    app.state.dazzle_routes_validated = True
    app.state.dazzle_route_conflicts = conflicts
    return conflicts
