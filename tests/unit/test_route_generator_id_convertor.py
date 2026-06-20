"""#1167: detail routes use Starlette's `uuid` path convertor.

`/{plural}/{id}` registers as `/{plural}/{id:uuid}`, so a literal
segment like `create` can't be mistaken for an `{id}` — it doesn't
match the convertor and falls through to a clean router 404. This
retired the `_create_guard` sentinel routes (#598): routes whose only
job was to return 404 so `create` wouldn't be parsed as a UUID.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from dazzle.http.runtime.route_generator import RouteGenerator  # noqa: E402
from dazzle.http.specs import EndpointSpec, HttpMethod  # noqa: E402


def _generator() -> RouteGenerator:
    return RouteGenerator(
        services={},
        models={},
        schemas={},
        entity_access_specs={},
        auth_dep=None,
        optional_auth_dep=None,
    )


def test_detail_route_registers_with_uuid_convertor() -> None:
    """`_add_route` rewrites the `{id}` segment to `{id:uuid}`."""
    generator = _generator()
    endpoint = EndpointSpec(
        name="get_task", service="svc", method=HttpMethod.GET, path="/tasks/{id}"
    )

    async def _handler(id: str) -> None: ...

    generator._add_route(endpoint, _handler)

    paths = [getattr(r, "path", "") for r in generator.router.routes]
    assert "/tasks/{id:uuid}" in paths
    assert "/tasks/{id}" not in paths


def test_list_route_path_is_untouched() -> None:
    """A path with no `{id}` segment is registered verbatim."""
    generator = _generator()
    endpoint = EndpointSpec(name="list_tasks", service="svc", method=HttpMethod.GET, path="/tasks")

    async def _handler() -> None: ...

    generator._add_route(endpoint, _handler)

    assert "/tasks" in [getattr(r, "path", "") for r in generator.router.routes]


def test_no_create_guard_routes_registered() -> None:
    """The `/{plural}/create` sentinel guard routes are gone — a GET
    `{id}` endpoint no longer spawns a `Guard`-tagged companion route."""
    generator = _generator()
    detail = EndpointSpec(name="get_task", service="svc", method=HttpMethod.GET, path="/tasks/{id}")

    with patch.object(generator, "generate_route"):
        generator.generate_all_routes([detail], service_specs={})

    guard_routes = [
        getattr(r, "path", "")
        for r in generator.router.routes
        if "Guard" in (getattr(r, "tags", None) or [])
    ]
    assert not guard_routes, f"expected no guard routes, found {guard_routes}"
