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

import html as _html_mod
import logging
from typing import Any

from dazzle.http.runtime.workspace_context import WorkspaceRegionContext
from dazzle.http.runtime.workspace_csv import _render_csv_response
from dazzle.http.runtime.workspace_region_computes import compute_columns_for_persona
from dazzle.http.runtime.workspace_region_fetch import fetch_region_items
from dazzle.http.runtime.workspace_region_orchestration import compute_region_render_inputs
from dazzle.http.runtime.workspace_region_prelude import resolve_request_user_context
from dazzle.http.runtime.workspace_region_render import render_region_html

logger = logging.getLogger(__name__)


def _row_status(row: Any, field_name: str) -> Any:
    """Read a row's status field, tolerating dict rows and entity objects (#1396)."""
    if isinstance(row, dict):
        return row.get(field_name)
    return getattr(row, field_name, None)


def _region_polling_complete(ctx: WorkspaceRegionContext, fetched: Any) -> bool:
    """#1399 slice 2: True when a polling region has nothing left to poll.

    The region's source entity has a state machine and EVERY fetched row is in
    a terminal state — so a finished pipeline isn't polled forever. Rule:
    INFERRED status field (the entity's single state-machine ``status_field``)
    + stop only when ALL rows are terminal.

    Conservative guards keep us from stopping prematurely:
    - only when the region actually polls (``refresh_interval`` set),
    - only when the source entity has a state machine,
    - only when the fetched page holds *every* matching row (a later page could
      still carry non-terminal rows),
    - never on an empty region (no rows yet ≠ done — the pipeline may not have
      started).
    """
    if not getattr(ctx.ir_region, "refresh_interval", None):
        return False
    sm = getattr(ctx.entity_spec, "state_machine", None) if ctx.entity_spec else None
    if sm is None:
        return False
    items = fetched.items
    if not items:
        return False
    if getattr(fetched, "total", len(items)) > len(items):
        return False
    terminal = sm.terminal_states()
    if not terminal:
        return False
    return all(_row_status(row, sm.status_field) in terminal for row in items)


def _build_region_response(
    ctx: WorkspaceRegionContext,
    fetched: Any,
    html_body: str,
    hx_target: str | None,
) -> Any:
    """Build the region-fetch HTTP response, stopping the poll when complete.

    #1399 slice 2 — htmx-native poll-stop. htmx 4 removed the legacy HTTP-286
    poll-cancel, so we stop via self-replacement instead: when the region is
    complete, swap the *polling element itself* (the ``dz-card-body`` that
    carries the ``every Ns`` trigger) for a triggerless copy via
    ``HX-Reswap: outerHTML``. The old element leaves the DOM, so htmx's
    ``setInterval(... e.isConnected ? rearm : clearInterval ...)`` self-clears
    the poll; the new element has no trigger to re-arm.

    The replacement preserves the element's id (read from the ``HX-Target``
    request header, so multi-card regions each keep their own id), classes, and
    ``data-display`` so layout/styling are unchanged. If ``HX-Target`` is absent
    (no element id), we can't safely outerHTML-replace, so we fall back to the
    normal innerHTML body and the region simply keeps polling — a safe no-op.
    """
    from fastapi.responses import HTMLResponse

    if hx_target and _region_polling_complete(ctx, fetched):
        display = str(getattr(ctx.ctx_region, "display", "") or "").lower()
        replacement = (
            f'<div class="dz-card-body" id="{_html_mod.escape(hx_target, quote=True)}" '
            f'data-display="{_html_mod.escape(display, quote=True)}" '
            f'data-dz-poll-complete="true">{html_body}</div>'
        )
        return HTMLResponse(content=replacement, headers={"HX-Reswap": "outerHTML"})
    return HTMLResponse(content=html_body)


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

    # #1399 slice 2: stop polling a finished region (htmx-native self-replace).
    return _build_region_response(ctx, fetched, html_body, request.headers.get("hx-target"))
