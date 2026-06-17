"""Async card-data fetchers + entity-card section assembly.

Extracted from workspace_rendering.py in #1057 cut 5 (v0.67.104).
Pairs the I/O layer with the pure data shapers in
`workspace_card_data.py` and HTML builders in `workspace_card_bodies.py`:

- `_fetch_entity_card_section_rows`: fan out per-section queries for
  an entity_card region.
- `_fetch_task_inbox_items_per_source`: fan out per-source queries
  for a multi-source task_inbox.
- `_empty_list_coro` / `_safe_fetch`: shared concurrency helpers.
- `_build_entity_card_sections`: assemble the resolved section dicts
  by dispatching to the per-mode body renderers.
"""

import asyncio
import logging
from typing import Any

from dazzle.back.runtime.workspace_scope import _apply_workspace_scope_filters
from dazzle.render.fragment.region.workspace_card_bodies import (
    _dazzle_html_escape,
    _render_mini_bars_body,
    _render_quick_actions_body,
    _render_stamps_body,
    _render_thread_summary_body,
)

logger = logging.getLogger(__name__)


async def _fetch_entity_card_section_rows(
    *,
    config: Any,
    ctx: Any,
    request: Any,
    auth_context: Any,
    user_id: str | None,
    context_id: str | None = None,
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
            from dazzle.back.runtime.scope_filters import _extract_condition_filters

            with suppress(Exception):
                # #1225: thread `context_id` through so per-section
                # `filter: X = current_context` predicates resolve to
                # the scoped record id. Pre-fix this argument was None
                # → filter silently dropped → sections rendered the
                # first-scope row regardless of which entity the
                # entity_card was scoped to. AegisMark's pupil_dashboard
                # made the data-attribution-wrongness visible.
                _extract_condition_filters(
                    section_filter,
                    user_id or "",
                    merged_filters,
                    logger,
                    auth_context,
                    None,
                    context_id,
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
            from dazzle.back.runtime.scope_filters import _extract_condition_filters

            # #1232 — thread the source entity's FK→target map so dotted
            # left-side paths (`teacher.user = current_user`) resolve via
            # subquery JOINs in `_extract_condition_filters` instead of
            # falling through as an unrecognised `teacher.user` filter key.
            entity_ref_targets = getattr(ctx, "entity_ref_targets", None) or {}
            _ref_targets = entity_ref_targets.get(source_entity)
            with suppress(Exception):
                _extract_condition_filters(
                    source_filter,
                    user_id or "",
                    merged_filters,
                    logger,
                    auth_context,
                    _ref_targets,
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
    # Normalise rows to plain dicts so downstream `row.get(field)` calls
    # in `_render_mini_bars_body` / `_render_stamps_body` /
    # `_render_thread_summary_body` work regardless of whether the
    # repository returned Pydantic models (when `include=None` takes
    # the `_row_to_model` path) or dict rows. Mirrors the same
    # normalisation in `workspace_region_fetch.py` (#1215).
    if isinstance(result, dict):
        raw_items = result.get("items", []) or []
    elif isinstance(result, list):
        raw_items = result
    else:
        return []
    return [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in raw_items]


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
