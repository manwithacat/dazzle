"""Full-text search endpoint (#954 cycle 3).

Exposes ``GET /_dazzle/fts/{entity}?q=...`` backed by the cycle-2
``search_vector`` GENERATED column. Builds the query via
:meth:`Repository.fts_search` so all the indexed-FTS work happens
in one place.

Scope-aware filtering: when the entity carries `scope:` rules with
field conditions, the predicate compiler (used by the regular list
endpoint) produces a ``(sql, params)`` tuple that's ANDed into the
FTS WHERE clause. This keeps RBAC correct on the search endpoint
without re-implementing the scope path.

Cycle 3 scope:
  * Single-entity search via the route param.
  * Authentication required (cookie / bearer / dev-default per the
    project's auth dep).
  * Scope predicates honoured when present.

Out of scope here (cycle 4+):
  * Cross-entity / federated search (the legacy ``/_dazzle/search``
    endpoint covers the multi-entity ILIKE fallback).
  * Highlight / snippet rendering (``ts_headline``).
  * ``display: search_box`` workspace region wiring.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from dazzle.http.runtime.http_errors import require_found

logger = logging.getLogger(__name__)


def create_fts_routes(
    *,
    appspec: Any,
    repositories: dict[str, Any],
    fk_graph: Any,
    auth_dep: Any,
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
        q: str = Query(..., min_length=1, description="Search query"),
        page: int = Query(1, ge=1, description="1-indexed page number"),
        page_size: int = Query(20, ge=1, le=100, description="Per-page limit"),
        html: int = Query(
            0, description="When 1, return an HTML fragment instead of JSON (#954 cycle 4)"
        ),
        auth_context: Any = Depends(auth_dep),
    ) -> Any:
        spec = require_found(spec_by_entity.get(entity), f"No search spec for entity {entity!r}")
        repo = require_found(repositories.get(entity), f"No repository for entity {entity!r}")

        # Compile scope predicate per request — same path the list
        # endpoint takes. Skipped when the entity has no scope rules
        # or the user is a tenant admin.
        scope_pred: tuple[str, list[Any]] | None = None
        cedar_spec = _find_cedar_spec(appspec, entity)
        user_id = _resolve_user_id(auth_context)
        if cedar_spec is not None and user_id is not None:
            scope_pred = _compile_scope(
                cedar_spec=cedar_spec,
                entity_name=entity,
                fk_graph=fk_graph,
                user_id=user_id,
                auth_context=auth_context,
                admin_personas=admin_personas,
            )

        result = await repo.fts_search(
            spec,
            q,
            page=page,
            page_size=page_size,
            scope_predicate=scope_pred,
        )
        if html:
            return _render_results_html(entity, q, result)
        return {
            "entity": entity,
            "query": q,
            **result,
        }

    return router


def _render_results_html(entity: str, q: str, result: dict[str, Any]) -> HTMLResponse:
    """Render the htmx fragment for the search_box region (#954 cycle 4).

    Used when the request carries `?html=1` (the search_box region's
    htmx swap target). Pre-renders an OOB-style result list so the
    HTMX swap can drop it into `#dz-search-results-…` directly.

    The `<mark>` tags inside snippets come from `ts_headline` and
    contain matched terms only — Postgres pre-escapes the surrounding
    text. Snippets are emitted via raw concatenation (no escape) so
    the highlight markup survives; everything else goes through
    `html.escape`.

    Phase 4 (v0.67.62): inline-rendered with stdlib html.escape. The
    legacy `fragments/search_box_results.html` template is preserved
    on disk for downstream Jinja consumers.
    """
    import html

    from dazzle.render.filters import _gettext

    items = result.get("items", []) or []
    snippet_fields = result.get("snippet_fields", []) or []
    total = result.get("total", 0) or 0

    if total == 0:
        no_results = html.escape(_gettext("No results for"), quote=True)
        q_html = html.escape(str(q), quote=True)
        body = (
            f'<div class="dz-search-box-empty dz-search-box-empty--no-results">'
            f"{no_results} <em>{q_html}</em></div>"
        )
        return HTMLResponse(body)  # nosemgrep: direct-use-of-jinja2

    entity_slug = html.escape(str(entity).lower(), quote=True)
    label_text = _gettext("result") if total == 1 else _gettext("results")
    count_html = (
        f'<div class="dz-search-box-result-count">'
        f"{total} {html.escape(label_text, quote=True)}</div>"
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
        id_attr = html.escape(id_str, quote=True)

        label_value: Any = None
        if snippet_fields:
            first_field = snippet_fields[0]
            if isinstance(item, dict):
                label_value = item.get(first_field)
        if not label_value and isinstance(item, dict):
            label_value = item.get("title") or item.get("name")
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
                fld_html = html.escape(str(fld), quote=True)
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

        rows.append(
            f'<li class="dz-search-box-result">'
            f'<a href="/app/{entity_slug}/{id_attr}" class="dz-search-box-result-link">'
            f'<span class="dz-search-box-result-title">{label_html}</span>'
            f"{snippets_html}"
            f"</a></li>"
        )

    body = f'{count_html}<ul class="dz-search-box-result-list" role="list">{"".join(rows)}</ul>'
    return HTMLResponse(body)  # nosemgrep: direct-use-of-jinja2


def _find_cedar_spec(appspec: Any, entity_name: str) -> Any | None:
    """Look up the cedar/access spec for an entity. Returns None when
    no scope rules are declared (open access)."""
    for spec in getattr(appspec, "cedar_access_specs", None) or {}:
        if spec == entity_name:
            return appspec.cedar_access_specs[spec]
    return None


def _resolve_user_id(auth_context: Any) -> str | None:
    """Pull the entity-id of the current user, or None when unauth."""
    if auth_context is None:
        return None
    user = getattr(auth_context, "user", None)
    if user is None:
        return None
    return getattr(user, "id", None) or getattr(user, "entity_id", None)


def _compile_scope(
    *,
    cedar_spec: Any,
    entity_name: str,
    fk_graph: Any,
    user_id: str,
    auth_context: Any,
    admin_personas: list[str] | None,
) -> tuple[str, list[Any]] | None:
    """Wrap the route_generator helper to produce a scope predicate
    suitable for ``Repository.fts_search``.

    Returns ``None`` when no scope filter applies (admin bypass, or
    no field-level scope rules). Returns the ``(sql, params)`` tuple
    otherwise.
    """
    try:
        from dazzle.http.runtime.scope_filters import _resolve_predicate_filters
    except ImportError:
        logger.debug("route_generator scope compiler unavailable", exc_info=True)
        return None

    # Find a list-permission scope predicate on the cedar spec.
    # Cedar specs carry per-operation predicates compiled by the
    # linker; LIST is the right one for search (returning matching rows).
    from dazzle.core.access import AccessOperationKind

    list_rules = [
        r
        for r in getattr(cedar_spec, "permissions", []) or []
        if getattr(r, "operation", None) == AccessOperationKind.LIST
    ]
    predicates = [p for p in (getattr(r, "predicate", None) for r in list_rules) if p is not None]
    if not predicates:
        return None

    # Cycle 3 simplification: when multiple LIST rules carry predicates,
    # use the first. Multi-predicate OR composition is what the list
    # endpoint does; the FTS endpoint will follow once the same
    # composition helper lands as a public API.
    filters = _resolve_predicate_filters(
        predicate=predicates[0],
        entity_name=entity_name,
        fk_graph=fk_graph,
        user_id=user_id,
        auth_context=auth_context,
        admin_personas=admin_personas,
    )
    if not filters or "__scope_predicate" not in filters:
        return None
    sql, params = filters["__scope_predicate"]
    return (str(sql), list(params))


__all__ = ["create_fts_routes"]
