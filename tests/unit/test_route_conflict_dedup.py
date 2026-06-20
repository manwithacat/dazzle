"""Regression tests for #1101 — duplicate route mounting.

Two scenarios:

1. `convert_surfaces_to_services` deduplicates endpoints by ``(method, path)``
   so two surfaces that compile to the same HTTP shape don't both register.

2. `RouteGenerator.generate_all_routes` respects a ``claimed_routes`` set so
   project-route overrides aren't shadowed by a generic CRUD mount on the
   same path — the override is the intended handler and the duplicate mount
   would only fire ``Route conflict`` warnings on every boot.
"""

from fastapi import APIRouter, FastAPI

from dazzle.core import ir
from dazzle.http.converters.surface_converter import (
    _dedupe_endpoints,
    convert_surfaces_to_services,
)
from dazzle.http.runtime.route_validator import validate_routes
from dazzle.http.specs import EndpointSpec, HttpMethod


def _make_edit_surface(name: str, entity: str) -> ir.SurfaceSpec:
    return ir.SurfaceSpec(
        name=name,
        title=f"{entity} {name}",
        entity_ref=entity,
        mode=ir.SurfaceMode.EDIT,
    )


def test_dedupe_endpoints_drops_same_method_path() -> None:
    """Two surfaces with the same (method, path) collapse to one endpoint."""
    a = EndpointSpec(name="edit_a", service="svc_a", method=HttpMethod.PUT, path="/widgets/{id}")
    b = EndpointSpec(name="edit_b", service="svc_b", method=HttpMethod.PUT, path="/widgets/{id}")
    c = EndpointSpec(
        name="view_widget", service="svc_c", method=HttpMethod.GET, path="/widgets/{id}"
    )
    deduped = _dedupe_endpoints([a, b, c])
    # `b` is dropped (same key as `a`), `a` and `c` survive
    assert [ep.name for ep in deduped] == ["edit_a", "view_widget"]


def test_convert_surfaces_dedupes_two_edit_surfaces_same_entity() -> None:
    """Two EDIT surfaces on one entity produce one PUT, not two (#1101)."""
    surfaces = [
        _make_edit_surface("widget_edit", "Widget"),
        _make_edit_surface("widget_admin_edit", "Widget"),
    ]
    _services, endpoints = convert_surfaces_to_services(surfaces, domain=None)
    put_endpoints = [ep for ep in endpoints if ep.method == HttpMethod.PUT]
    assert len(put_endpoints) == 1, [ep.name for ep in put_endpoints]
    assert put_endpoints[0].path == "/widgets/{id}"


def test_generate_all_routes_skips_claimed_routes() -> None:
    """A claimed (method, path) is skipped by generate_all_routes — `generate_route` never sees it."""
    from unittest.mock import patch

    from dazzle.http.runtime.route_generator import RouteGenerator

    generator = RouteGenerator(
        services={},
        models={},
        schemas={},
        entity_access_specs={},
        auth_dep=None,
        optional_auth_dep=None,
    )

    skipped = EndpointSpec(
        name="list_things", service="list_things", method=HttpMethod.GET, path="/things"
    )

    with patch.object(generator, "generate_route") as spy:
        generator.generate_all_routes(
            [skipped],
            service_specs={},
            claimed_routes={("GET", "/things")},
        )
    assert spy.call_count == 0, "claimed endpoint should be skipped"


def test_app_with_override_emits_zero_conflicts() -> None:
    """End-to-end: an override + a generic CRUD with the same path produce 0 conflicts."""
    app = FastAPI()
    # Simulate a project override
    override = APIRouter(tags=["Project Overrides"])

    @override.get("/things")
    async def my_override() -> dict[str, str]:
        return {"hi": "there"}

    app.include_router(override)

    # Build a tiny CRUD router via generate_all_routes, with the claimed set
    # the server.py wiring would produce.
    from dazzle.http.runtime.route_generator import RouteGenerator

    generator = RouteGenerator(
        services={},
        models={},
        schemas={},
        entity_access_specs={},
        auth_dep=None,
        optional_auth_dep=None,
    )
    crud = EndpointSpec(
        name="list_things",
        service="list_things",
        method=HttpMethod.GET,
        path="/things",
    )

    claimed: set[tuple[str, str]] = set()
    for route in app.routes:
        for method in getattr(route, "methods", None) or ():
            claimed.add((method, getattr(route, "path", "")))

    router = generator.generate_all_routes([crud], service_specs={}, claimed_routes=claimed)
    app.include_router(router)

    conflicts = validate_routes(app)
    assert conflicts == [], f"expected zero conflicts, got: {conflicts}"
