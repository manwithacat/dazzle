"""#1603 — resolve list-row drill URL when ``open: Entity via field`` is set.

Pure helper used by SSR list compile and HTMX meta so both paths share one
formula. Default (no open_via) remains same-entity detail ``.../{id}``.
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


def resolve_list_detail_url_template(
    surface: Any,
    entity: Any,
    *,
    app_prefix: str = "/app",
) -> str:
    """Return a ``str.format`` template for row drill-down.

    With ``open: Company via company`` → ``/app/company/{company}``.
    Without open_via → ``/app/<list-entity-slug>/{id}``.

    When open-via is set, pair with
    :func:`resolve_list_same_entity_detail_template` as the per-row fallback
    for null FKs (#1614).
    """
    open_via = getattr(surface, "open_via", None) if surface is not None else None
    open_entity = getattr(surface, "open_entity", None) if surface is not None else None
    list_entity_name = getattr(entity, "name", None) or getattr(surface, "entity_ref", "") or ""

    if not open_via:
        return resolve_list_same_entity_detail_template(entity, surface, app_prefix=app_prefix)

    # Prefer explicit open_entity; else resolve from the FK field's ref target.
    target_name = open_entity
    if not target_name and entity is not None:
        fld = None
        try:
            fld = entity.get_field(open_via)
        except Exception:
            fld = None
        if fld is None:
            for f in getattr(entity, "fields", None) or []:
                if getattr(f, "name", None) == open_via:
                    fld = f
                    break
        if fld is not None and getattr(fld, "type", None) is not None:
            target_name = getattr(fld.type, "ref_entity", None)

    if not target_name:
        # Fall back to list entity — still use the via field as the id slot so
        # authors get a predictable miss rather than wrong same-entity drill.
        target_name = list_entity_name

    slug = app_paths.entity_slug(str(target_name))
    # Placeholder is the FK field name so _resolve_row_links formats from row dict.
    return app_paths.detail_path(app_prefix, slug, id="{" + str(open_via) + "}")
