"""Pure route ownership rules shared by compilation and inspection."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.ir import SurfaceMode
from dazzle.core.ir.appspec import AppSpec
from dazzle.page import app_paths


def surface_route(surface: ir.SurfaceSpec, app_prefix: str, entity_name: str) -> str:
    """The page URL compiled for one surface."""
    slug = app_paths.entity_slug(entity_name)
    routes = {
        SurfaceMode.LIST: app_paths.list_path(app_prefix, slug),
        SurfaceMode.CREATE: app_paths.create_path(app_prefix, slug),
        SurfaceMode.EDIT: app_paths.edit_path(app_prefix, slug),
        SurfaceMode.VIEW: app_paths.detail_path(app_prefix, slug),
    }
    return routes.get(surface.mode, f"/{surface.name}")


def surface_wins(candidate: ir.SurfaceSpec, incumbent: ir.SurfaceSpec) -> bool:
    """Match the page compiler's collision rule; first declaration wins ties."""
    return (bool(candidate.render), bool(candidate.sections)) > (
        bool(incumbent.render),
        bool(incumbent.sections),
    )


def _declared_routes(
    appspec: AppSpec, app_prefix: str
) -> tuple[dict[str, ir.SurfaceSpec], set[str]]:
    owners: dict[str, ir.SurfaceSpec] = {}
    list_entities: set[str] = set()
    for surface in appspec.surfaces:
        entity = appspec.domain.get_entity(surface.entity_ref) if surface.entity_ref else None
        entity_name = entity.name if entity else (surface.entity_ref or "item")
        route = surface_route(surface, app_prefix, entity_name)
        incumbent = owners.get(route)
        if incumbent is None or surface_wins(surface, incumbent):
            owners[route] = surface
        if surface.mode == SurfaceMode.LIST and surface.entity_ref:
            list_entities.add(surface.entity_ref)
    return owners, list_entities


def _synthetic_detail_routes(
    appspec: AppSpec, app_prefix: str, owners: dict[str, ir.SurfaceSpec], list_entities: set[str]
) -> None:
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.source:
                list_entities.add(region.source)
    for entity_ref in sorted(list_entities):
        entity = appspec.domain.get_entity(entity_ref)
        if entity is None:
            continue
        slug = app_paths.entity_slug(entity.name)
        route = app_paths.detail_path(app_prefix, slug)
        owners.setdefault(
            route,
            ir.SurfaceSpec(name=f"{slug}_detail", entity_ref=entity.name, mode=SurfaceMode.VIEW),
        )


def page_route_owners(appspec: AppSpec, app_prefix: str) -> dict[str, ir.SurfaceSpec]:
    """Resolve compiled page URL owners, including synthetic detail pages."""
    owners, list_entities = _declared_routes(appspec, app_prefix)

    if not appspec.workspaces:
        first_list = next((s for s in appspec.surfaces if s.mode == SurfaceMode.LIST), None)
        if first_list is not None:
            owners.setdefault("/", first_list)

    _synthetic_detail_routes(appspec, app_prefix, owners, list_entities)
    return owners
