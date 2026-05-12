"""Workspace rendering helpers extracted from server.py.

Contains functions for building workspace region data, computing aggregate
metrics, and rendering workspace regions as HTML or JSON.

Post-#1057 (v0.67.100): column-metadata builders moved to
``workspace_columns.py``. Old import paths preserved as re-exports
below so external callers keep working.
"""

import asyncio
import csv
import datetime as _dt
import io
import logging
from dataclasses import dataclass, field
from typing import Any

from starlette.responses import StreamingResponse

# Aggregation machinery — #1057 cut 4 moved these to workspace_aggregation.
# Re-imported because `_workspace_region_handler` (below) dispatches to
# them and ~30 test sites import them from this module.
from dazzle.back.runtime.workspace_aggregation import (  # noqa: F401
    _AGGREGATE_RE,
    _aggregate_via_groupby,
    _bucket_key_label,
    _build_aggregate_filters,
    _compute_aggregate_metrics,
    _compute_box_plot_stats,
    _compute_bucketed_aggregates,
    _compute_histogram_bins,
    _compute_pivot_buckets,
    _enumerate_distinct_buckets,
    _fetch_count_metric,
    _fetch_scalar_metric,
    _format_bucket_label,
    _parse_simple_where,
    _resolve_fk_target_spec,
)

# Card-body renderers — #1057 cut 2 moved these to workspace_card_bodies.
# Imported here because `_build_entity_card_sections` (below) dispatches
# to them by display mode.
from dazzle.back.runtime.workspace_card_bodies import (
    _dazzle_html_escape,
    _render_mini_bars_body,
    _render_quick_actions_body,
    _render_stamps_body,
    _render_thread_summary_body,
)

# Card-data shapers — #1057 cut 3 moved these to workspace_card_data.
# Imported here because `_build_entity_card_sections` (below) dispatches
# to them by display mode, and tests still import them from this module.
from dazzle.back.runtime.workspace_card_data import (  # noqa: F401
    _CARD_TEMPLATE_RE,
    _build_cohort_cells,
    _build_day_timeline_slots,
    _build_task_inbox_payload,
    _coerce_pipeline_progress,
    _coerce_urgency,
    _initials_from,
    _inject_display_names,
    _interpolate_card_template,
    _items_from_template,
    _resolve_display_name,
    _resolve_path,
    _resolve_task_inbox_multi_source,
)

# Re-exports for back-compat — #1057 moved these to workspace_columns.
from dazzle.back.runtime.workspace_columns import (
    build_entity_columns as _build_entity_columns,  # noqa: F401
)
from dazzle.back.runtime.workspace_columns import (
    build_surface_columns as _build_surface_columns,  # noqa: F401
)
from dazzle.back.runtime.workspace_columns import (
    field_kind_to_col_type as _field_kind_to_col_type,  # noqa: F401
)

logger = logging.getLogger(__name__)


async def _fetch_entity_card_section_rows(
    *,
    config: Any,
    ctx: Any,
    request: Any,
    auth_context: Any,
    user_id: str | None,
) -> dict[int, list[dict[str, Any]]]:
    """Fan out per-section queries for an entity_card region (#1017).

    For each section that declares its own `source:` (the modes that
    pull from related entities — `mini_bars`, `stamps`,
    `thread_summary`):
      1. Look up the section entity's repository + access spec.
      2. Synthesize a per-section context via `dataclasses.replace`
         so `_apply_workspace_scope_filters` evaluates RBAC against
         the section entity's own scope rules.
      3. Convert the section's `filter:` ConditionExpr to a
         repo-filter dict.
      4. Fetch rows in parallel via `asyncio.gather`, capped by
         `section.limit` (when set, else 20).

    Returns a dict mapping section index → list of fetched row dicts.
    Sections without their own `source:` (halo / flags / quick_actions)
    have no entry in the returned dict — those modes don't need
    per-section rows.

    Per-section failure isolation: same as task_inbox — one bad
    query logs at warning level and yields an empty list rather
    than crashing the whole entity_card render.
    """
    import asyncio
    from contextlib import suppress
    from dataclasses import replace as _dc_replace

    cfg_sections = list(getattr(config, "sections", []) or [])
    if not cfg_sections:
        return {}
    repositories = getattr(ctx, "repositories", None) or {}
    entity_access_specs = getattr(ctx, "entity_access_specs", None) or {}
    if not repositories:
        return {}

    coros: list[Any] = []
    indices: list[int] = []
    for idx, section in enumerate(cfg_sections):
        section_source = str(getattr(section, "source", "") or "")
        if not section_source:
            continue  # halo / flags / quick_actions live on the scoped record
        repo = repositories.get(section_source)
        if repo is None:
            continue

        per_section_ctx = _dc_replace(
            ctx,
            source=section_source,
            cedar_access_spec=entity_access_specs.get(section_source),
        )
        scope_filters, scope_denied = _apply_workspace_scope_filters(
            per_section_ctx, auth_context, user_id, None
        )
        if scope_denied:
            indices.append(idx)
            coros.append(_empty_list_coro())
            continue

        merged_filters: dict[str, Any] = {}
        if scope_filters:
            merged_filters.update(scope_filters)
        section_filter = getattr(section, "filter", None)
        if section_filter is not None:
            from dazzle.back.runtime.route_generator import _extract_condition_filters

            with suppress(Exception):
                _extract_condition_filters(
                    section_filter,
                    user_id or "",
                    merged_filters,
                    logger,
                    auth_context,
                    None,
                    None,
                )

        section_limit = getattr(section, "limit", None)
        page_size = section_limit if section_limit and section_limit > 0 else 20
        coros.append(
            _safe_fetch(repo, filters=merged_filters, page_size=page_size, label=section_source)
        )
        indices.append(idx)

    if not coros:
        return {}
    results = await asyncio.gather(*coros, return_exceptions=True)
    rows_per_section: dict[int, list[dict[str, Any]]] = {}
    for idx, result in zip(indices, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "entity_card section %d fetch failed: %s — treating as empty",
                idx,
                result,
            )
            rows_per_section[idx] = []
        else:
            rows_per_section[idx] = list(result or [])
    return rows_per_section


