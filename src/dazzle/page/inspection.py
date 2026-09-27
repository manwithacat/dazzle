"""Explain a page URL from the same AppSpec projection used by page routes."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID

from pydantic import BaseModel, Field

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.location import SourceLocation
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec
from dazzle.core.strings import to_api_plural
from dazzle.page.route_owners import page_route_owners


class PageDependency(BaseModel):
    """A declaration directly referenced by the page owner."""

    kind: str
    name: str
    source: str | None = None


class PageRegionTrace(BaseModel):
    """One workspace region's authored and mounted request path."""

    name: str
    display: str
    endpoint: str
    source_name: str | None = None
    source_declaration: str | None = None
    filter_ir: dict[str, object] | None = None
    sort_ir: list[dict[str, object]] = Field(default_factory=list)
    limit: int | None = None
    workspace_access: str
    allowed_personas: list[str] = Field(default_factory=list)
    list_permission_ir: list[dict[str, object]] = Field(default_factory=list)
    list_scope_ir: list[dict[str, object]] = Field(default_factory=list)
    action_surface: str | None = None
    action_declaration: str | None = None
    action_route: str | None = None
    mutation_method: str | None = None
    mutation_endpoint: str | None = None


class PageExplanation(BaseModel):
    """Read-only route provenance; no generated page file is maintained."""

    requested_url: str
    route_pattern: str
    kind: str
    name: str
    title: str
    source: str | None = None
    module: str | None = None
    entity: str | None = None
    mode: str | None = None
    dependencies: list[PageDependency] = Field(default_factory=list)
    generated: bool = False
    region: PageRegionTrace | None = None


def _source_path(source: SourceLocation | None, project_root: Path) -> str | None:
    if source is None:
        return None
    path = Path(source.file)
    if path.is_absolute():
        try:
            path = path.relative_to(project_root)
        except ValueError:
            pass
    return f"{path}:{source.line}"


def _source_module(source: SourceLocation | None, project_root: Path) -> str | None:
    if source is None:
        return None
    path = Path(source.file)
    if not path.is_absolute():
        path = project_root / path
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^module\s+([A-Za-z_][\w.]*)\s*$", line)
        if match:
            return match.group(1)
    return None


def _route_matches(pattern: str, path: str) -> bool:
    pattern_parts = (pattern.rstrip("/") or "/").split("/")
    path_parts = (path.rstrip("/") or "/").split("/")
    if len(pattern_parts) != len(path_parts):
        return False
    for template, actual in zip(pattern_parts, path_parts, strict=True):
        if template == "{id}":
            try:
                UUID(actual)
            except ValueError:
                return False
        elif template != actual:
            return False
    return True


def _dependencies(appspec: AppSpec, refs: list[str], project_root: Path) -> list[PageDependency]:
    declarations = {
        **{e.name: ("entity", e.source) for e in appspec.domain.entities},
        **{s.name: ("surface", s.source) for s in appspec.surfaces},
        **{w.name: ("workspace", w.source) for w in appspec.workspaces},
    }
    seen: set[str] = set()
    result: list[PageDependency] = []
    for ref in refs:
        if ref in seen or ref not in declarations:
            continue
        seen.add(ref)
        kind, source = declarations[ref]
        result.append(
            PageDependency(kind=kind, name=ref, source=_source_path(source, project_root))
        )
    return result


def _workspace_explanation(
    appspec: AppSpec, workspace: WorkspaceSpec, requested_url: str, pattern: str, project_root: Path
) -> PageExplanation:
    refs: list[str] = []
    for region in workspace.regions:
        refs.extend(
            ref
            for ref in (
                region.source,
                *region.sources,
                region.action,
                region.primary_action,
                region.secondary_action,
                region.revoke,
            )
            if ref
        )
    refs.extend(action.target for action in workspace.primary_actions)
    for group in workspace.nav_groups:
        refs.extend(item.entity for item in group.items)
    return PageExplanation(
        requested_url=requested_url,
        route_pattern=pattern,
        kind="workspace",
        name=workspace.name,
        title=workspace.title or workspace.name,
        source=_source_path(workspace.source, project_root),
        module=_source_module(workspace.source, project_root),
        dependencies=_dependencies(appspec, refs, project_root),
    )


def _surface_explanation(
    appspec: AppSpec, owner: SurfaceSpec, requested_url: str, pattern: str, project_root: Path
) -> PageExplanation:
    surface = next((s for s in appspec.surfaces if s is owner), None)
    if surface is None:
        entity = appspec.domain.get_entity(owner.entity_ref) if owner.entity_ref else None
        return PageExplanation(
            requested_url=requested_url,
            route_pattern=pattern,
            kind="generated detail",
            name=owner.name,
            title=entity.title or entity.name if entity else owner.name,
            source=_source_path(entity.source, project_root) if entity else None,
            module=_source_module(entity.source, project_root) if entity else None,
            entity=owner.entity_ref or None,
            mode="view",
            generated=True,
        )
    return PageExplanation(
        requested_url=requested_url,
        route_pattern=pattern,
        kind="surface",
        name=surface.name,
        title=surface.title or surface.name,
        source=_source_path(surface.source, project_root),
        module=_source_module(surface.source, project_root),
        entity=surface.entity_ref,
        mode=surface.mode.value,
        dependencies=_dependencies(
            appspec, [surface.entity_ref] if surface.entity_ref else [], project_root
        ),
    )


