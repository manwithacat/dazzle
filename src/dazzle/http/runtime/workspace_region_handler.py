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

import asyncio
import html as _html_mod
import logging
from typing import Any
from urllib.parse import unquote

from dazzle.core.ir import WhenEmpty
from dazzle.http.runtime.workspace_context import WorkspaceRegionContext
from dazzle.http.runtime.workspace_csv import _render_csv_response
from dazzle.http.runtime.workspace_region_computes import compute_columns_for_persona
from dazzle.http.runtime.workspace_region_fetch import fetch_region_items
from dazzle.http.runtime.workspace_region_orchestration import compute_region_render_inputs
from dazzle.http.runtime.workspace_region_prelude import resolve_request_user_context
from dazzle.http.runtime.workspace_region_render import (
    is_list_rows_request,
    render_region_html,
)
from dazzle.page.runtime.when_empty_resolver import resolve_when_empty
from dazzle.render.fragment.primitives.data import region_poll_id

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


def _target_element_id(hx_target: str | None) -> str | None:
    """The swap target's element id from the ``HX-Target`` request header.

    htmx 4 sends ``tag#id`` (the id URI-encoded); a bare value is taken as the
    id itself. ``None`` when the header is absent or names no id.
    """
    if not hx_target:
        return None
    _tag, sep, ident = hx_target.partition("#")
    return (unquote(ident) if sep else hx_target) or None


def _poller_oob_delete(body_id: str) -> str:
    """OOB-delete the card body's poller sibling (#1802) — it, not the body,
    carries the ``every Ns`` trigger, so removing it is what stops the poll."""
    poll_id = _html_mod.escape(region_poll_id(body_id), quote=True)
    return f'<div id="{poll_id}" hx-swap-oob="delete"></div>'


def _build_region_response(
    ctx: WorkspaceRegionContext,
    fetched: Any,
    html_body: str,
    hx_target: str | None,
    is_added_card: bool = False,
    rows_only: bool = False,
) -> Any:
    """Build the region-fetch HTTP response, stopping the poll when complete.

    #1399 slice 2 — htmx-native poll-stop. htmx 4 removed the legacy HTTP-286
    poll-cancel, so we stop by removing the polling element. Since #1802 that
    is the card body's hidden poller SIBLING (``poll-<body id>``, never an
    ancestor of the region — htmx 4 implicit inheritance would hand its
    trigger to every control in the swapped body): the response OOB-deletes
    it, and htmx's ``setInterval(... e.isConnected ? rearm : clearInterval
    ...)`` self-clears. The body itself takes the plain innerHTML swap.

    The body id comes from the ``HX-Target`` request header (``tag#id`` under
    htmx 4), so multi-card regions each stop their own poller. Without it the
    region simply keeps polling — a safe no-op.
    """
    from fastapi.responses import HTMLResponse

    target_id = _target_element_id(hx_target)
    if rows_only:
        # #1821: a filter / pager fetch swaps the list's rows, not the card
        # body — neither `when_empty` (a filter matching nothing must show
        # the empty state, not collapse the card) nor the poll-stop applies.
        return HTMLResponse(content=html_body)
    # #1494 (UX-maturity 3d): an empty region self-demotes per its resolved
    # `when_empty` mode (declarative-over-htmx-4 — native OOB / HX-Reswap, no
    # bespoke JS). Only when the fetch produced no rows; `message` (the default
    # for primary content) falls through to the normal typed empty-state body.
    # #1494: a picker-added card (`?added=1`) is exempt from the auto self-demote
    # default — a user who explicitly adds a card should see its empty-state, not
    # have it immediately collapse/vanish. An *explicit* author `when_empty:`
    # still applies (their declared intent wins, even for an added card).
    if target_id and not getattr(fetched, "items", None):
        mode = resolve_when_empty(ctx.ir_region)
        if is_added_card and getattr(ctx.ir_region, "when_empty", None) is None:
            mode = WhenEmpty.MESSAGE
        if mode == WhenEmpty.SUPPRESS:
            # Remove the whole card: htmx OOB-delete the addressable wrapper
            # (`card-…`, derived from the body's `region-…` hx-target; the
            # poller lives inside it). The empty main body would swap into the
            # now-doomed card-body — moot.
            wrapper_id = "card-" + target_id.removeprefix("region-")
            return HTMLResponse(
                content=(
                    f'<div id="{_html_mod.escape(wrapper_id, quote=True)}" '
                    f'hx-swap-oob="delete"></div>'
                )
            )
        if mode == WhenEmpty.COLLAPSE:
            # Drop the empty body, keep the card chrome (title): delete the
            # hx-target (the `dz-card-body`) via the swap-override header, and
            # its poller with it (a poll into a deleted target is pointless).
            return HTMLResponse(
                content=_poller_oob_delete(target_id), headers={"HX-Reswap": "delete"}
            )

    if target_id and _region_polling_complete(ctx, fetched):
        return HTMLResponse(content=html_body + _poller_oob_delete(target_id))
    return HTMLResponse(content=html_body)


async def render_region_body_html(
    request: Any,
    ctx: WorkspaceRegionContext,
    *,
    page: int = 1,
    page_size: int | None = None,
    sort: str | None = None,
    dir: str = "asc",
) -> str:
    """Six-phase region body HTML without wrapping an HTTP response (#1677)."""
    user_ctx = await resolve_request_user_context(request, ctx)
    fetched = await fetch_region_items(request, ctx, user_ctx, sort, dir, page, page_size)
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
    render_inputs = await compute_region_render_inputs(request, ctx, user_ctx, fetched, columns)
    return await render_region_html(request, ctx, user_ctx, render_inputs, sort, dir)


async def ssr_fold_bodies(request: Any, ctxs: list[WorkspaceRegionContext]) -> dict[str, str]:
    """Render fold region bodies concurrently; a failed region stays a skeleton."""

    async def _one(ctx: WorkspaceRegionContext) -> tuple[str, str]:
        name = getattr(getattr(ctx, "ctx_region", None), "name", "") or ""
        try:
            html = await render_region_body_html(request, ctx)
            return name, html
        except Exception:
            logger.warning("command_center SSR failed for region %s", name, exc_info=True)
            return name, ""

    if not ctxs:
        return {}
    pairs = await asyncio.gather(*(_one(c) for c in ctxs))
    return {name: html for name, html in pairs if name and html}


async def _workspace_region_handler(
    request: Any,
    page: int,
    page_size: int | None,
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
    # #1494: `?added=1` marks a picker-added card → exempt from auto self-demote.
    is_added_card = request.query_params.get("added") == "1"
    return _build_region_response(
        ctx,
        fetched,
        html_body,
        request.headers.get("hx-target"),
        is_added_card=is_added_card,
        rows_only=is_list_rows_request(ctx, request),
    )
