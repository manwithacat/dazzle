"""Full-text search endpoint (#954 cycle 3).

Exposes ``GET /_dazzle/fts/{entity}?q=...`` backed by the cycle-2
``search_vector`` GENERATED column. Builds the query via
:meth:`Repository.fts_search` so all the indexed-FTS work happens
in one place.

Access: the route applies exactly the LIST enforcement the entity's list
endpoint applies for the same caller — the Cedar LIST permit gate and the
`scope: list:` rules, via :func:`access.gated.list_scope_filters` (the
same ``_resolve_scope_filters`` call ``gated_list`` makes). The resulting
filters are ANDed into the FTS WHERE clause, so search never returns a row
the list would hide. (Before ship P the route looked the access spec up on
a non-existent ``AppSpec`` attribute and applied no scope at all.)

Cycle 3 scope:
  * Single-entity search via the route param.
  * Authentication required (cookie / bearer / dev-default per the
    project's auth dep).
  * Scope predicates honoured when present.

Out of scope here (cycle 4+):
  * Cross-entity / federated search (the legacy ``/_dazzle/search``
    endpoint covers the multi-entity ILIKE fallback).
  * Highlight / snippet rendering (``ts_headline``).
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from dazzle.core import ir
from dazzle.http.runtime.access.gated import (
    AccessForbidden,
    access_context_from,
    list_scope_filters,
)
from dazzle.http.runtime.http_errors import require_found
from dazzle.render.breadcrumbs import (
    clerk_empty_search_title,
    clerk_search_results_label,
    entity_path_labels_from_spec,
)
from dazzle.render.filters import clerk_fts_snippet_field_label
from dazzle.render.open_discovery import search_open_attr_suffix

logger = logging.getLogger(__name__)


def create_fts_routes(
    *,
    appspec: ir.AppSpec,
    repositories: dict[str, Any],
    fk_graph: Any,
    auth_dep: Any,
    cedar_access_specs: dict[str, Any] | None = None,
    admin_personas: list[str] | None = None,
) -> APIRouter | None:
    """Build the FTS router. Returns ``None`` when the AppSpec has no
    SearchSpecs (no endpoint is registered, OpenAPI stays clean).

    Args:
        appspec: The runtime AppSpec — read for ``searches`` + per-entity
            scope rules.
        repositories: ``{entity_name: Repository}`` from the runtime.
        fk_graph: For predicate compilation (FK traversal).
        auth_dep: FastAPI dependency that resolves the current user.
        cedar_access_specs: ``{entity_name: EntityAccessSpec}`` — the same
            map the list routes are generated from.
        admin_personas: Tenant-admin persona allow-list — bypass scope
            for these (mirrors the list endpoint's behaviour).
    """
    searches = list(getattr(appspec, "searches", []) or [])
    if not searches:
        return None

    # Index searches by entity for O(1) lookup at request time.
    spec_by_entity = {s.entity: s for s in searches}

    router = APIRouter(prefix="/_dazzle/fts", tags=["Search"])

    @router.get("/{entity}")
    async def fts_search(
        entity: str,
        request: Request,
        q: str = Query("", description="Search query (empty → 422 JSON / 204 html)"),
        page: int = Query(1, ge=1, description="1-indexed page number"),
        page_size: int = Query(20, ge=1, le=100, description="Per-page limit"),
        html: int = Query(
            0, description="When 1, return an HTML fragment instead of JSON (#954 cycle 4)"
        ),
        auth_context: Any = Depends(auth_dep),
    ) -> Any:
        spec = require_found(spec_by_entity.get(entity), f"No search spec for entity {entity!r}")
        repo = require_found(repositories.get(entity), f"No repository for entity {entity!r}")
        if not q.strip():
            if html:
                # #1821: a cleared search box's request (a delayed keystroke
                # landing after the clear) is answered with "nothing to swap"
                # — the box has already restored its coaching line; an error
                # body here used to land in the results panel.
                return Response(status_code=204)
            raise HTTPException(status_code=422, detail="q must not be empty")

        # Same LIST enforcement as the entity's list endpoint: permit gate,
        # then `scope: list:` rules for this caller's roles.
        access = access_context_from(
            auth_context=auth_context,
            entity_name=entity,
            cedar_access_spec=(cedar_access_specs or {}).get(entity),
            fk_graph=fk_graph,
            admin_personas=admin_personas,
        )
        try:
            scope_filters = list_scope_filters(access)
        except AccessForbidden:
            raise HTTPException(status_code=403, detail="Forbidden")

        if scope_filters is None:
            # Default-deny: no scope rule matched this caller — nothing visible.
            result: dict[str, Any] = {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
            }
        else:
            result = await repo.fts_search(
                spec,
                q,
                page=page,
                page_size=page_size,
                filters=scope_filters,
            )
        if html:
            return _render_results_html(
                entity,
                q,
                result,
                catalog=entity_path_labels_from_spec(appspec),
            )
        return {
            "entity": entity,
            "query": q,
            **result,
        }

    return router


def _render_results_html(
    entity: str,
    q: str,
    result: dict[str, Any],
    catalog: dict[str, str] | None = None,
) -> HTMLResponse:
    """Render the htmx fragment for the `SearchBox` results panel (#954 cycle 4).

    Used when the request carries `?html=1` (the list-toolbar `SearchBox`
    htmx swap target). Pre-renders an OOB-style result list so the
    HTMX swap can drop it into `#dz-search-results-…` directly.

    The `<mark>` tags inside snippets come from `ts_headline` and
    contain matched terms only — Postgres pre-escapes the surrounding
    text. Snippets are emitted via raw concatenation (no escape) so
    the highlight markup survives; everything else goes through
    `html.escape`.

    Phase 4 (v0.67.62): inline-rendered with stdlib html.escape. The
    legacy Jinja results template went with Jinja (#1042).
    """
    import html

    items = result.get("items", []) or []
    snippet_fields = result.get("snippet_fields", []) or []
    total = result.get("total", 0) or 0

    if total == 0:
        no_results = html.escape(clerk_empty_search_title(entity, catalog), quote=True)
        q_html = html.escape(str(q), quote=True)
        body = (
            f'<div class="dz-search-box-empty dz-search-box-empty--no-results">'
            f"{no_results} <em>{q_html}</em></div>"
        )
        return HTMLResponse(body)  # nosemgrep: direct-use-of-jinja2

    noun = clerk_search_results_label(entity, catalog, total=total)
    count_html = (
        f'<div class="dz-search-box-result-count">{total} {html.escape(noun, quote=True)}</div>'
    )

    rows: list[str] = []
    for item in items:
        if isinstance(item, dict):
            _id = item.get("id")
            if not _id:
                vals = list(item.values())
                _id = vals[0] if vals else ""
        else:
            _id = ""
        id_str = str(_id)

        # Prefer human labels over raw ids. Contact-style rows often have
        # first_name/last_name/email but no title/name — showing UUIDs made
        # FTS look broken to pilots (cycle 1279 agent_acceptance_panel).
        label_value: Any = None
        if snippet_fields and isinstance(item, dict):
            first_field = snippet_fields[0]
            label_value = item.get(first_field)
        if not label_value and isinstance(item, dict):
            label_value = item.get("title") or item.get("name") or item.get("label")
        if not label_value and isinstance(item, dict):
            fn = item.get("first_name")
            ln = item.get("last_name")
            if fn or ln:
                label_value = " ".join(str(p) for p in (fn, ln) if p)
        if not label_value and isinstance(item, dict):
            label_value = (
                item.get("email")
                or item.get("last_name")
                or item.get("first_name")
                or item.get("subject")
                or item.get("message")
            )
        if not label_value:
            label_value = id_str
        label_html = html.escape(str(label_value), quote=True)

        snippets_html = ""
        if snippet_fields and isinstance(item, dict):
            snippet_items: list[str] = []
            for fld in snippet_fields:
                snip = item.get(f"{fld}__snippet")
                if not snip:
                    continue
                fld_html = html.escape(clerk_fts_snippet_field_label(fld), quote=True)
                # Snippet HTML is server-trusted (PG ts_headline output) —
                # the configured StartSel/StopSel `<mark>` tags must
                # survive. Surrounding text is pre-escaped by PG.
                snippet_items.append(
                    f'<li class="dz-search-box-result-snippet">'
                    f'<span class="dz-search-box-result-snippet-field">{fld_html}:</span>'
                    f'<span class="dz-search-box-result-snippet-text">{snip}</span>'
                    f"</li>"
                )
            if snippet_items:
                snippets_html = (
                    f'<ul class="dz-search-box-result-snippets">{"".join(snippet_items)}</ul>'
                )

        # Cycle 1824 — stamp open-discovery so agents attr-read FTS result
        # hops (SearchBox results panel) without scraping titles. Logical href
        # before attr-escape; marker data-dz-search-drill (command/breadcrumb
        # parity via _view_drill_open_attr_suffix).
        href = f"/app/{str(entity).lower()}/{id_str}"
        href_attr = html.escape(href, quote=True)
        open_suffix = search_open_attr_suffix(href)
        rows.append(
            f'<li class="dz-search-box-result">'
            f'<a href="{href_attr}" class="dz-search-box-result-link"{open_suffix}>'
            f'<span class="dz-search-box-result-title">{label_html}</span>'
            f"{snippets_html}"
            f"</a></li>"
        )

    body = f'{count_html}<ul class="dz-search-box-result-list" role="list">{"".join(rows)}</ul>'
    return HTMLResponse(body)  # nosemgrep: direct-use-of-jinja2


__all__ = ["create_fts_routes"]