async def _fetch_task_inbox_items_per_source(
    *,
    config: Any,
    ctx: Any,
    request: Any,
    auth_context: Any,
    user_id: str | None,
) -> dict[int, list[dict[str, Any]]]:
    """Fan out per-source queries for a task_inbox region (#1015).

    For each source declared in the config:
      1. Look up the source entity's repository (`ctx.repositories`).
      2. Look up the source entity's access spec (`ctx.entity_access_specs`).
      3. Convert the source's `filter:` ConditionExpr (if any) to a
         repo-filter dict via the existing `_extract_condition_filters`.
      4. Apply per-entity scope filters via `_apply_workspace_scope_filters`
         using a synthesized per-source context.
      5. Fetch rows in parallel via `asyncio.gather`.

    Returns a dict mapping source index → list of fetched row dicts.
    A scope-denied source (no matching scope rule) maps to an empty
    list (default-deny). Failed queries also map to empty lists with
    an operator-visible warning log — one source's failure must not
    block the rest of the inbox from rendering.

    The returned dict keys ONLY appear for as_task or count_as
    sources that successfully fetched rows; missing keys signal
    "treat as empty" downstream (matches the helper's defensive
    behaviour at `_resolve_task_inbox_multi_source`).
    """
    import asyncio
    from contextlib import suppress
    from dataclasses import replace as _dc_replace

    sources = list(getattr(config, "sources", []) or [])
    if not sources:
        return {}
    repositories = getattr(ctx, "repositories", None) or {}
    entity_access_specs = getattr(ctx, "entity_access_specs", None) or {}
    if not repositories:
        return {}

    # Gather per-source fetch coroutines along with their indices.
    coros: list[Any] = []
    indices: list[int] = []
    for idx, src in enumerate(sources):
        source_entity = str(getattr(src, "source", "") or "")
        if not source_entity:
            continue
        repo = repositories.get(source_entity)
        if repo is None:
            continue

        # Build per-source ctx for scope evaluation. Cedar access
        # spec comes from the source entity, NOT the region's own
        # primary entity.
        per_source_ctx = _dc_replace(
            ctx,
            source=source_entity,
            cedar_access_spec=entity_access_specs.get(source_entity),
        )
        scope_filters, scope_denied = _apply_workspace_scope_filters(
            per_source_ctx, auth_context, user_id, None
        )
        if scope_denied:
            # Default-deny when no scope rule matched.
            indices.append(idx)
            coros.append(_empty_list_coro())
            continue

        # Convert source.filter (ConditionExpr) to repo filter dict.
        merged_filters: dict[str, Any] = {}
        if scope_filters:
            merged_filters.update(scope_filters)
        source_filter = getattr(src, "filter", None)
        if source_filter is not None:
            from dazzle.back.runtime.route_generator import _extract_condition_filters

            with suppress(Exception):
                _extract_condition_filters(
                    source_filter,
                    user_id or "",
                    merged_filters,
                    logger,
                    auth_context,
                    None,
                    None,
                )

        # Per-source row cap is intentionally small — the inbox
        # composes typed task items, not paginated lists. 50 per
        # source is generous and keeps fan-out cost bounded.
        coros.append(_safe_fetch(repo, filters=merged_filters, page_size=50, label=source_entity))
        indices.append(idx)

    if not coros:
        return {}

    results = await asyncio.gather(*coros, return_exceptions=True)
    items_per_source: dict[int, list[dict[str, Any]]] = {}
    for idx, result in zip(indices, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("task_inbox source %d fetch failed: %s — treating as empty", idx, result)
            items_per_source[idx] = []
        else:
            items_per_source[idx] = list(result or [])
    return items_per_source


async def _empty_list_coro() -> list[dict[str, Any]]:
    """Awaitable that resolves to an empty list. Used by the
    fan-out helper to keep the gather shape uniform when a source
    is scope-denied."""
    return []


async def _safe_fetch(
    repo: Any, *, filters: dict[str, Any], page_size: int, label: str
) -> list[dict[str, Any]]:
    """Wrap a repo.list call so per-source failures don't propagate.

    Returns the items list on success, an empty list on any
    exception (logged at warning level so operators can audit)."""
    try:
        result = await repo.list(
            page=1,
            page_size=page_size,
            filters=filters,
            sort=None,
            include=None,
            fk_display_only=True,
        )
    except Exception as exc:  # noqa: BLE001 — surface to ops log
        logger.warning("task_inbox source %s fetch raised %s", label, exc)
        return []
    if isinstance(result, dict):
        return list(result.get("items", []) or [])
    if isinstance(result, list):
        return list(result)
    return []


def _build_entity_card_sections(
    *,
    items: list[dict[str, Any]],
    config: Any,
    rows_per_section: dict[int, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Build entity_card section dicts from the scoped record (#1017).

    The entity_card region scopes to a single record via the
    ``scope_param`` URL parameter; the upstream filter machinery
    narrows `items` to that record (or empty if not found / not
    permitted). This helper composes one section dict per IR
    section, populating bodies from the scoped record's fields.

    For the MVP, section bodies are minimal — `halo` and `flags`
    sections render a small key→value table from `fields`; other
    modes (mini_bars, stamps, thread_summary) emit empty bodies
    pending the per-mode compact renderer ship that wires section
    sources to their own fan-out queries.

    Sections marked `is_omitted` here when the scoped record has
    no field values for any of the section's `fields`.
    """
    if config is None:
        return []
    record = items[0] if items else None
    cfg_sections = list(getattr(config, "sections", []) or [])
    if not cfg_sections:
        return []
    out: list[dict[str, Any]] = []
    rps = rows_per_section or {}
    for section_idx, section in enumerate(cfg_sections):
        name = str(getattr(section, "name", "") or "")
        if not name:
            continue
        mode_obj = getattr(section, "mode", None)
        mode = getattr(mode_obj, "value", None) or str(mode_obj or "halo")
        fields = list(getattr(section, "fields", []) or [])
        column = "sidebar" if mode in ("flags", "thread_summary") else "main"
        body_html = ""
        is_omitted = False
        section_rows = rps.get(section_idx, [])

        if mode in ("halo", "flags") and record is not None and fields:
            rows: list[str] = []
            for field in fields:
                value = record.get(field)
                if value is None or value == "":
                    continue
                rows.append(
                    f"<dt>{_dazzle_html_escape(str(field))}</dt><dd>{_dazzle_html_escape(str(value))}</dd>"
                )
            if rows:
                body_html = f'<dl class="dz-entity-card-{mode}-grid">{"".join(rows)}</dl>'
            else:
                # Optional section with no values resolved — omit
                # rather than render an empty <dl>.
                is_omitted = True
        elif mode == "halo" and record is None:
            is_omitted = True
        elif mode == "quick_actions":
            # quick_actions sections render a button row from the IR's
            # `actions: [...]` list. No DB query — pure config-to-HTML.
            # Each action is an action id (typically a surface name);
            # the runtime adapter wires it as `data-dz-action="<id>"`
            # so project JS can hook open-modal behavior. When the
            # action list is empty the section omits entirely.
            actions = list(getattr(section, "actions", []) or [])
            if actions:
                body_html = _render_quick_actions_body(actions)
            else:
                is_omitted = True
        elif mode == "mini_bars":
            # mini_bars renders a compact horizontal bar row from
            # rows pre-fetched by the per-section fan-out (#1017
            # v0.67.18). `fields[0]` is the value column; `fields[1]`
            # (optional) is the label column. Bars are normalised
            # against the max value in the row set so each bar's
            # width is relative.
            value_field = fields[0] if fields else ""
            label_field = fields[1] if len(fields) > 1 else ""
            body_html = _render_mini_bars_body(
                rows=section_rows,
                value_field=value_field,
                label_field=label_field,
            )
            if not body_html:
                is_omitted = True
        elif mode == "stamps":
            # stamps renders a chronological event list from rows
            # pre-fetched by the per-section fan-out (#1017 v0.67.19).
            # `fields[0]` is the timestamp column; `fields[1]` is the
            # label column; `fields[2]` (optional) is a secondary
            # detail (e.g. actor / category). Sort descending by
            # timestamp — most recent event first. Section omits
            # when there are no rows.
            timestamp_field = fields[0] if fields else ""
            label_field = fields[1] if len(fields) > 1 else ""
            detail_field = fields[2] if len(fields) > 2 else ""
            body_html = _render_stamps_body(
                rows=section_rows,
                timestamp_field=timestamp_field,
                label_field=label_field,
                detail_field=detail_field,
            )
            if not body_html:
                is_omitted = True
        elif mode == "thread_summary":
            # thread_summary renders a compact comm-summary card
            # showing the SINGLE most-recent thread / message in
            # the row set (#1017 v0.67.20). Field convention:
            # `fields[0]` = timestamp column (used to pick most
            # recent), `fields[1]` = sender / counterparty,
            # `fields[2]` = subject, `fields[3]` = body / snippet.
            # Section omits when there are no rows or no timestamp
            # field is configured (need a sort key to pick "most
            # recent"). Sidebar column by default — the section's
            # job is to be a compact secondary panel, not a row.
            timestamp_field = fields[0] if fields else ""
            sender_field = fields[1] if len(fields) > 1 else ""
            subject_field = fields[2] if len(fields) > 2 else ""
            snippet_field = fields[3] if len(fields) > 3 else ""
            body_html = _render_thread_summary_body(
                rows=section_rows,
                timestamp_field=timestamp_field,
                sender_field=sender_field,
                subject_field=subject_field,
                snippet_field=snippet_field,
            )
            if not body_html:
                is_omitted = True

        section_label = name.replace("_", " ").title()
        out.append(
            {
                "section_id": name,
                "label": section_label,
                "mode": mode,
                "body": body_html,
                "column": column,
                "is_omitted": is_omitted,
            }
        )
    return out


async def _resolve_workspace_user(
    request: Any,
    auth_middleware: Any,
    repositories: dict[str, Any] | None,
    user_entity_name: str = "User",
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve the current authenticated user to a DSL User entity UUID and attributes dict.

    Returns (entity_uuid, entity_dict) or (auth_user_id, None) as fallback.
    If no user can be resolved, returns (None, None).
    """
    if not auth_middleware:
        return None, None
    try:
        auth = auth_middleware.get_auth_context(request)
        if not (auth and auth.is_authenticated and auth.user):
            return None, None
    except Exception:
        logger.debug("Failed to resolve current user for filter context", exc_info=True)
        return None, None

    # Try to find the user entity record by email so filters use entity IDs.
    # Uses the DSL user entity name (may be "Student", "Member", etc.) (#588).
    email = getattr(auth.user, "email", None)
    if email and repositories:
        user_repo = repositories.get(user_entity_name)
        if user_repo:
            try:
                user_result = await user_repo.list(filters={"email": email}, page_size=1)
                user_items = (
                    user_result.get("items", [])
                    if isinstance(user_result, dict)
                    else getattr(user_result, "items", [])
                )
                if user_items:
                    entity_user = user_items[0]
                    uid = (
                        entity_user.get("id")
                        if isinstance(entity_user, dict)
                        else getattr(entity_user, "id", None)
                    )
                    if uid:
                        entity_dict = (
                            entity_user
                            if isinstance(entity_user, dict)
                            else entity_user.model_dump()
                            if hasattr(entity_user, "model_dump")
                            else {}
                        )
                        return str(uid), entity_dict
            except Exception:
                logger.debug("Could not resolve User entity by email", exc_info=True)

    # Fallback to auth user ID
    return str(auth.user.id), None


@dataclass
class WorkspaceRegionContext:
    """Bundles the non-request, non-pagination context for a workspace region handler."""

    ctx_region: Any
    ir_region: Any
    source: str
    entity_spec: Any
    attention_signals: list[Any]
    ws_access: Any
    repositories: dict[str, Any]
    require_auth: bool
    auth_middleware: Any
    # Pre-computed at startup (constant-folded from IR)
    precomputed_columns: list[dict[str, Any]] = field(default_factory=list)
    # Pre-computed ref relation names for eager-loading (from entity_auto_includes)
    auto_include: list[str] = field(default_factory=list)
    # Surface UX metadata (#362)
    surface_default_sort: list[Any] = field(default_factory=list)
    surface_empty_message: str = ""
    # Runtime parameter resolution (#572)
    param_resolver: Any = None  # ParamResolver | None
    tenant_id: str | None = None
    # Entity access spec for scope predicate enforcement (#574)
    cedar_access_spec: Any = None
    fk_graph: Any = None
    # DSL user entity name for current_user resolution (#588)
    user_entity_name: str = "User"
    # #1015 (v0.67.16) — per-entity access specs for multi-source
    # task_inbox fan-out. Maps entity name → access spec so each
    # source can apply its own scope rules at fetch time. Default
    # empty dict keeps single-source paths cost-free.
    entity_access_specs: dict[str, Any] = field(default_factory=dict)


def _render_csv_response(
    items: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    region_name: str,
) -> StreamingResponse:
    """Return items as a CSV download."""
    output = io.StringIO()
    col_keys = [c["key"] for c in columns]
    col_labels = [c.get("label", c["key"]) for c in columns]

    writer = csv.writer(output)
    writer.writerow(col_labels)
    for item in items:
        row = [str(item.get(f"{k}_display", item.get(k, ""))) for k in col_keys]
        writer.writerow(row)

    output.seek(0)
    filename = f"{region_name}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _apply_workspace_scope_filters(
    ctx: WorkspaceRegionContext,
    auth_context: Any,
    user_id: str | None,
    filters: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, bool]:
    """Apply entity-level scope predicates to workspace region filters.

    Mirrors the scope enforcement in ``route_generator._make_list_handler``
    so that workspace regions cannot bypass row-level scope rules (#574).

    Returns:
        (merged_filters, denied) — *denied* is True when no scope rule
        matched the user's roles (default-deny: caller should return empty).
    """
    cedar_access_spec = ctx.cedar_access_spec
    if not cedar_access_spec or not user_id or not auth_context:
        return filters, False

    scopes = getattr(cedar_access_spec, "scopes", None)
    if not scopes:
        # No scope rules — pass through without row filtering (#607).
        # The permit gate already controls entity-level access.
        return filters, False

    from dazzle.back.runtime.route_generator import (
        _normalize_role,
        _resolve_scope_filters,
    )

    # Collect normalized user roles
    scope_user_roles: set[str] = set()
    user_obj = getattr(auth_context, "user", None)
    if user_obj:
        for r in getattr(user_obj, "roles", []):
            rname = r if isinstance(r, str) else getattr(r, "name", str(r))
            scope_user_roles.add(_normalize_role(rname))

    scope_result = _resolve_scope_filters(
        cedar_access_spec,
        "list",
        scope_user_roles,
        user_id,
        auth_context,
        entity_name=ctx.source,
        fk_graph=ctx.fk_graph,
    )

    if scope_result is None:
        # No scope rule matched — default-deny
        return filters, True

    if scope_result:
        filters = {**(filters or {}), **scope_result}

    return filters, False


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

    Extracted from DazzleBackendApp._init_workspace_routes to reduce closure
    complexity.  All context is bundled in a ``WorkspaceRegionContext``.
    """
    from fastapi import HTTPException
    from fastapi.responses import HTMLResponse

    # Enforce authentication (#145)
    if ctx.require_auth:
        auth_ctx = None
        if ctx.auth_middleware:
            try:
                auth_ctx = ctx.auth_middleware.get_auth_context(request)
            except Exception:
                logger.debug("Failed to get auth context for region", exc_info=True)
        if not (auth_ctx and auth_ctx.is_authenticated):
            raise HTTPException(status_code=401, detail="Authentication required")

        # RBAC: enforce workspace persona restrictions on region data.
        # Roles use "role_" prefix; persona IDs don't.
        if ctx.ws_access and ctx.ws_access.allow_personas and auth_ctx:
            is_super = auth_ctx.user and auth_ctx.user.is_superuser
            normalized_roles = [r.removeprefix("role_") for r in auth_ctx.roles]
            if not is_super and not any(
                r in ctx.ws_access.allow_personas for r in normalized_roles
            ):
                raise HTTPException(status_code=403, detail="Workspace access denied")

    # Resolve current user ID for filter expressions (e.g. reviewer == current_user)
    # Auth user IDs and User entity IDs are separate; resolve via email match (#480).
    # Always attempt resolution when middleware is available, even in test mode
    # where require_auth is False — the user may still be authenticated (#483).
    _current_user_id, _current_user_entity = await _resolve_workspace_user(
        request, ctx.auth_middleware, ctx.repositories, ctx.user_entity_name
    )

    # Build auth_context for _extract_condition_filters (shared with entity scope path)
    _auth_ctx_for_filters: Any = None
    if ctx.auth_middleware:
        try:
            _auth_ctx_for_filters = ctx.auth_middleware.get_auth_context(request)
            # Ensure preferences contain entity attributes so current_user.<attr> resolves
            if _auth_ctx_for_filters and _current_user_entity:
                prefs = getattr(_auth_ctx_for_filters, "preferences", None)
                if prefs is None:
                    _auth_ctx_for_filters.preferences = {}
                    prefs = _auth_ctx_for_filters.preferences
                from uuid import UUID as _UUID

                for k, v in _current_user_entity.items():
                    if k not in prefs and v is not None:
                        prefs[k] = str(v) if isinstance(v, _UUID) else v
                if _current_user_id and "entity_id" not in prefs:
                    prefs["entity_id"] = _current_user_id
        except Exception:
            logger.debug("Failed to get auth context for filter resolution", exc_info=True)

    # Build legacy filter context for attention signals and grant evaluation
    _filter_context: dict[str, Any] = {}
    if _current_user_id:
        _filter_context["current_user_id"] = _current_user_id
    if _current_user_entity:
        _filter_context["current_user_entity"] = _current_user_entity
    # Context selector value (v0.38.0): from query param or user preferences
    _context_id = request.query_params.get("context_id")
    if _context_id:
        _filter_context["current_context"] = _context_id

    # Pre-fetch active grants for has_grant() condition evaluation (v0.42.0)
    if _current_user_id:
        try:
            from .grant_store import GrantStore

            # Get DB connection from any available repository
            _db_mgr = None
            if ctx.repositories:
                for _r in ctx.repositories.values():
                    _db_mgr = getattr(_r, "db", None)
                    if _db_mgr:
                        break
            if _db_mgr:
                _grant_conn = _db_mgr.get_persistent_connection()
                _grant_store = GrantStore(_grant_conn)
                from uuid import UUID as _UUID

                _active_grants = _grant_store.list_grants(
                    principal_id=_UUID(_current_user_id), status="active"
                )
                _filter_context["active_grants"] = _active_grants
            else:
                _filter_context["active_grants"] = []
        except Exception:
            # Grant tables may not exist if no grant_schemas defined
            logger.debug("Could not pre-fetch grants", exc_info=True)
            _filter_context["active_grants"] = []

    # Query the source entity
    items: list[dict[str, Any]] = []
    total = 0
    columns: list[dict[str, Any]] = []

    # SECURITY (#887): default-deny scope state before evaluating
    # `_apply_workspace_scope_filters`. The aggregate / bucketed /
    # pivot / overlay code paths downstream gate on `_scope_denied`,
    # so any failure path that skips scope evaluation (no repo, early
    # exception) MUST surface as a denial — otherwise unfiltered SQL
    # aggregates leak cross-tenant data.
    _scope_only_filters: dict[str, Any] | None = None
    _scope_denied: bool = True

    repo = ctx.repositories.get(ctx.source) if ctx.repositories else None
    if repo:
        try:
            # Build filters from IR ConditionExpr
            # Multi-source regions store per-source filter on _source_filter
            filters: dict[str, Any] | None = None
            ir_filter = getattr(ctx, "_source_filter", None) or ctx.ir_region.filter
            if ir_filter is not None:
                try:
                    from dazzle.back.runtime.route_generator import (
                        _extract_condition_filters,
                    )

                    filters = {}
                    _extract_condition_filters(
                        ir_filter,
                        _current_user_id or "",
                        filters,
                        logger,
                        _auth_ctx_for_filters,
                        context_id=_context_id,
                    )
                    if not filters:
                        filters = None
                except Exception:
                    logger.warning("Failed to evaluate condition filter", exc_info=True)

            # Build sort — user sort param > IR region sort > surface UX sort (#362)
            sort_list: list[str] | None = None
            if sort:
                sort_list = [f"-{sort}" if dir == "desc" else sort]
            else:
                ir_sort = ctx.ir_region.sort
                if ir_sort:
                    sort_list = [
                        f"-{s.field}" if s.direction == "desc" else s.field for s in ir_sort
                    ]
                elif ctx.surface_default_sort:
                    sort_list = [
                        f"-{s.field}" if s.direction == "desc" else s.field
                        for s in ctx.surface_default_sort
                    ]

            # Collect interactive filters from query params
            for param_key, param_val in request.query_params.items():
                if param_key.startswith("filter_") and param_val:
                    field_name = param_key[7:]  # strip "filter_"
                    if filters is None:
                        filters = {}
                    filters[field_name] = param_val

            # Date range filtering (#566)
            date_field = ctx.ctx_region.date_field if hasattr(ctx.ctx_region, "date_field") else ""
            if date_field:
                date_from = request.query_params.get("date_from")
                date_to = request.query_params.get("date_to")
                if date_from:
                    if filters is None:
                        filters = {}
                    filters[f"{date_field}__gte"] = date_from
                if date_to:
                    if filters is None:
                        filters = {}
                    filters[f"{date_field}__lte"] = date_to

            # SECURITY: apply entity-level scope predicates (#574)
            _scope_only_filters, _scope_denied = _apply_workspace_scope_filters(
                ctx, _auth_ctx_for_filters, _current_user_id, None
            )
            if _scope_only_filters:
                filters = {**(filters or {}), **_scope_only_filters}

            # Use pre-computed auto_include from entity_auto_includes (#272, #423)
            include_rels = ctx.auto_include

            # Grouped views need enough items to distribute across columns.
            # BOX_PLOT (#889) added so a paginated default still surfaces
            # all FK-distinct buckets when `group_by: <fk_column>`.
            if (
                ctx.ctx_region.display in ("KANBAN", "BAR_CHART", "FUNNEL_CHART", "BOX_PLOT")
                and not ctx.ctx_region.limit
            ):
                limit = min(page_size, 200) if page_size > 20 else 50
            else:
                limit = ctx.ctx_region.limit or page_size
            if _scope_denied:
                # No scope rule matched — default-deny: empty result set
                result = {"items": [], "total": 0}
            else:
                result = await repo.list(
                    page=page,
                    page_size=limit,
                    filters=filters,
                    sort=sort_list,
                    include=include_rels or None,
                    fk_display_only=True,
                )
            if isinstance(result, dict):
                _result: dict[str, Any] = result
                raw_items = _result.get("items", [])
                items = [i.model_dump() if hasattr(i, "model_dump") else dict(i) for i in raw_items]
                # Resolve FK dicts to display strings (#571)
                items = [_inject_display_names(item) for item in items]
                # SECURITY: use item count as total for workspace regions.
                # The repo COUNT query may not have scope rules applied,
                # which would leak unscoped record counts in pagination
                # metadata (e.g., "Showing 10 of 52,380") (#573).
                total = len(items)

            # Zero results is valid — the region shows its empty: message.
            # Do NOT fall back to unfiltered queries: scope/filter conditions
            # are access-control gates, not advisory hints (#546).
        except Exception as exc:
            # #935: previously logged at WARN which hid backend errors
            # (DB type mismatches, missing columns, scope-predicate
            # compilation failures) inside the noise threshold of a
            # busy server. The fail-closed semantics (#546) are
            # preserved — the region still renders empty — but the
            # log line is now ERROR-level + structured so anyone
            # hitting "my region shows no rows but the entity list
            # shows 5" gets a single grep to find the cause.
            logger.error(
                "workspace_region_query_failed entity=%s region=%s exc=%s",
                ctx.source,
                ctx.ctx_region.name,
                type(exc).__name__,
                exc_info=True,
            )

    # Use pre-computed columns from startup (constant-folded from IR).
    # Filter out columns whose visible: predicate fails for the current
    # persona (#872). Build a fresh list — never mutate the shared one.
    if ctx.precomputed_columns:
        if any(c.get("visible_condition") for c in ctx.precomputed_columns):
            from dazzle.ui.utils.condition_eval import evaluate_condition as _eval_vis

            _request_roles = list(_auth_ctx_for_filters.roles) if _auth_ctx_for_filters else []
            _role_ctx = {
                "user_roles": [r.removeprefix("role_") for r in _request_roles],
            }
            columns = [
                c
                for c in ctx.precomputed_columns
                if not c.get("visible_condition")
                or _eval_vis(c["visible_condition"], {}, _role_ctx)
            ]
        else:
            columns = ctx.precomputed_columns
    elif items:
        columns = [
            {
                "key": k,
                "label": k.replace("_", " ").title(),
                "type": "text",
                "sortable": True,
            }
            for k in items[0].keys()
            if k != "id"
        ]

    # CSV export (#562)
    format_param = request.query_params.get("format")
    if format_param == "csv":
        return _render_csv_response(items, columns, ctx.ctx_region.name)

    # Build aggregate metrics if configured. SECURITY (#887): suppress
    # when scope is denied — unfiltered aggregates would leak counts /
    # sums / averages across tenants.
    metrics: list[dict[str, Any]] = []
    if ctx.ctx_region.aggregates and not _scope_denied:
        metrics = await _compute_aggregate_metrics(
            ctx.ctx_region.aggregates,
            ctx.repositories,
            total,
            items,
            scope_filters=_scope_only_filters,
            delta=ctx.ctx_region.delta,  # #884
            source_entity=ctx.source,  # #888 Phase 1
            tones=getattr(ctx.ctx_region, "tones", None),  # v0.61.65
        )

    # Bucketed aggregates for bar_chart distributions (#847). When a
    # bar_chart region declares both `group_by` and `aggregates`, evaluate
    # the first aggregate once per bucket so authors can express true
    # distributions instead of getting raw row counts. The bucket list
    # comes from `kanban_columns` when available (enum / state-machine
    # values), else falls back to distinct items[group_by].
    bucketed_metrics: list[dict[str, Any]] = []

    # Build filter column metadata for template
    filter_columns: list[dict[str, Any]] = [
        {
            "key": c["key"],
            "label": c["label"],
            "options": c.get("filter_options", []),
        }
        for c in columns
        if c.get("filterable")
    ]
    active_filters: dict[str, str] = {
        k[7:]: v for k, v in request.query_params.items() if k.startswith("filter_") and v
    }

    # Evaluate attention signals for row highlighting
    if ctx.attention_signals and items:
        from dazzle.back.runtime.condition_evaluator import (
            evaluate_condition as _eval_cond,
        )

        _severity_order = {
            "critical": 0,
            "warning": 1,
            "notice": 2,
            "info": 3,
        }
        for item in items:
            best: dict[str, str] | None = None
            best_sev = 999
            for sig in ctx.attention_signals:
                try:
                    cond_dict = sig.condition.model_dump(exclude_none=True)
                    if _eval_cond(cond_dict, item, _filter_context):
                        lvl = sig.level.value if hasattr(sig.level, "value") else str(sig.level)
                        sev = _severity_order.get(lvl, 99)
                        if sev < best_sev:
                            best_sev = sev
                            best = {
                                "level": lvl,
                                "message": sig.message,
                            }
                except Exception:
                    logger.debug("Failed to evaluate attention signal", exc_info=True)
            if best:
                item["_attention"] = best

    # Grouped displays: extract column values from group_by field's enum/state-machine
    kanban_columns: list[str] = []
    # Read group_by from ir_region — the IR preserves the typed form
    # (str | BucketRef | None). ctx_region (pydantic, template-facing)
    # flattens it to a string for Jinja.
    group_by = (
        getattr(ctx.ir_region, "group_by", None) if ctx.ir_region else ctx.ctx_region.group_by
    )
    _grouped_modes = {"KANBAN", "BAR_CHART", "FUNNEL_CHART"}
    # Time-bucketed group_by is a BucketRef — it has no enum values and is
    # never kanban. Skip the enum/state-machine resolution for it.
    from dazzle.core.ir import BucketRef as _BucketRef

    _gb_is_bucket = isinstance(group_by, _BucketRef)
    if (
        group_by
        and not _gb_is_bucket
        and ctx.ctx_region.display in _grouped_modes
        and ctx.entity_spec
    ):
        # Try enum values first, then state machine states
        for f in ctx.entity_spec.fields:
            if f.name == group_by:
                ev = getattr(f.type, "enum_values", None)
                if ev:
                    kanban_columns = list(ev)
                break
        if not kanban_columns:
            sm = ctx.entity_spec.state_machine
            if sm and sm.status_field == group_by:
                kanban_columns = [s if isinstance(s, str) else str(s) for s in sm.states]

    # Compute bucketed aggregates for bar_chart / line_chart / sparkline —
    # single-dim distributions or time-series. Multi-dim (area_chart /
    # pivot_table) runs through _compute_pivot_buckets below.
    # SECURITY (#887): same gating as `metrics` above — bucketed
    # aggregates run their own SQL GROUP BY query and would leak
    # cross-tenant rows when scope is denied.
    _single_dim_chart_modes = {"BAR_CHART", "LINE_CHART", "SPARKLINE", "RADAR", "BAR_TRACK"}
    if (
        ctx.ctx_region.display in _single_dim_chart_modes
        and group_by
        and ctx.ctx_region.aggregates
        and not _scope_denied
    ):
        bucketed_metrics = await _compute_bucketed_aggregates(
            ctx.ctx_region.aggregates,
            ctx.repositories,
            group_by,
            items,
            bucket_values=kanban_columns or None,
            scope_filters=_scope_only_filters,
            source_entity=ctx.source,
        )

    # Histogram (#882, v0.61.27): bin a continuous numeric column from the
    # already-fetched ``items`` and pass per-bin counts to the template.
    # No extra DB query — uses the rows already loaded for the region. The
    # value column is read from ``heatmap_value`` (legacy-named generic
    # "the value column" IR field). ``bin_count`` is the explicit bin count
    # or None for Sturges' rule (⌈log2(N) + 1⌉).
    histogram_bins: list[dict[str, Any]] = []
    if ctx.ctx_region.display == "HISTOGRAM":
        _value_field = (getattr(ctx.ctx_region, "heatmap_value", "") or "").strip()
        _bin_count = getattr(ctx.ir_region, "bin_count", None)
        if _value_field:
            histogram_bins = _compute_histogram_bins(items, _value_field, _bin_count)

    # Box plot (#881, v0.61.29): per-group quartile/whisker stats from the
    # already-fetched ``items``. Same in-process pattern as histogram.
    box_plot_stats: list[dict[str, Any]] = []
    if ctx.ctx_region.display == "BOX_PLOT":
        _value_field = (getattr(ctx.ctx_region, "heatmap_value", "") or "").strip()
        _bp_group_by = group_by if isinstance(group_by, str) else None
        _show_outliers = bool(getattr(ctx.ir_region, "show_outliers", True))
        if _value_field:
            box_plot_stats = _compute_box_plot_stats(
                items, _value_field, _bp_group_by, _show_outliers
            )

    # Overlay series (#883, v0.61.33): for line/area chart regions,
    # fire one extra `_compute_bucketed_aggregates` per overlay using
    # the parent's group_by but the overlay's own source/filter/aggregate.
    # Each overlay collapses to a list of {label, value} buckets that the
    # template renders as an additional polyline (line_chart) or stacked
    # layer (area_chart).
    overlay_series_data: list[dict[str, Any]] = []
    _ir_overlays = (getattr(ctx.ir_region, "overlay_series", None) if ctx.ir_region else None) or []
    # SECURITY (#887): overlays each fire a fresh `_compute_bucketed_aggregates`
    # against `_ovl_source` — same scope gate as the primary buckets above.
    if (
        _ir_overlays
        and ctx.ctx_region.display in {"LINE_CHART", "AREA_CHART"}
        and group_by
        and not _scope_denied
    ):
        for _overlay in _ir_overlays:
            _ovl_source = _overlay.source or ctx.source
            # Convert the overlay's filter ConditionExpr → flat dict for
            # the runtime via the same path scope_filters use. For the v1
            # we inline-merge the overlay's filter as the where_clause
            # of a synthetic `<aggregate_expr>` evaluated against
            # _ovl_source. Scope still applies (overlay sees the same
            # scope_filters as the primary aggregate).
            try:
                _overlay_aggregates = {_overlay.label: _overlay.aggregate_expr}
                _overlay_buckets = await _compute_bucketed_aggregates(
                    _overlay_aggregates,
                    ctx.repositories,
                    group_by,
                    items=[],  # overlay computes its own buckets via fast path
                    bucket_values=kanban_columns or None,
                    scope_filters=_scope_only_filters,
                    source_entity=_ovl_source,
                )
                overlay_series_data.append(
                    {
                        "label": _overlay.label,
                        "buckets": _overlay_buckets,
                    }
                )
            except Exception:
                logger.warning(
                    "Overlay series %r failed — skipping",
                    _overlay.label,
                    exc_info=True,
                )

    # Bullet chart (#880, v0.61.30): one row per item, reading three named
    # columns (label, actual, target) directly off the item. Pre-computed
    # MVP — per-group_by aggregation deferred (would need multi-measure
    # support in `_compute_bucketed_aggregates`). Reference_bands (#883)
    # render as comparative qualitative zones behind each bar.
    bullet_rows: list[dict[str, Any]] = []
    bullet_max_value: float = 0.0
    if ctx.ctx_region.display == "BULLET":
        _label_field = getattr(ctx.ir_region, "bullet_label", None)
        _actual_field = getattr(ctx.ir_region, "bullet_actual", None)
        _target_field = getattr(ctx.ir_region, "bullet_target", None)
        if _label_field and _actual_field:
            for item in items:
                _actual_raw = item.get(_actual_field)
                if _actual_raw is None:
                    continue
                try:
                    _actual = float(_actual_raw)
                except (TypeError, ValueError):
                    continue
                _target: float | None = None
                if _target_field:
                    _target_raw = item.get(_target_field)
                    if _target_raw is not None:
                        try:
                            _target = float(_target_raw)
                        except (TypeError, ValueError):
                            _target = None
                bullet_rows.append(
                    {
                        "label": str(item.get(_label_field, "") or ""),
                        "actual": _actual,
                        "target": _target,
                    }
                )
            # Shared scale for all rows — max of actual values, target ticks,
            # and the band extents so out-of-range values still fit.
            _scale_candidates: list[float] = [r["actual"] for r in bullet_rows]
            _scale_candidates.extend(r["target"] for r in bullet_rows if r["target"] is not None)
            _scale_candidates.extend(
                getattr(b, "to_value", 0.0)
                for b in (getattr(ctx.ir_region, "reference_bands", None) or [])
            )
            bullet_max_value = max(_scale_candidates) if _scale_candidates else 0.0

    # Bar track (#893, v0.61.53): per-row label + filled track + value.
    # Reuses the single-dim chart pipeline — `bucketed_metrics` is
    # already populated above. Post-process into row dicts with a
    # computed `fill_pct` (value / track_max) and `formatted_value`
    # (Python format spec applied). The format spec runs in Python via
    # `format()` rather than Jinja so the template stays simple and we
    # don't risk template injection from an author-supplied format
    # string.
    bar_track_rows: list[dict[str, Any]] = []
    bar_track_max: float = 0.0
    if ctx.ctx_region.display == "BAR_TRACK" and bucketed_metrics:
        _explicit_max = ctx.ctx_region.track_max
        _format_spec = ctx.ctx_region.track_format or ""
        _values: list[float] = []
        for _bucket in bucketed_metrics:
            try:
                _values.append(float(_bucket.get("value") or 0))
            except (TypeError, ValueError):
                _values.append(0.0)
        # Auto-max when not explicitly set: use the largest bucketed
        # value so all bars fit in [0, 1] of the track. Falls back to
        # 1.0 when all values are zero/negative to avoid div-by-zero.
        bar_track_max = (
            float(_explicit_max)
            if _explicit_max is not None
            else (max(_values) if _values and max(_values) > 0 else 1.0)
        )
        for _bucket, _value in zip(bucketed_metrics, _values, strict=True):
            _fill_pct = (
                max(0.0, min(100.0, (_value / bar_track_max) * 100.0)) if bar_track_max else 0.0
            )
            # Accept both str.format-template syntax (`"{:.0%}"` — what the
            # issue example shows; matches f-string convention) and bare
            # format-spec syntax (`".0%"`). Detect by looking for the
            # `{` wrapper.
            try:
                if not _format_spec:
                    _formatted = str(_value)
                elif "{" in _format_spec:
                    _formatted = _format_spec.format(_value)
                else:
                    _formatted = format(_value, _format_spec)
            except (ValueError, TypeError, KeyError, IndexError):
                # Malformed format spec → fall back to raw str. Logged so
                # authors notice; doesn't crash the dashboard.
                logger.warning(
                    "bar_track region %r: invalid track_format %r — rendering raw value",
                    ctx.ctx_region.name,
                    _format_spec,
                )
                _formatted = str(_value)
            bar_track_rows.append(
                {
                    "label": str(_bucket.get("label") or ""),
                    "value": _value,
                    "fill_pct": _fill_pct,
                    "formatted_value": _formatted,
                }
            )

    # Action grid (#891, v0.61.54): CTA cards on dashboards. Each card
    # carries a label/icon/url/tone (already resolved at context build
    # time) plus an optional `count_aggregate` expression that the
    # runtime fires per-card via the existing `_fetch_count_metric`
    # machinery. Single batched query is a future optimisation; MVP
    # fires concurrently via asyncio.gather.
    # SECURITY (#887): same scope gate as other aggregate paths — when
    # scope is denied the per-card counts are suppressed (cards still
    # render but with no count badge).
    action_card_data: list[dict[str, Any]] = []
    if ctx.ctx_region.display == "ACTION_GRID":
        _cards = ctx.ctx_region.action_cards or []
        if _cards and not _scope_denied:
            _AGG_RE = _AGGREGATE_RE
            _count_tasks: list[Any] = []
            _count_indices: list[int] = []
            for _idx, _card in enumerate(_cards):
                _expr = _card.get("count_aggregate") or ""
                if not _expr:
                    continue
                _m = _AGG_RE.match(_expr)
                if not _m:
                    continue
                _func, _entity_name, _where = _m.groups()
                _agg_repo = ctx.repositories.get(_entity_name) if ctx.repositories else None
                if _func != "count" or _agg_repo is None:
                    # Per-card scalar aggregates not yet supported —
                    # skip; card renders without a count.
                    continue
                # #901: scope_filters were resolved against the region's
                # source entity. They reference columns that only exist
                # on the source entity. Passing them to a different-
                # entity repo causes silent SQL errors (caught and
                # swallowed in `_fetch_count_metric`) and the card
                # renders 0. Gate on entity match: pass scope_filters
                # only when the per-card entity equals the region
                # source. Cross-entity counts run unscoped — log a
                # warning so operators can audit. Resolving the
                # destination entity's own scope here would require
                # threading appspec.surfaces lookups; deferred until a
                # consumer needs scoped cross-entity counts.
                _card_scope = _scope_only_filters if _entity_name == ctx.source else None
                if _card_scope is None and _scope_only_filters is not None:
                    logger.warning(
                        "action_grid card %d (entity=%s, source=%s): cross-entity "
                        "count is unscoped — destination entity's own RBAC at "
                        "navigation time still applies, but the count badge "
                        "shows ALL rows the runtime can read",
                        _idx,
                        _entity_name,
                        ctx.source,
                    )
                _count_tasks.append(
                    _fetch_count_metric(
                        f"action_card_{_idx}",
                        _agg_repo,
                        _where,
                        _card_scope,
                        source_entity=_entity_name,
                    )
                )
                _count_indices.append(_idx)
            _count_results: dict[int, Any] = {}
            if _count_tasks:
                import asyncio as _asyncio

                _results = await _asyncio.gather(*_count_tasks, return_exceptions=True)
                for _ridx, _rresult in zip(_count_indices, _results, strict=True):
                    if isinstance(_rresult, tuple):
                        _count_results[_ridx] = _rresult[1]
                    else:
                        logger.warning(
                            "action_grid card %d count query failed: %s", _ridx, _rresult
                        )
            for _idx, _card in enumerate(_cards):
                action_card_data.append(
                    {
                        "label": _card.get("label", ""),
                        "icon": _card.get("icon", ""),
                        "url": _card.get("url", ""),
                        "tone": _card.get("tone", "neutral"),
                        "count": _count_results.get(_idx),
                    }
                )
        elif _cards:
            # scope denied — render cards without counts
            for _card in _cards:
                action_card_data.append(
                    {
                        "label": _card.get("label", ""),
                        "icon": _card.get("icon", ""),
                        "url": _card.get("url", ""),
                        "tone": _card.get("tone", "neutral"),
                        "count": None,
                    }
                )

    # Pipeline steps (#890, v0.61.56): sequential-stage workflow.
    # Each stage's `value` is either an aggregate expression (matches
    # `_AGGREGATE_RE` — fires a count query) OR a literal string
    # (renders verbatim — v0.61.66 AegisMark UX patterns #4). RBAC
    # scope rules apply per stage for the aggregate path. Stages with
    # empty value render `—`. Median and other not-yet-supported
    # aggregates also render `—` (only count is wired today).
    # Mirrors the action_grid pattern (#891).
    pipeline_stage_data: list[dict[str, Any]] = []
    if ctx.ctx_region.display == "PIPELINE_STEPS":
        _stages = ctx.ctx_region.pipeline_stages or []
        if _stages and not _scope_denied:
            # Per-field task buckets — value (existing) and progress (#911).
            # Each bucket is keyed by stage index so we can stitch results
            # back into pipeline_stage_data after a single asyncio.gather.
            _stage_tasks: list[Any] = []
            _stage_task_keys: list[tuple[int, str]] = []  # (stage_idx, "value"|"progress")
            _stage_literals: dict[tuple[int, str], str] = {}  # (idx, field) → literal

            def _queue_stage_field(_sidx: int, _field: str, _expr: str) -> None:
                """Dispatch one stage field (value or progress) to either the
                literal stash or an async count-metric task. Cross-entity
                aggregates run unscoped with a warning, mirroring action_grid
                (#901)."""
                if not _expr:
                    return
                _m = _AGGREGATE_RE.match(_expr)
                if not _m:
                    _stage_literals[(_sidx, _field)] = _expr
                    return
                _func, _entity_name, _where = _m.groups()
                _agg_repo = ctx.repositories.get(_entity_name) if ctx.repositories else None
                if _func != "count" or _agg_repo is None:
                    return
                _stage_scope = _scope_only_filters if _entity_name == ctx.source else None
                if _stage_scope is None and _scope_only_filters is not None:
                    logger.warning(
                        "pipeline_steps stage %d %s (entity=%s, source=%s): "
                        "cross-entity count is unscoped — destination entity's "
                        "own RBAC at navigation time still applies, but the "
                        "stage %s shows ALL rows the runtime can read",
                        _sidx,
                        _field,
                        _entity_name,
                        ctx.source,
                        _field,
                    )
                _stage_tasks.append(
                    _fetch_count_metric(
                        f"pipeline_stage_{_sidx}_{_field}",
                        _agg_repo,
                        _where,
                        _stage_scope,
                        source_entity=_entity_name,
                    )
                )
                _stage_task_keys.append((_sidx, _field))

            for _sidx, _stage in enumerate(_stages):
                _queue_stage_field(_sidx, "value", _stage.get("value") or "")
                _queue_stage_field(_sidx, "progress", _stage.get("progress") or "")

            _stage_results: dict[tuple[int, str], Any] = {}
            if _stage_tasks:
                import asyncio as _asyncio

                _sresults = await _asyncio.gather(*_stage_tasks, return_exceptions=True)
                for _key, _srresult in zip(_stage_task_keys, _sresults, strict=True):
                    if isinstance(_srresult, tuple):
                        _stage_results[_key] = _srresult[1]
                    else:
                        logger.warning(
                            "pipeline_steps stage %d %s query failed: %s",
                            _key[0],
                            _key[1],
                            _srresult,
                        )

            for _sidx, _stage in enumerate(_stages):
                # Literal beats aggregate result: any stage parsed as a
                # literal short-circuits before the query path even ran.
                _val: Any = _stage_literals.get(
                    (_sidx, "value"), _stage_results.get((_sidx, "value"))
                )
                _prog_raw: Any = _stage_literals.get(
                    (_sidx, "progress"), _stage_results.get((_sidx, "progress"))
                )
                _prog_clamped, _prog_overshoot = _coerce_pipeline_progress(_prog_raw)
                pipeline_stage_data.append(
                    {
                        "label": _stage.get("label", ""),
                        "caption": _stage.get("caption", ""),
                        "value": _val,
                        "progress": _prog_clamped,
                        "progress_overshoot": _prog_overshoot,
                    }
                )
        elif _stages:
            # scope denied — render stages with no values (—) for
            # aggregate stages, but keep literals (they don't depend
            # on scope). Same logic for progress: literal numerics
            # render unchanged; aggregate progress is suppressed.
            for _stage in _stages:
                _expr = _stage.get("value") or ""
                _is_literal = bool(_expr) and not _AGGREGATE_RE.match(_expr)
                _prog_expr = _stage.get("progress") or ""
                _prog_is_literal = bool(_prog_expr) and not _AGGREGATE_RE.match(_prog_expr)
                _prog_raw = _prog_expr if _prog_is_literal else None
                _prog_clamped, _prog_overshoot = _coerce_pipeline_progress(_prog_raw)
                pipeline_stage_data.append(
                    {
                        "label": _stage.get("label", ""),
                        "caption": _stage.get("caption", ""),
                        "value": _expr if _is_literal else None,
                        "progress": _prog_clamped,
                        "progress_overshoot": _prog_overshoot,
                    }
                )

    # Profile card (#892, v0.61.55): single-record identity panel.
    # Resolves the avatar, primary, secondary, stats, and facts from
    # the first item already fetched (the region's `filter:` should
    # narrow to one record — typically `id = current_context`).
    # Secondary + facts strings support tiny `{{ field }}` /
    # `{{ field.path }}` interpolation against the item dict — handled
    # server-side by `_interpolate_card_template` so the template is
    # logic-less. No Jinja eval, no expressions.
    profile_card_data: dict[str, Any] = {}
    if ctx.ctx_region.display == "PROFILE_CARD":
        _item = items[0] if items else None
        if _item is not None:
            _avatar_field = ctx.ctx_region.avatar_field
            _primary_field = ctx.ctx_region.primary
            _secondary_tmpl = ctx.ctx_region.secondary
            _stats_specs = ctx.ctx_region.profile_stats or []
            _fact_tmpls = ctx.ctx_region.facts or []
            _avatar_url = ""
            if _avatar_field:
                _av = _resolve_path(_item, _avatar_field)
                _avatar_url = str(_av or "")
            _primary_str = ""
            if _primary_field:
                _pv = _resolve_path(_item, _primary_field)
                _primary_str = str(_pv or "")
            _initials = _initials_from(_primary_str)
            # v0.61.80 (#910 follow-up): `_stats_specs` is a list of
            # `{label, value}` dicts coming through the IR→template-context
            # boundary in `workspace_renderer.py` (see line 569: `profile_stats=
            # [{"label": s.label, "value": s.value} for s in ...]`). The pre-fix
            # code accessed `_stat.label` (attribute), which silently worked
            # only when `items` was empty so the `if _item is not None` branch
            # never ran — pre-#909 every prod call had wrong-bound scope filters
            # that emptied items. The #910 fix restored items, surfacing the
            # AttributeError as a 500. Use dict access to match the boundary.
            profile_card_data = {
                "avatar_url": _avatar_url,
                "initials": _initials,
                "primary": _primary_str,
                "secondary": _interpolate_card_template(_secondary_tmpl or "", _item),
                "stats": [
                    {
                        "label": _stat["label"],
                        "value": str(_resolve_path(_item, _stat["value"]) or ""),
                    }
                    for _stat in _stats_specs
                ],
                "facts": [_interpolate_card_template(_fact, _item) for _fact in _fact_tmpls],
            }

    # v0.61.72 (#6): confirm_action_panel reads state_value from the
    # entity field named by `state_field` so the template can branch
    # between off / live / revoked render modes. Reads from the first
    # fetched item (callers typically narrow with `filter:`). Empty
    # string when no field configured or no item — template falls
    # through to the safe default ("off").
    confirm_state_value: str = ""
    if ctx.ctx_region.display == "CONFIRM_ACTION_PANEL":
        _state_field = getattr(ctx.ctx_region, "state_field", None)
        if _state_field and items:
            _val = _resolve_path(items[0], _state_field)
            confirm_state_value = str(_val or "")

    # Multi-dimension aggregate for pivot_table (cycle 25) and area_chart
    # (cycle 28 — stacked time-series). Reads `group_by_dims` from the IR
    # and runs ONE multi-dim GROUP BY via Repository.aggregate. Each entry
    # is a column on the source entity or a BucketRef for time-bucketed
    # dims; FK columns auto-LEFT JOIN their target so the bucket carries
    # the resolved display field.
    # SECURITY (#887): same gating — `_compute_pivot_buckets` runs a
    # multi-dim GROUP BY query and would expose unscoped tenant rows.
    pivot_buckets: list[dict[str, Any]] = []
    pivot_dim_specs: list[dict[str, Any]] = []
    _multi_dim_modes = {"PIVOT_TABLE", "AREA_CHART"}
    _ir_group_by_dims = getattr(ctx.ir_region, "group_by_dims", None) if ctx.ir_region else None
    if (
        ctx.ctx_region.display in _multi_dim_modes
        and _ir_group_by_dims
        and ctx.ctx_region.aggregates
        and not _scope_denied
    ):
        pivot_buckets, pivot_dim_specs = await _compute_pivot_buckets(
            ctx.ctx_region.aggregates,
            ctx.repositories,
            _ir_group_by_dims,
            source_entity=ctx.source,
            source_entity_spec=ctx.entity_spec,
            scope_filters=_scope_only_filters,
        )

    # Queue display: extract state machine transitions for inline action buttons
    queue_transitions: list[dict[str, str]] = []
    queue_status_field = ""
    queue_api_endpoint = ""
    if ctx.ctx_region.display == "QUEUE" and ctx.entity_spec:
        sm = ctx.entity_spec.state_machine
        if sm:
            queue_status_field = sm.status_field
            seen: set[str] = set()
            for t in sm.transitions:
                to_state = t.to_state if isinstance(t.to_state, str) else str(t.to_state)
                if to_state not in seen:
                    seen.add(to_state)
                    queue_transitions.append(
                        {
                            "to_state": to_state,
                            "label": to_state.replace("_", " ").title(),
                        }
                    )
        # API endpoint for PUT transitions
        from dazzle.core.strings import to_api_plural

        queue_api_endpoint = f"/{to_api_plural(ctx.source)}"

    # Multi-source tabbed regions pass source_tabs to the template
    source_tabs = ctx.ctx_region.source_tabs or []

    # Tree display (#565) — build nested tree from flat items using group_by as parent ref
    tree_items: list[dict[str, Any]] = []

    # Heatmap: pivot flat items into a matrix structure (v0.44.0)
    heatmap_matrix: list[dict[str, Any]] = []
    heatmap_col_values: list[str] = []
    # Resolve heatmap_thresholds — check IR for ParamRef (#572, #575)
    _ir_thresholds = getattr(ctx.ir_region, "heatmap_thresholds", None)
    if hasattr(_ir_thresholds, "key"):  # ParamRef in IR
        from dazzle.back.runtime.param_store import resolve_value

        _resolved = resolve_value(
            _ir_thresholds,
            getattr(ctx, "param_resolver", None),
            tenant_id=getattr(ctx, "tenant_id", None),
        )
        # Fall back to ctx_region defaults when runtime has no override (#586)
        heatmap_thresholds: list[float] = list(
            _resolved or getattr(ctx.ctx_region, "heatmap_thresholds", None) or []
        )
    else:
        heatmap_thresholds = list(getattr(ctx.ctx_region, "heatmap_thresholds", None) or [])
    if ctx.ctx_region.display == "HEATMAP" and items:
        hm_rows_field = getattr(ctx.ctx_region, "heatmap_rows", "") or ""
        hm_cols_field = getattr(ctx.ctx_region, "heatmap_columns", "") or ""
        hm_value_field = getattr(ctx.ctx_region, "heatmap_value", "") or ""
        # Collect unique column values and build pivot
        # Use _display sibling keys injected by _inject_display_names() (#586)
        col_set: set[str] = set()
        for item in items:
            cv = str(item.get(f"{hm_cols_field}_display", "")) or _resolve_display_name(
                item.get(hm_cols_field, "")
            )
            if cv:
                col_set.add(cv)
        heatmap_col_values = sorted(col_set)
        # Group by row → column → value; track raw row IDs for action URLs
        row_map: dict[str, dict[str, float]] = {}
        row_ids: dict[str, str] = {}
        for item in items:
            rv = str(item.get(f"{hm_rows_field}_display", "")) or _resolve_display_name(
                item.get(hm_rows_field, "")
            )
            cv = str(item.get(f"{hm_cols_field}_display", "")) or _resolve_display_name(
                item.get(hm_cols_field, "")
            )
            val = float(item.get(hm_value_field, 0) or 0)
            if rv not in row_map:
                row_map[rv] = {}
            row_map[rv][cv] = val
            # Store raw row ID for action URL interpolation.
            # When the FK is expanded (dict), use its "id"; when it's a plain
            # UUID string, that IS the target entity ID — don't fall back to
            # the source item's own id (#633).
            raw_row = item.get(hm_rows_field)
            if isinstance(raw_row, dict):
                row_id = str(raw_row.get("id", ""))
            elif raw_row:
                row_id = str(raw_row)
            else:
                row_id = str(item.get("id", ""))
            row_ids[rv] = row_id
        for row_label in sorted(row_map.keys()):
            cells: list[dict[str, Any]] = []
            for col_label in heatmap_col_values:
                cell_val = row_map[row_label].get(col_label, 0.0)
                cells.append({"value": cell_val, "column": col_label})
            heatmap_matrix.append(
                {"row": row_label, "row_id": row_ids.get(row_label, ""), "cells": cells}
            )

    # Progress: count items per stage and compute percentage (v0.44.0)
    progress_stage_counts: list[dict[str, Any]] = []
    progress_total = 0
    progress_complete_count = 0
    progress_complete_pct = 0.0
    progress_stages_list: list[str] = list(getattr(ctx.ctx_region, "progress_stages", None) or [])
    progress_complete_at: str = getattr(ctx.ctx_region, "progress_complete_at", "") or ""
    if ctx.ctx_region.display == "PROGRESS" and items and progress_stages_list:
        stage_counter: dict[str, int] = dict.fromkeys(progress_stages_list, 0)
        status_field = group_by or "status"
        for item in items:
            item_stage = str(item.get(status_field, ""))
            if item_stage in stage_counter:
                stage_counter[item_stage] += 1
        progress_total = sum(stage_counter.values())
        # Find the index of complete_at stage; everything at or past it is "complete"
        complete_idx = -1
        if progress_complete_at in progress_stages_list:
            complete_idx = progress_stages_list.index(progress_complete_at)
        for i, stage_name in enumerate(progress_stages_list):
            cnt = stage_counter.get(stage_name, 0)
            is_complete = complete_idx >= 0 and i >= complete_idx
            progress_stage_counts.append(
                {"name": stage_name, "count": cnt, "complete": is_complete}
            )
            if is_complete:
                progress_complete_count += cnt
        if progress_total > 0:
            progress_complete_pct = round(progress_complete_count / progress_total * 100, 1)

    # Tree display (#565) — build nested hierarchy from flat items
    display_upper = ctx.ctx_region.display
    if display_upper == "TREE" and group_by and items:
        items_by_id = {str(item.get("id", "")): item for item in items}
        children_map: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            parent_id = str(item.get(group_by, "") or "")
            children_map.setdefault(parent_id, []).append(item)

        # Root items have no parent or parent not in the set
        roots = [item for item in items if str(item.get(group_by, "") or "") not in items_by_id]

        def _build_subtree(node: dict[str, Any]) -> dict[str, Any]:
            node_id = str(node.get("id", ""))
            node["_children"] = children_map.get(node_id, [])
            for child in node["_children"]:
                _build_subtree(child)
            return node

        tree_items = [_build_subtree(r) for r in roots]

    # Phase 4 region migration (v0.67.46): the typed-primitive path
    # extends beyond the original #1015–#1018 special cases. Region
    # kinds whose adapter builder is mature + whose data shape matches
    # the legacy Jinja partial's expectations are listed here; they
    # bypass the Jinja body in favour of FragmentRenderer output.
    # Adding a new display value is one entry in this whitelist plus
    # a matching `adapter_ctx[...]` population below.
    typed_primitive_html: str = ""
    _TYPED_REGION_DISPLAYS = (
        "COHORT_STRIP",
        "DAY_TIMELINE",
        "TASK_INBOX",
        "ENTITY_CARD",
        "PROGRESS",  # Phase 4 region migration (v0.67.46)
        # Phase 4 region migration batch (v0.67.47):
        "DETAIL",
        "TREE",
        "DIAGRAM",
        "SEARCH_BOX",
        "TABBED_LIST",
        # Phase 4 region migration batch (v0.67.48):
        "GRID",
        "HEATMAP",
        "SPARKLINE",
        "STATUS_LIST",
        "PROFILE_CARD",
        # Phase 4 region migration batch (v0.67.49):
        "METRICS",
        "FUNNEL_CHART",
        "HISTOGRAM",
        "PIVOT_TABLE",
        "TIMELINE",
        "KANBAN",
        "PIPELINE_STEPS",
        "QUEUE",
        "ACTION_GRID",
        "CONFIRM_ACTION_PANEL",
        # Phase 4 region migration batch (v0.67.50): chart + specialty:
        "BAR_CHART",
        "LINE_CHART",
        "AREA_CHART",
        "BAR_TRACK",
        "BULLET",
        "BOX_PLOT",
        "ACTIVITY_FEED",
        # Phase 4 region migration (v0.67.51): foundational list-view
        # — the richest ctx contract (sort/filter state, FilterBar,
        # CSV export, date-range picker, RBAC propagation, bulk
        # actions plumbing).
        "LIST",
        # Phase 4 region migration (v0.67.70): radar polar chart —
        # `_build_radar` consumes (label, value) axis pairs from the
        # legacy `bucketed_metrics` shape; the typed Radar primitive
        # does its own polygon/polar math.
        "RADAR",
    )
    if display_upper in _TYPED_REGION_DISPLAYS:
        from dazzle.back.runtime.renderers.region_adapter import WorkspaceRegionAdapter
        from dazzle.render.fragment import FragmentRenderer

        # Adapter wants the lowercase display value (its _BUILDERS
        # keys) on `region.display`, plus the IR config slots. Use
        # the IR region directly — it carries the typed configs.
        ir_region = ctx.ir_region or ctx.ctx_region
        # Force a lowercase display value if the IR carries the
        # uppercase enum (defensive — most callers already lowercase).
        _display_obj = getattr(ir_region, "display", None)
        _display_val = getattr(_display_obj, "value", None) or str(_display_obj or "")
        if _display_val and _display_val.upper() == display_upper:
            adapter_ctx: dict[str, Any] = {
                "region_url": getattr(ctx.ctx_region, "endpoint", "") or "",
            }
            # Per-display data resolution. Each branch reads its own
            # typed config off the IR region and shapes `items` (or
            # other already-scoped data) into the dict shape the
            # adapter consumes. Empty config = empty/unconfigured state
            # in the primitive (handled by the adapter).
            if display_upper == "COHORT_STRIP":
                _cohort_cfg = getattr(ir_region, "cohort_strip_config", None)
                if _cohort_cfg is not None:
                    _active_lens_id = (
                        request.query_params.get("lens")
                        or getattr(_cohort_cfg, "default_lens", "")
                        or (getattr(_cohort_cfg.lenses[0], "id", "") if _cohort_cfg.lenses else "")
                    )
                    adapter_ctx["cohort_active_lens"] = _active_lens_id
                    adapter_ctx["cohort_cells"] = _build_cohort_cells(
                        items=items,
                        config=_cohort_cfg,
                        active_lens_id=_active_lens_id,
                    )
            elif display_upper == "DAY_TIMELINE":
                _day_cfg = getattr(ir_region, "day_timeline_config", None)
                if _day_cfg is not None:
                    adapter_ctx["day_timeline_slots"] = _build_day_timeline_slots(
                        items=items,
                        config=_day_cfg,
                        now=_dt.datetime.now(_dt.UTC),
                    )
            elif display_upper == "TASK_INBOX":
                _inbox_cfg = getattr(ir_region, "task_inbox_config", None)
                if _inbox_cfg is not None:
                    # #1015 (v0.67.16) — fan out per-source queries in
                    # parallel, scope each against its own entity's
                    # access spec, pass the items_per_source dict to
                    # the helper. Falls through to single-source MVP
                    # when the fan-out produces an empty dict (e.g.
                    # repositories not yet wired in test contexts).
                    _items_per_source = await _fetch_task_inbox_items_per_source(
                        config=_inbox_cfg,
                        ctx=ctx,
                        request=request,
                        auth_context=_auth_ctx_for_filters,
                        user_id=_current_user_id,
                    )
                    inbox_items, inbox_chips = _build_task_inbox_payload(
                        items=items,
                        config=_inbox_cfg,
                        items_per_source=_items_per_source,
                    )
                    adapter_ctx["task_inbox_items"] = inbox_items
                    adapter_ctx["task_inbox_chips"] = inbox_chips
            elif display_upper == "PROGRESS":
                # Phase 4 region migration (v0.67.46): progress's
                # adapter builder consumes pre-computed stage rollups
                # from `progress_stage_counts` etc. already populated
                # upstream in this function.
                adapter_ctx["stage_counts"] = progress_stage_counts
                adapter_ctx["progress_total"] = progress_total
                adapter_ctx["complete_count"] = progress_complete_count
                adapter_ctx["complete_pct"] = progress_complete_pct
                # Legacy `items` fallback the adapter's _build_progress
                # accepts when stage_counts is empty — pass through so
                # the synthetic-stage path keeps working.
                adapter_ctx["items"] = items
            elif display_upper == "DETAIL":
                # Phase 4 region migration batch (v0.67.47): detail's
                # adapter consumes a single record + the region's
                # declared field shape.
                adapter_ctx["item"] = items[0] if items else None
                adapter_ctx["fields"] = columns
            elif display_upper == "TREE":
                # _build_tree wants the pre-computed nested tree shape
                # already produced upstream by `_build_subtree`.
                adapter_ctx["tree_items"] = tree_items
                adapter_ctx["items"] = items
                adapter_ctx["display_key"] = next(
                    (c["key"] for c in columns if c.get("type") not in ("badge", "ref")),
                    columns[0]["key"] if columns else "name",
                )
            elif display_upper == "DIAGRAM":
                # _build_diagram prefers `diagram_data` (Mermaid source)
                # but falls back to nodes/edges from the IR region
                # when not pre-computed.
                adapter_ctx["nodes"] = getattr(ctx.ctx_region, "nodes", []) or []
                adapter_ctx["edges"] = getattr(ctx.ctx_region, "edges", []) or []
            elif display_upper == "SEARCH_BOX":
                # _build_search_box wants source_entity + region name +
                # optional placeholder/coaching message.
                adapter_ctx["source_entity"] = getattr(ctx, "source", "") or ""
                adapter_ctx["name"] = getattr(ctx.ctx_region, "name", "")
                adapter_ctx["placeholder"] = getattr(ctx.ctx_region, "search_placeholder", "") or ""
                adapter_ctx["coaching_message"] = (
                    getattr(ctx.ctx_region, "coaching_message", "") or ""
                )
            elif display_upper == "TABBED_LIST":
                # _build_tabbed_list prefers `source_tabs` (HTMX-driven
                # lazy panels) which the runtime already computed
                # upstream from the IR region's source declarations.
                adapter_ctx["region_name"] = getattr(ctx.ctx_region, "name", "")
                adapter_ctx["source_tabs"] = source_tabs
            elif display_upper == "GRID":
                # Phase 4 region migration batch (v0.67.48): grid renders
                # card cells from the scoped item rows + the region's
                # column declarations.
                adapter_ctx["items"] = items
                adapter_ctx["columns"] = columns
                adapter_ctx["display_key"] = next(
                    (c["key"] for c in columns if c.get("type") not in ("badge", "ref")),
                    columns[0]["key"] if columns else "name",
                )
                adapter_ctx["entity_name"] = ctx.source
            elif display_upper == "HEATMAP":
                # Threshold-tinted matrix from pre-computed aggregates.
                adapter_ctx["heatmap_matrix"] = heatmap_matrix
                adapter_ctx["heatmap_col_values"] = heatmap_col_values
                adapter_ctx["heatmap_thresholds"] = heatmap_thresholds
                adapter_ctx["total"] = total
                adapter_ctx["items"] = items
            elif display_upper == "SPARKLINE":
                # Sparkline is a TimeSeries view variant; its adapter
                # builder reads `points` as a list of label/value
                # tuples or dicts. `bucketed_metrics` is already that
                # shape.
                adapter_ctx["points"] = bucketed_metrics
                adapter_ctx["chart_label"] = ctx.ctx_region.title
            elif display_upper == "STATUS_LIST":
                # Authored entries forwarded directly from the IR region
                # — no per-request resolution needed (#3, v0.61.69).
                adapter_ctx["status_entries"] = getattr(ctx.ctx_region, "status_entries", [])
            elif display_upper == "PROFILE_CARD":
                # Pre-assembled identity-panel dict — built upstream in
                # this function around line 2424.
                adapter_ctx["profile_card_data"] = profile_card_data
            elif display_upper == "METRICS":
                # Phase 4 region migration batch (v0.67.49): metrics
                # tiles read pre-computed aggregate values + columns.
                adapter_ctx["metrics"] = metrics
                adapter_ctx["columns"] = columns
            elif display_upper == "FUNNEL_CHART":
                # Funnel uses kanban_columns for stage order +
                # bucketed_metrics for per-stage counts.
                adapter_ctx["kanban_columns"] = kanban_columns
                adapter_ctx["bucketed_metrics"] = bucketed_metrics
            elif display_upper == "HISTOGRAM":
                # Pre-computed bins from `_compute_histogram_bins`.
                adapter_ctx["histogram_bins"] = histogram_bins
                adapter_ctx["reference_lines"] = getattr(ctx.ctx_region, "reference_lines", [])
            elif display_upper == "PIVOT_TABLE":
                # Multi-dim pivot: workspace-shape primitive consumes
                # pivot_buckets + pivot_dim_specs directly.
                adapter_ctx["pivot_buckets"] = pivot_buckets
                adapter_ctx["pivot_dim_specs"] = pivot_dim_specs
                adapter_ctx["bucketed_metrics"] = bucketed_metrics
                adapter_ctx["columns"] = columns
            elif display_upper == "TIMELINE":
                # Timeline events from scoped items + column declarations.
                adapter_ctx["items"] = items
                adapter_ctx["columns"] = columns
                adapter_ctx["display_key"] = next(
                    (c["key"] for c in columns if c.get("type") not in ("badge", "ref")),
                    columns[0]["key"] if columns else "name",
                )
            elif display_upper == "KANBAN":
                # KanbanRegion workspace-shape: items + status order
                # + columns + display_key.
                adapter_ctx["items"] = items
                adapter_ctx["columns"] = columns
                adapter_ctx["kanban_columns"] = kanban_columns
                adapter_ctx["display_key"] = next(
                    (c["key"] for c in columns if c.get("type") not in ("badge", "ref")),
                    columns[0]["key"] if columns else "name",
                )
                adapter_ctx["group_by"] = (
                    group_by.field if isinstance(group_by, _BucketRef) else group_by
                )
            elif display_upper == "PIPELINE_STEPS":
                # Pre-computed per-stage rollups from upstream.
                adapter_ctx["pipeline_stage_data"] = pipeline_stage_data
            elif display_upper == "QUEUE":
                # Review queue: items + state-transition wiring + the
                # filter-chrome contract _build_list shares.
                adapter_ctx["items"] = items
                adapter_ctx["columns"] = columns
                adapter_ctx["total"] = total
                adapter_ctx["metrics"] = metrics
                adapter_ctx["queue_transitions"] = queue_transitions
                adapter_ctx["queue_status_field"] = queue_status_field
                adapter_ctx["queue_api_endpoint"] = queue_api_endpoint
            elif display_upper == "ACTION_GRID":
                # Pre-assembled CTA card list (legacy alias
                # `action_card_data` is the actual upstream name).
                adapter_ctx["action_cards"] = action_card_data
            elif display_upper == "BAR_CHART":
                # Phase 4 region migration batch (v0.67.50): bar_chart's
                # adapter consumes `buckets` (list of label/count
                # tuples or dicts). bucketed_metrics is already the
                # right dict shape.
                adapter_ctx["buckets"] = bucketed_metrics
                adapter_ctx["chart_label"] = ctx.ctx_region.title
            elif display_upper == "RADAR":
                # Phase 4 region migration (v0.67.70): radar consumes
                # `axes` (label, value) pairs. The legacy template iterated
                # `bucketed_metrics` and read each entry's `label` + `value`
                # — same source, simpler shape here.
                radar_axes: list[tuple[str, float]] = []
                for entry in bucketed_metrics or []:
                    if not isinstance(entry, dict):
                        continue
                    label = str(entry.get("label", "") or "")
                    raw_val = entry.get("value", 0) or 0
                    try:
                        val = float(raw_val)
                    except (TypeError, ValueError):
                        val = 0.0
                    if label:
                        radar_axes.append((label, val))
                adapter_ctx["axes"] = radar_axes
                adapter_ctx["chart_label"] = ctx.ctx_region.title
            elif display_upper in ("LINE_CHART", "AREA_CHART"):
                # TimeSeries variants: both read `points` from the
                # same upstream `bucketed_metrics`. Reference lines /
                # bands / overlay series flow through too.
                adapter_ctx["points"] = bucketed_metrics
                adapter_ctx["chart_label"] = ctx.ctx_region.title
                adapter_ctx["reference_lines"] = getattr(ctx.ctx_region, "reference_lines", [])
                adapter_ctx["reference_bands"] = getattr(ctx.ctx_region, "reference_bands", [])
                adapter_ctx["overlay_series_data"] = overlay_series_data
            elif display_upper == "BAR_TRACK":
                # Pre-computed per-row {label, value, fill_pct,
                # formatted_value} from `_compute_bar_track_rows`.
                adapter_ctx["bar_track_rows"] = bar_track_rows
                adapter_ctx["bar_track_max"] = bar_track_max
            elif display_upper == "BULLET":
                # Pre-computed per-row {label, actual, target} from
                # `_compute_bullet_rows`.
                adapter_ctx["bullet_rows"] = bullet_rows
                adapter_ctx["bullet_max_value"] = bullet_max_value
            elif display_upper == "BOX_PLOT":
                # Per-group quartile stats from `_compute_box_plot_stats`.
                adapter_ctx["box_plot_stats"] = box_plot_stats
            elif display_upper == "ACTIVITY_FEED":
                # Items carry actor/description/created_at — the adapter
                # reads them directly off the row dicts.
                adapter_ctx["items"] = items
            elif display_upper == "LIST":
                # Phase 4 region migration (v0.67.51): foundational
                # list-view. Read all the chrome contract (filter bar,
                # date range, CSV, sort headers) plus row data.
                adapter_ctx["items"] = items
                adapter_ctx["columns"] = columns
                adapter_ctx["total"] = total
                adapter_ctx["endpoint"] = ctx.ctx_region.endpoint
                adapter_ctx["region_name"] = getattr(ctx.ctx_region, "name", "")
                adapter_ctx["filter_columns"] = filter_columns
                adapter_ctx["active_filters"] = active_filters
                adapter_ctx["date_range"] = getattr(ctx.ctx_region, "date_range", False)
                adapter_ctx["date_field"] = getattr(ctx.ctx_region, "date_field", "")
                adapter_ctx["date_from"] = request.query_params.get("date_from", "")
                adapter_ctx["date_to"] = request.query_params.get("date_to", "")
                adapter_ctx["csv_export"] = getattr(ctx.ctx_region, "csv_export", False)
                adapter_ctx["sort_field"] = sort or ""
                adapter_ctx["sort_dir"] = dir
                adapter_ctx["empty_message"] = (
                    ctx.surface_empty_message or ctx.ctx_region.empty_message
                )
            elif display_upper == "CONFIRM_ACTION_PANEL":
                # ConfirmGate full state machine — IR-level fields plus
                # the request-time state value.
                adapter_ctx["state_value"] = confirm_state_value
                adapter_ctx["confirmations"] = getattr(ctx.ctx_region, "confirmations", [])
                adapter_ctx["primary_action_url"] = getattr(
                    ctx.ctx_region, "primary_action_url", ""
                )
                adapter_ctx["secondary_action_url"] = getattr(
                    ctx.ctx_region, "secondary_action_url", ""
                )
                adapter_ctx["revoke_url"] = getattr(ctx.ctx_region, "revoke_url", "")
                adapter_ctx["audit_enabled"] = getattr(ctx.ctx_region, "audit_enabled", False)
            elif display_upper == "ENTITY_CARD":
                _card_cfg = getattr(ir_region, "entity_card_config", None)
                if _card_cfg is not None:
                    # #1017 (v0.67.18) — per-section fan-out for modes
                    # that pull from related entities (mini_bars, stamps,
                    # thread_summary). Sections without their own
                    # `source:` (halo / flags / quick_actions) skip the
                    # fan-out and read from the scoped record directly.
                    _rows_per_section = await _fetch_entity_card_section_rows(
                        config=_card_cfg,
                        ctx=ctx,
                        request=request,
                        auth_context=_auth_ctx_for_filters,
                        user_id=_current_user_id,
                    )
                    adapter_ctx["entity_card_sections"] = _build_entity_card_sections(
                        items=items,
                        config=_card_cfg,
                        rows_per_section=_rows_per_section,
                    )
                    if items:
                        # Heading from the resolved single record's
                        # `name` / `title` / `message` field — first
                        # row scoped via the `scope_param` URL parameter
                        # which the upstream filter machinery already
                        # applied. Empty when no record matched.
                        record = items[0]
                        adapter_ctx["entity_card_record_label"] = str(
                            record.get("name") or record.get("title") or record.get("message") or ""
                        )
            try:
                surface = WorkspaceRegionAdapter().build(ir_region, adapter_ctx)
                inner = getattr(getattr(surface, "body", None), "body", None)
                fragment_to_render = inner if inner is not None else surface
                typed_primitive_html = FragmentRenderer().render(fragment_to_render)
            except Exception as exc:  # noqa: BLE001 — surface to operator log
                logger.error(
                    "typed-primitive render failed for %s region %s: %s",
                    display_upper,
                    getattr(ctx.ctx_region, "name", "?"),
                    exc,
                )
                typed_primitive_html = (
                    '<p class="dz-empty-dense" role="status">'
                    "Typed primitive render failed; check server logs."
                    "</p>"
                )

    # Phase 4 (v0.67.70): every region display now resolves to
    # `_typed_primitive.html`. The Jinja fallback path is gone — the
    # typed substrate is the only render path.
    import html as _html_mod

    region_name_attr = _html_mod.escape(ctx.ctx_region.name, quote=True)
    html = (
        f'<div data-dz-region data-dz-region-name="{region_name_attr}" '
        f'id="region-{region_name_attr}">'
        f"{typed_primitive_html or ''}"
        f"</div>"
    )
    return HTMLResponse(content=html)


async def _fetch_region_json(
    request: Any,
    page: int,
    page_size: int,
    ctx: WorkspaceRegionContext,
    filter_context: dict[str, Any] | None = None,
    *,
    auth_context: Any = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Fetch a single region's data as JSON for batch responses."""
    repo = ctx.repositories.get(ctx.source) if ctx.repositories else None
    items: list[dict[str, Any]] = []
    total = 0

    # SECURITY (#887): mirror `_workspace_region_handler` — default-deny
    # scope state so a missing repo or early exception doesn't bypass
    # the gate on `_compute_aggregate_metrics` below.
    _scope_only_filters_batch: dict[str, Any] | None = None
    _scope_denied: bool = True

    if repo:
        try:
            filters: dict[str, Any] | None = None
            ir_filter = ctx.ir_region.filter
            if ir_filter is not None:
                try:
                    from dazzle.back.runtime.route_generator import (
                        _extract_condition_filters,
                    )

                    filters = {}
                    _extract_condition_filters(
                        ir_filter,
                        user_id or (filter_context or {}).get("current_user_id", ""),
                        filters,
                        logger,
                        auth_context,
                        context_id=(filter_context or {}).get("current_context"),
                    )
                    if not filters:
                        filters = None
                except Exception:
                    logger.warning("Failed to evaluate condition filter for region", exc_info=True)

            sort_list: list[str] | None = None
            ir_sort = ctx.ir_region.sort
            if ir_sort:
                sort_list = [f"-{s.field}" if s.direction == "desc" else s.field for s in ir_sort]

            # SECURITY: apply entity-level scope predicates (#574).
            # Capture scope-only filters (without other request filters
            # mixed in) so `_compute_aggregate_metrics` below can run a
            # scope-aware aggregate query — unfiltered aggregates leak
            # cross-tenant counts (#887).
            _scope_only_filters_batch, _scope_denied = _apply_workspace_scope_filters(
                ctx, auth_context, user_id, None
            )
            if _scope_only_filters_batch:
                filters = {**(filters or {}), **_scope_only_filters_batch}

            limit = ctx.ctx_region.limit or page_size
            include_rels = ctx.auto_include or None
            if _scope_denied:
                result = {"items": [], "total": 0}
            else:
                result = await repo.list(
                    page=page,
                    page_size=limit,
                    filters=filters,
                    sort=sort_list,
                    include=include_rels,
                    fk_display_only=True,
                )
            if isinstance(result, dict):
                _result: dict[str, Any] = result
                raw_items = _result.get("items", [])
                total = _result.get("total", 0)
                items = [i.model_dump() if hasattr(i, "model_dump") else dict(i) for i in raw_items]
                items = [_inject_display_names(item) for item in items]

            # Zero results is valid — the region shows its empty: message.
            # Do NOT fall back to unfiltered queries (#546).
        except Exception as exc:
            # #935: ERROR-level + structured (see _workspace_region_handler
            # above for rationale). Same fail-closed semantics.
            logger.error(
                "workspace_region_query_failed entity=%s region=%s exc=%s context=batch",
                ctx.source,
                ctx.ctx_region.name,
                type(exc).__name__,
                exc_info=True,
            )

    # SECURITY (#887): suppress aggregates when scope is denied AND
    # propagate the scope-only filters so the aggregate query stays
    # tenant-bounded for the legitimate case.
    metrics: list[dict[str, Any]] = []
    if ctx.ctx_region.aggregates and not _scope_denied:
        metrics = await _compute_aggregate_metrics(
            ctx.ctx_region.aggregates,
            ctx.repositories,
            total,
            items,
            scope_filters=_scope_only_filters_batch,
            source_entity=ctx.source,  # #888 Phase 1
            tones=getattr(ctx.ctx_region, "tones", None),  # v0.61.65
        )

    return {
        "region": ctx.ctx_region.name,
        "items": items,
        "total": total,
        "metrics": metrics,
    }


async def _workspace_batch_handler(
    request: Any,
    page: int,
    page_size: int,
    region_ctxs: list[WorkspaceRegionContext],
) -> dict[str, Any]:
    """Fetch all workspace regions concurrently and return combined JSON."""
    from fastapi import HTTPException

    # Enforce auth on any region that requires it
    for ctx in region_ctxs:
        if ctx.require_auth:
            auth_ctx = None
            if ctx.auth_middleware:
                try:
                    auth_ctx = ctx.auth_middleware.get_auth_context(request)
                except Exception:
                    logger.warning(
                        "Failed to get auth context for batch workspace request", exc_info=True
                    )
            if not (auth_ctx and auth_ctx.is_authenticated):
                raise HTTPException(status_code=401, detail="Authentication required")
            if ctx.ws_access and ctx.ws_access.allow_personas and auth_ctx:
                is_super = auth_ctx.user and auth_ctx.user.is_superuser
                normalized_roles = [r.removeprefix("role_") for r in auth_ctx.roles]
                if not is_super and not any(
                    r in ctx.ws_access.allow_personas for r in normalized_roles
                ):
                    raise HTTPException(status_code=403, detail="Workspace access denied")
            break  # All regions share the same workspace access

    # Resolve current user entity ID for filter context (same logic as
    # _workspace_region_handler) so batch region filters using current_user
    # compare against the DSL User entity UUID, not the auth UUID (#546).
    _first_ctx = region_ctxs[0] if region_ctxs else None
    _batch_user_id, _batch_user_entity = await _resolve_workspace_user(
        request,
        _first_ctx.auth_middleware if _first_ctx else None,
        _first_ctx.repositories if _first_ctx else None,
        _first_ctx.user_entity_name if _first_ctx else "User",
    )

    # Build auth_context for _extract_condition_filters
    _batch_auth_ctx: Any = None
    if _first_ctx and _first_ctx.auth_middleware:
        try:
            _batch_auth_ctx = _first_ctx.auth_middleware.get_auth_context(request)
            if _batch_auth_ctx and _batch_user_entity:
                prefs = getattr(_batch_auth_ctx, "preferences", None)
                if prefs is None:
                    _batch_auth_ctx.preferences = {}
                    prefs = _batch_auth_ctx.preferences
                from uuid import UUID as _UUID

                for k, v in _batch_user_entity.items():
                    if k not in prefs and v is not None:
                        prefs[k] = str(v) if isinstance(v, _UUID) else v
                if _batch_user_id and "entity_id" not in prefs:
                    prefs["entity_id"] = _batch_user_id
        except Exception:
            logger.debug("Batch: failed to get auth context", exc_info=True)

    # Legacy filter context for backward compat
    _batch_filter_ctx: dict[str, Any] = {}
    if _batch_user_id:
        _batch_filter_ctx["current_user_id"] = _batch_user_id
    if _batch_user_entity:
        _batch_filter_ctx["current_user_entity"] = _batch_user_entity

    results = await asyncio.gather(
        *(
            _fetch_region_json(
                request,
                page,
                page_size,
                ctx,
                filter_context=_batch_filter_ctx,
                auth_context=_batch_auth_ctx,
                user_id=_batch_user_id,
            )
            for ctx in region_ctxs
        ),
        return_exceptions=True,
    )

    regions: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, dict):
            regions.append(result)
        elif isinstance(result, BaseException):
            logger.warning("Batch region query failed: %s", result)

    return {"regions": regions}


async def _workspace_stats_handler(
    request: Any,
    region_ctxs: list[WorkspaceRegionContext],
) -> dict[str, Any]:
    """Compute workspace aggregate metrics as standalone JSON (closes #783).

    Returns ``{"workspace": name, "stats": {region_name: {metric: value}}}``.
    Only regions with a non-empty ``aggregates`` mapping contribute.
    Items-based aggregates (``count`` alone or ``sum:field``) resolve to 0 —
    callers needing those values should invoke the region endpoint directly.
    """
    from fastapi import HTTPException

    # Enforce auth (same shape as batch handler: any region that requires it).
    for ctx in region_ctxs:
        if ctx.require_auth:
            auth_ctx = None
            if ctx.auth_middleware:
                try:
                    auth_ctx = ctx.auth_middleware.get_auth_context(request)
                except Exception:
                    logger.warning("Failed to get auth context for stats request", exc_info=True)
            if not (auth_ctx and auth_ctx.is_authenticated):
                raise HTTPException(status_code=401, detail="Authentication required")
            if ctx.ws_access and ctx.ws_access.allow_personas and auth_ctx:
                is_super = auth_ctx.user and auth_ctx.user.is_superuser
                normalized_roles = [r.removeprefix("role_") for r in auth_ctx.roles]
                if not is_super and not any(
                    r in ctx.ws_access.allow_personas for r in normalized_roles
                ):
                    raise HTTPException(status_code=403, detail="Workspace access denied")
            break

    workspace_name = ""
    if region_ctxs:
        endpoint = region_ctxs[0].ctx_region.endpoint or ""
        if "/api/workspaces/" in endpoint:
            workspace_name = endpoint.split("/api/workspaces/")[1].split("/")[0]

    stats: dict[str, dict[str, Any]] = {}
    seen_regions: set[str] = set()
    for ctx in region_ctxs:
        aggregates = ctx.ctx_region.aggregates
        if not aggregates:
            continue
        region_name = ctx.ctx_region.name
        if region_name in seen_regions:
            continue
        seen_regions.add(region_name)

        metrics = await _compute_aggregate_metrics(
            aggregates,
            ctx.repositories,
            total=0,
            items=[],
            source_entity=ctx.source,  # #888 Phase 1
        )
        stats[region_name] = {m["label"]: m["value"] for m in metrics}

    return {"workspace": workspace_name, "stats": stats}
