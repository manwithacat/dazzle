"""Workspace route builder — workspace region and entity redirect routes.

Houses ``WorkspaceRouteBuilder`` which was previously defined inline in
``server.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from dazzle.core.ir import AppSpec
from dazzle_back.runtime.auth import AuthMiddleware
from dazzle_back.runtime.workspace_rendering import (
    WorkspaceRegionContext,
    _build_entity_columns,
    _build_surface_columns,
    _workspace_batch_handler,
    _workspace_region_handler,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# FastAPI Request — imported lazily to avoid hard dependency at module level
try:
    from fastapi import Request
except ImportError:
    Request = None  # type: ignore


class WorkspaceRouteBuilder:
    """Registers workspace region and entity redirect routes for DazzleBackendApp."""

    def __init__(
        self,
        *,
        app: FastAPI,
        appspec: AppSpec,
        entities: list[Any],
        repositories: dict[str, Any],
        auth_middleware: AuthMiddleware | None,
        enable_auth: bool,
        enable_test_mode: bool,
        entity_auto_includes: dict[str, list[str]] | None = None,
        user_entity_name: str = "User",
    ) -> None:
        self._app = app
        self._appspec = appspec
        self._entities = entities
        self._repositories = repositories
        self._auth_middleware = auth_middleware
        self._enable_auth = enable_auth
        self._enable_test_mode = enable_test_mode
        self._entity_auto_includes = entity_auto_includes or {}
        self._fk_graph = getattr(appspec, "fk_graph", None)
        self._user_entity_name = user_entity_name

    def init_workspace_routes(self) -> None:
        """Initialize workspace layout routes (v0.20.0)."""
        if not self._app:
            return

        workspaces = self._appspec.workspaces
        if not workspaces:
            logging.getLogger("dazzle.server").debug(
                "No workspaces in spec — skipping workspace routes"
            )
            return

        try:
            from dazzle_ui.runtime.workspace_renderer import build_workspace_context

            app = self._app
            appspec = self._appspec
            entities = self._entities
            repositories = self._repositories
            auth_middleware = self._auth_middleware
            entity_auto_includes = self._entity_auto_includes

            require_auth = self._enable_auth and not self._enable_test_mode

            # Build entity → list surface lookup for column projection (#357, #359)
            _entity_list_surfaces: dict[str, Any] = {}
            for _surf in appspec.surfaces:
                _eref = _surf.entity_ref
                _mode = str(_surf.mode or "").lower()
                if _eref and _mode == "list" and _eref not in _entity_list_surfaces:
                    _entity_list_surfaces[_eref] = _surf

            def _columns_for_entity(entity_spec: Any, entity_name: str) -> list[dict[str, Any]]:
                """Build columns using list surface projection if available."""
                _ls = _entity_list_surfaces.get(entity_name)
                if _ls and entity_spec:
                    return _build_surface_columns(entity_spec, _ls)
                return _build_entity_columns(entity_spec)

            for workspace in workspaces:
                ws_ctx = build_workspace_context(workspace, appspec)
                ws_name = workspace.name

                _ws_access = workspace.access
                _ws_region_ctxs: list[WorkspaceRegionContext] = []

                for ir_region, ctx_region in zip(workspace.regions, ws_ctx.regions, strict=False):
                    # Multi-source regions: register per-source sub-endpoints
                    if ctx_region.sources:
                        source_filters_ir = dict(getattr(ir_region, "source_filters", {}) or {})
                        for src_tab in ctx_region.source_tabs:
                            _src_name = src_tab.entity_name
                            _src_entity_spec = None
                            for _e in entities:
                                if _e.name == _src_name:
                                    _src_entity_spec = _e
                                    break

                            # Build a synthetic single-source IR region for this tab
                            _src_filter = source_filters_ir.get(
                                _src_name, getattr(ir_region, "filter", None)
                            )

                            # Per-source tab uses tab_data.html (not tabbed_list.html)
                            # to avoid infinite HTMX loop (#328)
                            _tab_endpoint = (
                                f"/api/workspaces/{ws_name}/regions/{ctx_region.name}/{_src_name}"
                            )
                            _src_ctx_region = ctx_region.model_copy(
                                update={
                                    "template": "workspace/regions/tab_data.html",
                                    "endpoint": _tab_endpoint,
                                    "source_tabs": [],
                                }
                            )
                            _src_region_ctx = WorkspaceRegionContext(
                                ctx_region=_src_ctx_region,
                                ir_region=ir_region,
                                source=_src_name,
                                entity_spec=_src_entity_spec,
                                attention_signals=[],
                                ws_access=_ws_access,
                                repositories=repositories,
                                require_auth=require_auth,
                                auth_middleware=auth_middleware,
                                precomputed_columns=_columns_for_entity(
                                    _src_entity_spec, _src_name
                                ),
                                auto_include=entity_auto_includes.get(_src_name, []),
                                cedar_access_spec=getattr(_src_entity_spec, "access", None),
                                fk_graph=self._fk_graph,
                                user_entity_name=self._user_entity_name,
                            )
                            # Override the IR filter for this source
                            _src_region_ctx._source_filter = _src_filter  # type: ignore[attr-defined]
                            _ws_region_ctxs.append(_src_region_ctx)

                            def _make_src_route(
                                rctx: WorkspaceRegionContext,
                                src_filter: Any = _src_filter,
                            ) -> Any:
                                async def workspace_src_data(
                                    request: Request,
                                    page: int = 1,
                                    page_size: int = 20,
                                    sort: str | None = None,
                                    dir: str = "asc",
                                ) -> Any:
                                    return await _workspace_region_handler(
                                        request,
                                        page,
                                        page_size,
                                        sort,
                                        dir,
                                        ctx=rctx,
                                    )

                                return workspace_src_data

                            app.get(
                                f"/api/workspaces/{ws_name}/regions/{ctx_region.name}/{_src_name}",
                                tags=["Workspaces"],
                            )(_make_src_route(_src_region_ctx))
                        continue

                    if not ctx_region.source:
                        continue

                    _source = ctx_region.source

                    _entity_spec = None
                    for _e in entities:
                        if _e.name == _source:
                            _entity_spec = _e
                            break

                    _attention_signals: list[Any] = []
                    _surface_default_sort: list[Any] = []
                    _surface_empty_message = ""
                    for _surf in appspec.surfaces:
                        if _surf.entity_ref == _source:
                            ux = getattr(_surf, "ux", None)
                            if ux:
                                if getattr(ux, "attention_signals", None):
                                    _attention_signals = list(ux.attention_signals)
                                if getattr(ux, "sort", None):
                                    _surface_default_sort = list(ux.sort)
                                if getattr(ux, "empty_message", None):
                                    _surface_empty_message = ux.empty_message

                    _columns = _columns_for_entity(_entity_spec, _source)

                    _region_ctx = WorkspaceRegionContext(
                        ctx_region=ctx_region,
                        ir_region=ir_region,
                        source=_source,
                        entity_spec=_entity_spec,
                        attention_signals=_attention_signals,
                        ws_access=_ws_access,
                        repositories=repositories,
                        require_auth=require_auth,
                        auth_middleware=auth_middleware,
                        precomputed_columns=_columns,
                        auto_include=entity_auto_includes.get(_source, []),
                        surface_default_sort=_surface_default_sort,
                        surface_empty_message=_surface_empty_message,
                        cedar_access_spec=getattr(_entity_spec, "access", None),
                        fk_graph=self._fk_graph,
                        user_entity_name=self._user_entity_name,
                    )
                    _ws_region_ctxs.append(_region_ctx)

                    # Use a factory to bind each region context via closure
                    # instead of a default parameter — FastAPI deepcopies
                    # defaults, which fails on non-picklable PGconn objects (#290).
                    def _make_region_route(rctx: WorkspaceRegionContext) -> Any:
                        async def workspace_region_data(
                            request: Request,
                            page: int = 1,
                            page_size: int = 20,
                            sort: str | None = None,
                            dir: str = "asc",
                        ) -> Any:
                            return await _workspace_region_handler(
                                request,
                                page,
                                page_size,
                                sort,
                                dir,
                                ctx=rctx,
                            )

                        return workspace_region_data

                    app.get(
                        f"/api/workspaces/{ws_name}/regions/{ctx_region.name}",
                        tags=["Workspaces"],
                    )(_make_region_route(_region_ctx))

                # Batch endpoint: collect all region contexts (already built above)
                _batch_ctxs = list(_ws_region_ctxs)

                def _make_batch_route(
                    ctxs: list[WorkspaceRegionContext],
                ) -> Any:
                    async def workspace_batch(
                        request: Request,
                        page: int = 1,
                        page_size: int = 20,
                    ) -> Any:
                        return await _workspace_batch_handler(request, page, page_size, ctxs)

                    return workspace_batch

                app.get(
                    f"/api/workspaces/{ws_name}/batch",
                    tags=["Workspaces"],
                )(_make_batch_route(_batch_ctxs))

                # Context selector options endpoint (v0.38.0)
                _ctx_sel = workspace.context_selector
                if _ctx_sel and repositories.get(_ctx_sel.entity):
                    _sel_repo = repositories[_ctx_sel.entity]
                    _sel_display = _ctx_sel.display_field

                    # Find entity spec for scope enforcement
                    _sel_entity_spec = next(
                        (e for e in entities if e.name == _ctx_sel.entity), None
                    )
                    _sel_access = (
                        getattr(_sel_entity_spec, "access", None) if _sel_entity_spec else None
                    )

                    def _make_context_options_route(
                        sel_repo: Any,
                        display: str,
                        sel_access: Any = None,
                        sel_auth_mw: Any = None,
                        sel_entity_name: str = "",
                        sel_fk_graph: Any = None,
                        sel_scope_field: str | None = None,
                    ) -> Any:
                        async def context_options(request: Request) -> Any:
                            from fastapi.responses import JSONResponse

                            # SECURITY: apply scope predicates to context selector (#574)
                            scope_filters: dict[str, Any] | None = None
                            if sel_access and sel_auth_mw and getattr(sel_access, "scopes", None):
                                try:
                                    auth_ctx = sel_auth_mw.get_auth_context(request)
                                    user_id = (
                                        getattr(auth_ctx, "user_id", None) if auth_ctx else None
                                    )
                                    if user_id and auth_ctx:
                                        from dazzle_back.runtime.route_generator import (
                                            _normalize_role,
                                            _resolve_scope_filters,
                                        )

                                        user_roles: set[str] = set()
                                        user_obj = getattr(auth_ctx, "user", None)
                                        if user_obj:
                                            for r in getattr(user_obj, "roles", []):
                                                rname = (
                                                    r
                                                    if isinstance(r, str)
                                                    else getattr(r, "name", str(r))
                                                )
                                                user_roles.add(_normalize_role(rname))
                                        scope_result = _resolve_scope_filters(
                                            sel_access,
                                            "list",
                                            user_roles,
                                            user_id,
                                            auth_ctx,
                                            entity_name=sel_entity_name,
                                            fk_graph=sel_fk_graph,
                                        )
                                        if scope_result is None:
                                            return JSONResponse(content={"options": []})
                                        if scope_result:
                                            scope_filters = scope_result
                                except Exception:
                                    pass  # Fall through to unscoped if auth fails

                            # Apply scope_field filter: restrict options by
                            # matching FK field to current user's attribute (#634)
                            if sel_scope_field and sel_auth_mw:
                                try:
                                    auth_ctx = (
                                        auth_ctx
                                        if "auth_ctx" in dir()
                                        else sel_auth_mw.get_auth_context(request)
                                    )
                                    user_obj = getattr(auth_ctx, "user", None) if auth_ctx else None
                                    if user_obj:
                                        user_val = getattr(user_obj, sel_scope_field, None)
                                        if user_val is None and isinstance(user_obj, dict):
                                            user_val = user_obj.get(sel_scope_field)
                                        if user_val:
                                            sf = scope_filters or {}
                                            sf[sel_scope_field] = str(user_val)
                                            scope_filters = sf
                                except Exception:
                                    pass

                            result = await sel_repo.list(
                                page=1, page_size=500, filters=scope_filters
                            )
                            items = result.get("items", []) if isinstance(result, dict) else result
                            options = []
                            for row in items:
                                r = row if isinstance(row, dict) else row.model_dump()
                                options.append(
                                    {
                                        "id": str(r.get("id", "")),
                                        "label": str(r.get(display, r.get("name", ""))),
                                    }
                                )
                            return JSONResponse(content={"options": options})

                        return context_options

                    app.get(
                        f"/api/workspaces/{ws_name}/context-options",
                        tags=["Workspaces"],
                    )(
                        _make_context_options_route(
                            _sel_repo,
                            _sel_display,
                            sel_access=_sel_access,
                            sel_auth_mw=auth_middleware,
                            sel_entity_name=_ctx_sel.entity,
                            sel_fk_graph=self._fk_graph,
                            sel_scope_field=_ctx_sel.scope_field,
                        )
                    )

                self._init_workspace_entity_routes(workspaces, app)

            logging.getLogger("dazzle.server").info(
                "Workspace routes initialized for %s workspace(s)",
                len(workspaces),
            )

        except ImportError as e:
            logging.getLogger("dazzle.server").debug("Workspace renderer not available: %s", e)

        except Exception:
            logging.getLogger("dazzle.server").error(
                "Failed to init workspace routes",
                exc_info=True,
            )

    def _init_workspace_entity_routes(self, workspaces: list[Any], app: Any) -> None:
        """Register workspace-prefixed entity routes (v0.20.1)."""
        from starlette.responses import RedirectResponse

        from dazzle.core.strings import to_api_plural

        seen: set[str] = set()

        for workspace in workspaces:
            ws_name = workspace.name
            for region in workspace.regions:
                source: str | None = region.source
                if not source:
                    continue

                entity_plural = to_api_plural(source)
                route_key = f"{ws_name}/{entity_plural}"
                if route_key in seen:
                    continue
                seen.add(route_key)

                _entity_plural = entity_plural

                @app.api_route(  # type: ignore[misc, untyped-decorator, unused-ignore]
                    f"/{ws_name}/{entity_plural}",
                    methods=["GET", "POST"],
                    tags=["Workspaces"],
                    include_in_schema=False,
                )
                async def ws_entity_collection(
                    _ep: str = _entity_plural,
                ) -> RedirectResponse:
                    # _ep is a compile-time slug from entity names — no user input involved.
                    return RedirectResponse(url=f"/{_ep}", status_code=307)

                @app.api_route(  # type: ignore[misc, untyped-decorator, unused-ignore]
                    f"/{ws_name}/{entity_plural}/{{id}}",
                    methods=["GET", "PUT", "PATCH", "DELETE"],
                    tags=["Workspaces"],
                    include_in_schema=False,
                )
                async def ws_entity_item(
                    id: str,
                    _ep: str = _entity_plural,
                ) -> RedirectResponse:
                    # Validate id is a bare UUID/slug (no slashes, no scheme).
                    # Reject anything that looks like a path traversal or URL.
                    safe_id = id.split("/")[0].split("?")[0].split("#")[0]
                    return RedirectResponse(url=f"/{_ep}/{safe_id}", status_code=307)
