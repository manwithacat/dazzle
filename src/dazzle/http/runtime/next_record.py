"""#1664: next matching record after a job stamp (not pile-return).

Opt-in via region ``after: next``. Not ``stack:``. Leftover origin
tokens stay put (pile-return). Peek and ``drill: none`` do not invent
a detail hop.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from dazzle.http.runtime.scope_filters import _extract_condition_filters

logger = logging.getLogger(__name__)

_ORIGIN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def leftover_honest_origin(raw: object) -> str | None:
    """Valid workspace/region names ride. Leftover stays put (None)."""
    if not isinstance(raw, str):
        return None
    token = raw.strip()
    if not token or not _ORIGIN.fullmatch(token):
        return None
    return token


def pick_next_id(ids: list[str], skip_id: str) -> str | None:
    """First id in stable order that is not the row just left."""
    skip = str(skip_id)
    for item_id in ids:
        if str(item_id) and str(item_id) != skip:
            return str(item_id)
    return None


def after_next_redirect(
    *,
    next_id: str | None,
    entity_slug: str,
    workspace: str,
    drill_none: bool,
    has_view: bool,
) -> str:
    """Detail of the next row, or the workspace (quiet empty / no VIEW)."""
    if next_id and has_view and not drill_none and entity_slug:
        return f"/app/{entity_slug}/{next_id}"
    return f"/app/workspaces/{workspace}"


def stamp_queue_after_next(adapter_ctx: dict[str, Any], ctx: Any) -> None:
    """Origin + drill query for ``after: next`` queue regions."""
    if getattr(ctx.ir_region, "after", None) != "next":
        return
    ws = workspace_from_region_endpoint(getattr(ctx.ctx_region, "endpoint", "") or "")
    rg = str(getattr(ctx.ir_region, "name", "") or "")
    adapter_ctx["after_workspace"] = ws
    adapter_ctx["after_region"] = rg
    tmpl = str(adapter_ctx.get("detail_url_template") or "")
    if tmpl and ws and rg:
        sep = "&" if "?" in tmpl else "?"
        adapter_ctx["detail_url_template"] = f"{tmpl}{sep}from_ws={ws}&from_rg={rg}"


def workspace_from_region_endpoint(endpoint: str) -> str:
    """Parse ``/api/workspaces/{name}/regions/...`` → workspace name."""
    parts = str(endpoint or "").strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "workspaces":
        return leftover_honest_origin(parts[2]) or ""
    return ""


def find_region(appspec: Any, workspace: str, region: str) -> Any | None:
    for ws in getattr(appspec, "workspaces", None) or ():
        if getattr(ws, "name", "") != workspace:
            continue
        for rg in getattr(ws, "regions", None) or ():
            if getattr(rg, "name", "") == region:
                return rg
    return None


def _item_id(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("id") or "")
    return str(getattr(item, "id", "") or "")


async def resolve_after_next_url(
    *,
    service: Any,
    appspec: Any,
    workspace: str,
    region: str,
    skip_id: str,
    entity_slug: str,
    auth_ctx: Any = None,
) -> str | None:
    """HX-Redirect target after a stamp, or None to keep pile-return.

    None means the origin was leftover, the region is not ``after: next``,
    or listing failed — caller keeps ``HX-Current-URL``.
    """
    ws = leftover_honest_origin(workspace)
    rg = leftover_honest_origin(region)
    if not ws or not rg:
        return None
    ir_region = find_region(appspec, ws, rg)
    if ir_region is None or getattr(ir_region, "after", None) != "next":
        return None
    ids = await _list_region_ids(service, ir_region, auth_ctx)
    if ids is None:
        return None
    nxt = pick_next_id(ids, skip_id)
    return after_next_redirect(
        next_id=nxt,
        entity_slug=entity_slug,
        workspace=ws,
        drill_none=getattr(ir_region, "drill", None) == "none",
        has_view=bool(entity_slug),
    )


def _region_sort_list(ir_region: Any) -> list[str] | None:
    ir_sort = getattr(ir_region, "sort", None) or ()
    if not ir_sort:
        return None
    return [f"-{s.field}" if getattr(s, "direction", "") == "desc" else s.field for s in ir_sort]


def _region_page_size(ir_region: Any) -> int:
    limit = getattr(ir_region, "limit", None) or 50
    try:
        return max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        return 50


async def _list_region_ids(service: Any, ir_region: Any, auth_ctx: Any) -> list[str] | None:
    filters: dict[str, Any] | None = None
    ir_filter = getattr(ir_region, "filter", None)
    if ir_filter is not None:
        try:
            extracted: dict[str, Any] = {}
            _extract_condition_filters(ir_filter, "", extracted, logger, auth_ctx)
            filters = extracted or None
        except Exception:
            logger.warning("after:next filter extract failed", exc_info=True)
            return None
    try:
        listed = await service.list(
            page=1,
            page_size=_region_page_size(ir_region),
            filters=filters,
            sort=_region_sort_list(ir_region),
        )
    except Exception:
        logger.warning("after:next list failed", exc_info=True)
        return None
    items = listed.get("items") if isinstance(listed, dict) else listed
    return [_item_id(it) for it in (items or [])]
