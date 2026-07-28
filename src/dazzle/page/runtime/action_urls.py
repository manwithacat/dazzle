"""Action / confirm CTA URL resolution (#891, #979, cycles 1401–1402).

Leaf helpers for ``action_grid`` and ``confirm_action_panel`` — kept out of
``workspace_renderer`` so the layout builder stays MI-rank A.
"""

from __future__ import annotations

from typing import Any

from dazzle.page import app_paths


def _mode_str(mode: Any) -> str:
    """Normalise SurfaceMode / str / None to a lowercase mode token."""
    return str(getattr(mode, "value", mode) or "").lower()


def _split_action_query(action: str) -> tuple[str, str]:
    """Split ``name?query`` so surface lookup ignores the query suffix."""
    if "?" not in action:
        return action, ""
    name, query = action.split("?", 1)
    return name, query


def surface_entity_path(entity_ref: str, mode: Any) -> str:
    """Map a surface's entity + mode for dashboard CTAs without a row id.

    CREATE → ``/app/{slug}/create`` so action_grid ``action: system_create``
    lands on the create form (and the cycle-1397 CREATE RBAC gate can see
    the ``/create`` suffix). LIST / VIEW / EDIT / CUSTOM / unknown → list
    path: dashboard CTAs lack a row id, so edit/detail templates are not
    usable as card hrefs.
    """
    slug = app_paths.entity_slug(entity_ref)
    if _mode_str(mode) == "create":
        return app_paths.create_path("/app", slug)
    return app_paths.list_path("/app", slug)


def surface_entity_path_for_row(entity_ref: str, mode: Any) -> str:
    """Map a surface's entity + mode when a single row id is available later.

    Used by confirm_action_panel (cycle 1402): the panel binds to a source
    row, so EDIT/VIEW keep the ``{id}`` template segment and request-time
    fills the concrete id. CREATE still uses create_path; LIST / CUSTOM /
    unknown stay on the list path.
    """
    slug = app_paths.entity_slug(entity_ref)
    m = _mode_str(mode)
    if m == "create":
        return app_paths.create_path("/app", slug)
    if m == "edit":
        return app_paths.edit_path("/app", slug)
    if m == "view":
        return app_paths.detail_path("/app", slug)
    return app_paths.list_path("/app", slug)


def action_to_url(action: str, app_spec: Any | None = None) -> str:
    """Resolve an ``action_grid`` card target to a URL (#891, #979).

    Three forms accepted, in priority order:

      1. **Literal URL** prefixed with `/` — used as-is.
      2. **Surface name** in ``app_spec.surfaces`` → entity slug path
         (CREATE → create_path; other modes → list for dashboard CTAs).
      3. **Bare slugified fallback** when no matching surface/entity.

    Empty input returns empty string (informational card, no click-through).
    """
    if not action:
        return ""
    if action.startswith("/"):
        return action

    name, query = _split_action_query(action)

    if app_spec is not None:
        surfaces = getattr(app_spec, "surfaces", None) or []
        for s in surfaces:
            if getattr(s, "name", None) == name:
                entity_ref = getattr(s, "entity_ref", None) or ""
                if entity_ref:
                    base = surface_entity_path(entity_ref, getattr(s, "mode", None))
                    return f"{base}?{query}" if query else base
                break

    base = app_paths.list_path("/app", app_paths.entity_slug(name))
    return f"{base}?{query}" if query else base


def confirm_action_to_url(
    action: str,
    app_spec: Any | None = None,
    *,
    source_entity: str = "",
) -> str:
    """Resolve confirm_action_panel primary/secondary/revoke to a URL.

    Same three forms as :func:`action_to_url`, but:

    * EDIT/VIEW surfaces keep ``{id}`` path templates (the panel has a
      source row; request-time fills the id — cycle 1402).
    * When the action string is not a known surface **and**
      ``source_entity`` is set, fall back to that entity's edit path
      with ``{id}`` rather than inventing a dead ``/app/<action-slug>``
      route (ops_dashboard ``integration_enable`` had no surface and
      404'd after the consent checklist).
    """
    if not action:
        return ""
    if action.startswith("/"):
        return action

    name, query = _split_action_query(action)

    if app_spec is not None:
        surfaces = getattr(app_spec, "surfaces", None) or []
        for s in surfaces:
            if getattr(s, "name", None) == name:
                entity_ref = getattr(s, "entity_ref", None) or ""
                if entity_ref:
                    base = surface_entity_path_for_row(entity_ref, getattr(s, "mode", None))
                    return f"{base}?{query}" if query else base
                break

    if source_entity:
        base = app_paths.edit_path("/app", app_paths.entity_slug(source_entity))
        return f"{base}?{query}" if query else base

    base = app_paths.list_path("/app", app_paths.entity_slug(name))
    return f"{base}?{query}" if query else base


def fill_row_id_in_url(url: str, item_id: str) -> str:
    """Replace ``{id}`` in a path/query URL, or clear when id is missing.

    Confirm-panel mutation chrome is stamped with ``{id}`` at compile
    time; request-time has the fetched row. Without a concrete id the
    template segment would 404 — return empty so the CTA is omitted.
    """
    if not url or "{id}" not in url:
        return url
    rid = str(item_id or "").strip()
    if not rid:
        return ""
    return url.replace("{id}", rid)


def region_row_drill_url(
    action: str,
    app_spec: Any | None = None,
    *,
    source_entity: str = "",
) -> str:
    """Resolve workspace region ``action:`` to a row-drill URL template.

    Fleet authors write ``action: task_edit`` / ``action: system_edit`` so
    list rows open the edit form. Pre-cycle-1403 the substrate always
    drilled to VIEW detail (``_entity_detail_url_map``) and
    ``RegionContext.action_url`` ignored surface mode — so EDIT surfaces
    navigated to detail.

    Priority:

      1. Workspace name → ``/app/workspaces/{name}?context_id={id}``
      2. Surface name → mode-aware path via :func:`surface_entity_path_for_row`
         (EDIT/VIEW keep ``{id}``; CREATE → create; LIST → list)
      3. Empty when unresolved (caller falls back to source-entity detail)

    ``source_entity`` is reserved for future cross-entity FK templates;
    same-entity EDIT/VIEW use the surface's entity_ref.
    """
    del source_entity  # reserved; same-entity templates use surface entity_ref
    if not action or not app_spec:
        return ""

    workspaces = getattr(app_spec, "workspaces", None) or []
    for ws in workspaces:
        if getattr(ws, "name", None) == action:
            return f"/app/workspaces/{action}?context_id={{id}}"

    surfaces = getattr(app_spec, "surfaces", None) or []
    for s in surfaces:
        if getattr(s, "name", None) == action:
            entity_ref = getattr(s, "entity_ref", None) or ""
            if entity_ref:
                return surface_entity_path_for_row(entity_ref, getattr(s, "mode", None))
            break
    return ""


# Private aliases kept for call-sites / tests that used the old names.
_surface_entity_path = surface_entity_path
_action_to_url = action_to_url
_confirm_action_to_url = confirm_action_to_url
_region_row_drill_url = region_row_drill_url