def explain_page(
    appspec: AppSpec, requested_url: str, project_root: Path, *, app_prefix: str = "/app"
) -> PageExplanation | None:
    """Resolve a URL to its winning workspace or surface declaration."""
    path = unquote(urlsplit(requested_url).path)
    if not path.startswith("/"):
        return None
    normalized = path.rstrip("/") or "/"
    prefix = app_prefix.rstrip("/")
    for workspace in appspec.workspaces:
        pattern = f"{prefix}/workspaces/{workspace.name}"
        if _route_matches(pattern, normalized):
            return _workspace_explanation(appspec, workspace, requested_url, pattern, project_root)
    owners = page_route_owners(appspec, prefix)
    sorted_owners = sorted(
        owners.items(), key=lambda item: (-item[0].count("/"), 0 if "{" not in item[0] else 1)
    )
    for pattern, owner in sorted_owners:
        if _route_matches(pattern, normalized):
            return _surface_explanation(appspec, owner, requested_url, pattern, project_root)
    return None


def _region_action_trace(
    appspec: AppSpec, region: WorkspaceRegion, app_prefix: str
) -> tuple[str | None, SurfaceSpec | None, str | None, str | None, str | None]:
    action_name = region.action or region.primary_action
    action_surface = next((s for s in appspec.surfaces if s.name == action_name), None)
    action_route = next(
        (
            route
            for route, owner in page_route_owners(appspec, app_prefix.rstrip("/")).items()
            if owner is action_surface
        ),
        None,
    )
    mutation_method: str | None = None
    mutation_endpoint: str | None = None
    if action_surface and action_surface.entity_ref:
        endpoint = f"/{to_api_plural(action_surface.entity_ref)}"
        if action_surface.mode == SurfaceMode.CREATE:
            mutation_method, mutation_endpoint = "POST", endpoint
        elif action_surface.mode == SurfaceMode.EDIT:
            mutation_method, mutation_endpoint = "PUT", f"{endpoint}/{{id}}"
    return action_name, action_surface, action_route, mutation_method, mutation_endpoint


def _region_list_policy_ir(
    appspec: AppSpec, region: WorkspaceRegion
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    source_entity = appspec.domain.get_entity(region.source) if region.source else None
    source_access = source_entity.access if source_entity else None
    if source_access is None:
        return [], []
    return (
        [
            rule.model_dump(mode="json")
            for rule in source_access.permissions
            if rule.operation.value == "list"
        ],
        [
            rule.model_dump(mode="json", exclude={"predicate"})
            for rule in source_access.scopes
            if rule.operation.value == "list"
        ],
    )


def explain_workspace_region(
    appspec: AppSpec,
    page: PageExplanation,
    region_name: str,
    project_root: Path,
    *,
    app_prefix: str = "/app",
) -> PageRegionTrace | None:
    """Project a named region from AppSpec using the registered URL convention.

    This is a static explanation of the request contract. Actual rows and
    permission outcomes depend on the current user and running server.
    """
    if page.kind != "workspace":
        return None
    workspace = next((ws for ws in appspec.workspaces if ws.name == page.name), None)
    if workspace is None:
        return None
    region = workspace.get_region(region_name)
    if region is None:
        return None

    declarations = {
        **{entity.name: entity.source for entity in appspec.domain.entities},
        **{surface.name: surface.source for surface in appspec.surfaces},
    }
    action_name, action_surface, action_route, mutation_method, mutation_endpoint = (
        _region_action_trace(appspec, region, app_prefix)
    )
    access = workspace.access
    list_permission_ir, list_scope_ir = _region_list_policy_ir(appspec, region)
    return PageRegionTrace(
        name=region.name,
        display=region.display.value,
        endpoint=f"/api/workspaces/{workspace.name}/regions/{region.name}",
        source_name=region.source,
        source_declaration=_source_path(
            declarations.get(region.source) if region.source else None, project_root
        ),
        filter_ir=region.filter.model_dump(mode="json") if region.filter else None,
        sort_ir=[item.model_dump(mode="json") for item in region.sort],
        limit=region.limit,
        workspace_access=access.level.value if access else "authenticated",
        allowed_personas=list(access.allow_personas) if access else [],
        list_permission_ir=list_permission_ir,
        list_scope_ir=list_scope_ir,
        action_surface=action_name,
        action_declaration=_source_path(action_surface.source, project_root)
        if action_surface
        else None,
        action_route=action_route,
        mutation_method=mutation_method,
        mutation_endpoint=mutation_endpoint,
    )
