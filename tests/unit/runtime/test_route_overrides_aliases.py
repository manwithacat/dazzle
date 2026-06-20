"""Issue #1020: route override re-exports must not collapse onto a single handler.

When multiple ``# dazzle:route-override`` files do
``from X import handler`` to alias an existing surface, each alias must
register a *distinct* dispatch entry. The previous keying scheme keyed by
the handler's defining module, which collapsed every alias onto the
first-imported handler.
"""

from __future__ import annotations

import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest


def _write_module(dirpath: Path, filename: str, body: str) -> Path:
    """Write a module file under a temp project root, dedenting the body."""
    p = dirpath / filename
    p.write_text(textwrap.dedent(body).lstrip("\n"))
    return p


@pytest.fixture
def project_with_aliases(tmp_path: Path) -> Iterator[tuple[Path, tuple[str, ...]]]:
    """Build a project where five route override files re-export one handler.

    The project layout is::

        tmp_path/
          routes/
            __init__.py
            underlying.py        # owns ``handler`` + has its own route header
            alpha.py             # `from routes.underlying import handler`
            beta.py              # ditto
            gamma.py
            delta.py
            epsilon.py

    ``tmp_path`` is added to ``sys.path`` so the alias files'
    ``from routes.underlying import handler`` resolves.
    """
    routes = tmp_path / "routes"
    routes.mkdir(parents=True)
    (routes / "__init__.py").write_text("")

    # Underlying surface owner — has its own route header AND defines ``handler``.
    _write_module(
        routes,
        "underlying.py",
        """
        # dazzle:route-override GET /app/workspaces/underlying
        async def handler(request):
            return {"served_from": "underlying"}
        """,
    )

    aliases = ("alpha", "beta", "gamma", "delta", "epsilon")
    for alias in aliases:
        _write_module(
            routes,
            f"{alias}.py",
            f"""
            # dazzle:route-override GET /app/workspaces/{alias}
            from routes.underlying import handler  # noqa: F401
            """,
        )

    sys.path.insert(0, str(tmp_path))
    try:
        yield tmp_path, aliases
    finally:
        try:
            sys.path.remove(str(tmp_path))
        except ValueError:
            pass
        # Drop any leaked module entries so other tests don't see them.
        for mod_name in list(sys.modules):
            if mod_name.startswith("routes") or mod_name.startswith("dazzle_routes."):
                del sys.modules[mod_name]


def test_route_override_aliases_via_reexport_resolve_to_separate_routes(
    project_with_aliases: tuple[Path, tuple[str, ...]],
) -> None:
    """Five files re-exporting the same handler must register five
    distinct route override descriptors, each with its own source path."""
    project_root, aliases = project_with_aliases
    routes = project_root / "routes"

    from dazzle.http.runtime.route_overrides import discover_route_overrides

    overrides = discover_route_overrides(routes)

    paths = sorted(o.path for o in overrides)
    expected_alias_paths = [f"/app/workspaces/{a}" for a in aliases]
    expected = sorted([*expected_alias_paths, "/app/workspaces/underlying"])
    assert paths == expected, (
        f"Expected six distinct paths (5 aliases + underlying), got {paths!r}. "
        "Re-exporting via `from X import handler` collapsed the entries."
    )

    # Each descriptor must record its OWN source file (not the underlying
    # module's file). This is the keying signal — overrides keyed by file
    # path keep aliases distinct even when the callable is shared.
    by_path = {o.path: o for o in overrides}
    for alias in aliases:
        descriptor = by_path[f"/app/workspaces/{alias}"]
        assert descriptor.source_path.name == f"{alias}.py", (
            f"Alias {alias} reports source {descriptor.source_path.name!r}, expected {alias}.py"
        )

    # Each alias must expose a DISTINCT handler callable so FastAPI sees
    # one endpoint object per route. Otherwise registration collapses
    # because the same function is registered five times — and any
    # framework feature that keys per-handler (dependency caching,
    # middleware wrappers) maps every alias onto the first registration.
    alias_handlers = [by_path[f"/app/workspaces/{a}"].handler for a in aliases]
    distinct_ids = {id(h) for h in alias_handlers}
    assert len(distinct_ids) == len(aliases), (
        f"Each alias must own a distinct handler callable. "
        f"Got {len(distinct_ids)} distinct callables for {len(aliases)} aliases — "
        "re-exports collapsed onto one identity (issue #1020)."
    )

    # Each alias handler must report its alias file as ``__module__``
    # (not the underlying module). This is the dispatch-keying contract.
    for alias in aliases:
        h = by_path[f"/app/workspaces/{alias}"].handler
        assert alias in getattr(h, "__module__", ""), (
            f"Alias {alias!r} handler.__module__={h.__module__!r} "
            f"must reference the alias file, not the underlying module."
        )


def test_route_override_aliases_register_distinct_fastapi_routes(
    project_with_aliases: tuple[Path, tuple[str, ...]],
) -> None:
    """build_override_router must register a separate APIRoute per alias path."""
    project_root, aliases = project_with_aliases
    routes = project_root / "routes"

    from dazzle.http.runtime.route_overrides import build_override_router

    router = build_override_router(routes)
    assert router is not None

    registered_paths = sorted(r.path for r in router.routes)  # type: ignore[attr-defined]
    expected_alias_paths = [f"/app/workspaces/{a}" for a in aliases]
    expected = sorted([*expected_alias_paths, "/app/workspaces/underlying"])
    assert registered_paths == expected, (
        f"FastAPI router did not register one route per alias; "
        f"got {registered_paths!r}, expected {expected!r}"
    )

    # Each route's endpoint must be its own callable — FastAPI keeps the
    # endpoint reference per APIRoute, and any per-handler wrapping or
    # dependency caching will misbehave if multiple routes share one.
    endpoints = [r.endpoint for r in router.routes]  # type: ignore[attr-defined]
    assert len({id(ep) for ep in endpoints}) == len(endpoints), (
        f"Endpoints must be unique per route. Got {len(endpoints)} routes "
        f"but {len({id(ep) for ep in endpoints})} distinct callables."
    )


def test_route_override_alias_handler_invokes_underlying(
    project_with_aliases: tuple[Path, tuple[str, ...]],
) -> None:
    """Each alias's wrapped handler must still produce the underlying body."""
    import asyncio

    project_root, aliases = project_with_aliases
    routes = project_root / "routes"

    from dazzle.http.runtime.route_overrides import discover_route_overrides

    overrides = discover_route_overrides(routes)
    by_path = {o.path: o for o in overrides}

    for alias in aliases:
        handler = by_path[f"/app/workspaces/{alias}"].handler
        # The underlying handler accepts a positional `request`.
        result = asyncio.run(handler(None))
        assert result == {"served_from": "underlying"}, (
            f"Alias {alias} handler did not delegate to underlying; got {result!r}"
        )
