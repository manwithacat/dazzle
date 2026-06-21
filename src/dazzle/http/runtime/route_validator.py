"""
Route conflict detection for FastAPI applications.

Inspects registered routes after all routers are mounted and warns
about duplicate method+path combinations that FastAPI silently overwrites.

Also hosts the #1426 link↔route check (``validate_app_links``): a boot-time
guard that every ``/app`` drill-down detail link the app will emit has a matching
mounted detail route — converting the silent list-only dead-link (mode-1 of #1422)
into a boot signal.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


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


# Env opt-in to make a link↔route mismatch a hard boot failure (CI-friendly).
_STRICT_LINKS_ENV = "DAZZLE_STRICT_LINKS"


def _mounted_get_paths(app: FastAPI) -> set[str]:
    """The set of GET route path templates mounted on the app."""
    mounted: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods and "GET" in methods:
            mounted.add(path)
    return mounted


def _drill_down_entities(appspec: Any) -> set[str]:
    """Entities whose list surface / workspace region advertises a ``/{id}``
    drill-down link — mirrors the #1421 detail-synthesis predicate exactly."""
    refs: set[str] = set()
    for s in getattr(appspec, "surfaces", []) or []:
        mode = getattr(getattr(s, "mode", None), "value", None)
        if mode == "list" and getattr(s, "entity_ref", None):
            refs.add(s.entity_ref)
    for ws in getattr(appspec, "workspaces", []) or []:
        for region in getattr(ws, "regions", []) or []:
            src = getattr(region, "source", None)
            if src:
                refs.add(src)
    return refs


def validate_app_links(
    app: FastAPI, appspec: Any, *, app_prefix: str = "/app", strict: bool = False
) -> list[str]:
    """#1426: verify every ``/app`` drill-down detail link the app emits resolves
    to a mounted route.

    Every list surface and workspace list region advertises a
    ``{app_prefix}/<slug>/{id}`` row drill-down link (see ``server.py`` /
    ``workspace_renderer`` / the #1421 detail synthesis). The link generator and the
    route table are independent derivations of the DSL; this catches the residual
    case where an entity has a list presence but no detail route is mounted — a
    silent dead link (mode-1 of #1422). Link and route paths are both built from the
    ``dazzle.page.app_paths`` SSOT, so this only fires on a genuine generation gap,
    never a formula mismatch.

    Warns per mismatch (naming the entity + missing route). Raises ``RuntimeError``
    when ``strict`` (or the ``DAZZLE_STRICT_LINKS`` env var) is set. Idempotent —
    both ``server`` and ``app_factory`` mount paths may call it.
    """
    from dazzle.page import app_paths

    if getattr(app.state, "dazzle_app_links_validated", False):
        return getattr(app.state, "dazzle_app_link_problems", [])

    strict = strict or bool(os.environ.get(_STRICT_LINKS_ENV))

    mounted = _mounted_get_paths(app)
    domain = getattr(appspec, "domain", None)
    problems: list[str] = []
    for ref in sorted(_drill_down_entities(appspec)):
        entity = domain.get_entity(ref) if domain is not None else None
        if entity is None:
            continue
        detail_route = app_paths.detail_path(app_prefix, app_paths.entity_slug(entity.name))
        if detail_route not in mounted:
            problems.append(
                f"{entity.name}: a list/region advertises a drill-down link to "
                f"{detail_route} but no detail route is mounted"
            )

    if problems:
        for p in problems:
            logger.warning("Link↔route mismatch (#1426): %s", p)
        if strict:
            raise RuntimeError(
                f"Link↔route mismatches detected ({len(problems)}):\n" + "\n".join(problems)
            )

    app.state.dazzle_app_links_validated = True
    app.state.dazzle_app_link_problems = problems
    return problems
