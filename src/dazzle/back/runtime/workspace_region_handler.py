"""The workspace region handler — orchestration spine for `/region/<name>` GETs.

Extracted from ``workspace_rendering.py`` in #1057 cut 16 (v0.67.115).
After 15 prior cuts of code motion + decomposition, this handler is
a thin async orchestration over six phase functions, each of which
returns a typed dataclass:

1. ``resolve_request_user_context`` → ``RequestUserContext``
   (auth gate + DSL user resolution + filter context).
2. ``fetch_region_items`` → ``RegionItemsResult``
   (filters + sort + scope + ``repo.list``).
3. Column metadata — pre-computed visible-filtered columns from
   startup, or auto-derived from the first item's keys (#872).
4-5. ``compute_region_render_inputs`` → ``RegionRenderInputs``
   (every aggregate / bucketed / per-display compute the render
   tail consumes).
6. ``render_region_html`` → ``str`` (typed-primitive adapter
   build + ``FragmentRenderer.render`` + region-chrome wrap).

Reading top-to-bottom is the architecture. Each phase is in its own
sibling module; every boundary is a named dataclass — grep
``RegionItemsResult`` / ``RegionRenderInputs`` to find every reader.
"""

import logging
from typing import Any

from dazzle.back.runtime.workspace_context import WorkspaceRegionContext
from dazzle.back.runtime.workspace_csv import _render_csv_response
from dazzle.back.runtime.workspace_region_computes import compute_columns_for_persona
from dazzle.back.runtime.workspace_region_fetch import fetch_region_items
from dazzle.back.runtime.workspace_region_orchestration import compute_region_render_inputs
from dazzle.back.runtime.workspace_region_prelude import resolve_request_user_context
from dazzle.back.runtime.workspace_region_render import render_region_html

logger = logging.getLogger(__name__)


async def _workspace_region_handler(
    request: Any,
    page: int,
    page_size: int,
    sort: str | None,
    dir: str,
    *,
    ctx: WorkspaceRegionContext,
) -> Any:
    """Return rendered HTML for a workspace region.

    Six-phase orchestration — see the module docstring for the
    full pipeline. Each phase function lives in its own sibling
    module and returns a typed dataclass.
    """
    from fastapi.responses import HTMLResponse

    # Phase 1: auth gate + identity resolution + filter-context build.
    # Raises HTTPException(401/403) if the request is unauthorised.
    user_ctx = await resolve_request_user_context(request, ctx)

    # Phase 2: filters + sort + scope + repo.list. Returns the row
    # data plus the scope state downstream aggregate paths gate on.
    fetched = await fetch_region_items(request, ctx, user_ctx, sort, dir, page, page_size)

    # Phase 3: column metadata — pre-computed visible-filtered columns
    # from startup, or auto-derived from the first item's keys (#872).
    if ctx.precomputed_columns:
        columns = compute_columns_for_persona(
            ctx.precomputed_columns,
            list(user_ctx.auth_ctx_for_filters.roles) if user_ctx.auth_ctx_for_filters else [],
        )
    elif fetched.items:
        columns = [
            {
                "key": k,
                "label": k.replace("_", " ").title(),
                "type": "text",
                "sortable": True,
            }
            for k in fetched.items[0].keys()
            if k != "id"
        ]
    else:
        columns = []

    # CSV export (#562) — short-circuits the typed-primitive render.
    if request.query_params.get("format") == "csv":
        return _render_csv_response(fetched.items, columns, ctx.ctx_region.name)

    # Phases 4-5: build every shape the render tail consumes.
    render_inputs = await compute_region_render_inputs(request, ctx, user_ctx, fetched, columns)

    # Phase 6: typed-primitive render + region-chrome wrap.
    html_body = await render_region_html(request, ctx, user_ctx, render_inputs, sort, dir)
    return HTMLResponse(content=html_body)
