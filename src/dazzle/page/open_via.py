"""#1603 — resolve list-row drill URL when ``open: Entity via field`` is set.

Pure helper used by SSR list compile and HTMX meta so both paths share one
formula. Default (no open_via) remains same-entity detail ``.../{id}``.

#1600 P2: polymorphic / first-non-null chains produce an ordered list of
candidate templates; row resolve tries each until a non-null FK formats.
"""

from __future__ import annotations

from typing import Any

from dazzle.page import app_paths


def resolve_list_same_entity_detail_template(
    entity: Any,
    surface: Any = None,
    *,
    app_prefix: str = "/app",
) -> str:
    """Same-entity detail template ``/app/<list-entity>/{id}`` (#1614 fallback)."""
    list_entity_name = getattr(entity, "name", None) or getattr(surface, "entity_ref", None) or ""
    slug = app_paths.entity_slug(str(list_entity_name))
    return app_paths.detail_path(app_prefix, slug, id="{id}")


def _field_ref_entity(entity: Any, field_name: str) -> str | None:
    """Return the ref target entity for ``field_name`` on ``entity``, if any."""
    if entity is None or not field_name:
        return None
    fld = None
    try:
        fld = entity.get_field(field_name)
    except Exception:
        fld = None
    if fld is None:
        for f in getattr(entity, "fields", None) or []:
            if getattr(f, "name", None) == field_name:
                fld = f
                break
    if fld is not None and getattr(fld, "type", None) is not None:
        return getattr(fld.type, "ref_entity", None)
    return None


def _normalize_open_targets(surface: Any) -> list[tuple[str | None, str]]:
    """Return ``(entity_or_None, via_field)`` pairs from surface IR.

    Prefer ``open_via_targets``; fall back to legacy ``open_via`` / ``open_entity``.
    """
    raw = list(getattr(surface, "open_via_targets", None) or []) if surface is not None else []
    if raw:
        out: list[tuple[str | None, str]] = []
        for t in raw:
            via = getattr(t, "via", None) or (t.get("via") if isinstance(t, dict) else None)
            ent = getattr(t, "entity", None)
            if ent is None and isinstance(t, dict):
                ent = t.get("entity")
            if via:
                out.append((ent, str(via)))
        return out
    open_via = getattr(surface, "open_via", None) if surface is not None else None
    if not open_via:
        return []
    open_entity = getattr(surface, "open_entity", None) if surface is not None else None
    return [(open_entity, str(open_via))]


def resolve_list_detail_url_candidates(
    surface: Any,
    entity: Any,
    *,
    app_prefix: str = "/app",
) -> list[str]:
    """Ordered open-via hop templates (first non-null FK wins at row time).

    Single ``open: Company via company`` → one template.
    Multi / first_non_null → one template per hop.
    No open-via → empty list (caller uses same-entity template as primary).
    """
    targets = _normalize_open_targets(surface)
    if not targets:
        return []

    list_entity_name = getattr(entity, "name", None) or getattr(surface, "entity_ref", "") or ""
    templates: list[str] = []
    for open_entity, open_via in targets:
        target_name = open_entity
        if not target_name:
            target_name = _field_ref_entity(entity, open_via)
        if not target_name:
            target_name = list_entity_name
        slug = app_paths.entity_slug(str(target_name))
        templates.append(app_paths.detail_path(app_prefix, slug, id="{" + str(open_via) + "}"))
    return templates


def resolve_list_detail_url_template(
    surface: Any,
    entity: Any,
    *,
    app_prefix: str = "/app",
) -> str:
    """Return the primary ``str.format`` template for row drill-down.

    With ``open: Company via company`` → ``/app/company/{company}``.
    With multi-hop → first candidate (remaining live in
    :func:`resolve_list_detail_url_candidates`).
    Without open_via → ``/app/<list-entity-slug>/{id}``.

    When open-via is set, pair with
    :func:`resolve_list_same_entity_detail_template` as the per-row fallback
    for null FKs (#1614).
    """
    candidates = resolve_list_detail_url_candidates(surface, entity, app_prefix=app_prefix)
    if candidates:
        return candidates[0]
    return resolve_list_same_entity_detail_template(entity, surface, app_prefix=app_prefix)
