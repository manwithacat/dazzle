"""Column-metadata builders for workspace regions (#1057).

Pre-v0.67.100 these three helpers lived inline in
`workspace_rendering.py` (which clocks at 4,483 lines). Extracted as
the first cut of the per-concern decomposition — they're self-contained,
take IR specs in and return plain dicts out, and have no dependency on
the request/response cycle.

Public API:
- ``field_kind_to_col_type(field, entity)`` — map a FieldSpec to a
  column rendering type (``badge`` / ``bool`` / ``date`` / ``currency``
  / ``text``).
- ``build_surface_columns(entity_spec, surface_spec)`` — derive
  columns from a LIST surface's section elements, preserving the
  author's field order and threading per-element ``visible:``
  predicates through to the column metadata.
- ``build_entity_columns(entity_spec)`` — fallback column derivation
  from the entity's full field list when a surface doesn't pin its
  own projection. Applies the 2d field-economy default-flip (#1491):
  keeps the top-6 most salient columns (``resolve_column_economy``) and
  sheds the low-signal tail, which the default row drill/peek recovers.
"""

from __future__ import annotations

from typing import Any

from dazzle.page.app_paths import detail_path, entity_slug
from dazzle.page.runtime.column_economy_resolver import resolve_column_economy
from dazzle.render.filters import status_tone_map


def _column_label(field_name: str, surface_label: str | None = None) -> str:
    """Clerk-facing column title (oral #132).

    Surface ``field photo_url "Photo"`` must win over schema
    ``Photo Url``. Empty leftover labels stay put as the title-cased
    field name — do not invent a guessed clerk title.
    """
    text = (surface_label or "").strip()
    if text:
        return text
    return str(field_name or "").replace("_", " ").title()


# Query values stay ``true``/``false``; the FilterBar label is Yes/No
# (same as format_cell bool / list-surface filters). Leftover junk is
# not in this catalog (oral #146).
_BOOL_FILTER_OPTIONS: tuple[tuple[str, str], ...] = (("true", "Yes"), ("false", "No"))


def bool_filter_options() -> list[tuple[str, str]]:
    """Workspace bool FilterBar options: ``true``/``false`` ride, labels Yes/No."""
    return list(_BOOL_FILTER_OPTIONS)


def _ref_detail_route(ref_entity: Any) -> str:
    """UI VIEW hub template for a ref/belongs_to column (``/app/<slug>/{id}``).

    Workspace kanban/detail/grid secondary fields render these as ``<a href>``.
    Historically this used API plurals (``/projects/{id}``) which serve JSON
    (or 404/405) — not the typed entity hub. SSOT is :func:`detail_path` so
    links stay mounted with route registration (#1426).
    """
    if not ref_entity:
        return ""
    return detail_path("/app", entity_slug(str(ref_entity)))


def _enumish_token(value: Any) -> str:
    """Normalize enum/str field-type tokens to a plain lowercase-ish string."""
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _resolved_field_kind_token(field: Any) -> str:
    """Core IR kind **or** convert_entities scalar_type (kind=scalar).

    Runtime entity specs use ``kind=scalar`` + ``scalar_type=bool|date|…``;
    core IR uses ``FieldTypeKind.BOOL`` directly as ``type.kind``.
    """
    ft = getattr(field, "type", None)
    kind_val = _enumish_token(getattr(ft, "kind", None) if ft is not None else None)
    if kind_val == "scalar" and ft is not None:
        return _enumish_token(getattr(ft, "scalar_type", None))
    return kind_val


# kind / scalar_type token → list column type. date vs datetime kept distinct
# so UK date-only vs date+time humanisation is not collapsed.
_KIND_TO_COL_TYPE: dict[str, str] = {
    "enum": "badge",
    "bool": "bool",
    "date": "date",
    "datetime": "datetime",
    "money": "currency",
}


# Post-5.8 media depth: palette + image URL names render as visual chrome
# (swatches / thumbs) even on entity-fallback workspace columns.
_COLOR_FIELD_KEYS = frozenset(
    {
        "primary_color",
        "secondary_color",
        "accent_color",
        "color",
        "colour",
        "bg_color",
        "background_color",
        "text_color",
        "fill_color",
    }
)
_IMAGE_FIELD_KEYS = frozenset(
    {
        "logo_url",
        "preview_url",
        "image_url",
        "avatar_url",
        "thumbnail_url",
        "thumb_url",
        "cover_url",
        "photo_url",
    }
)


def _media_col_type_for_field_name(name: str) -> str | None:
    """Heuristic presentation type from field name (Goal B media / palette)."""
    key = (name or "").strip().lower()
    if not key:
        return None
    if key in _COLOR_FIELD_KEYS or key.endswith("_color") or key.endswith("_colour"):
        return "color"
    if key in _IMAGE_FIELD_KEYS or key.endswith("_image_url") or key.endswith("_thumb_url"):
        return "image"
    return None


def _resolve_surface_field(
    field_map: dict[str, Any], fn: str
) -> tuple[Any, str] | tuple[None, str]:
    """Resolve a LIST-surface field name against IR or runtime entity fields.

    ``convert_entities`` expands ``amount: money`` into ``amount_minor`` +
    ``amount_currency``. Surface ``field amount`` must still project the
    minor column — otherwise queue/timeline pads drop pay and title the
    ISO date (oral #136).
    """
    f = field_map.get(fn)
    if f is not None:
        return f, _resolved_field_kind_token(f)
    minor = field_map.get(f"{fn}_minor")
    if minor is not None and f"{fn}_currency" in field_map:
        return minor, "money"
    return None, ""


def _money_currency_code(field_map: dict[str, Any], fn: str, money_field: Any) -> str:
    """ISO code from the money type, else the expanded currency default."""
    ft = getattr(money_field, "type", None)
    code = getattr(ft, "currency_code", None) if ft is not None else None
    if code:
        return str(code)
    ccy = field_map.get(f"{fn}_currency")
    default = getattr(ccy, "default", None) if ccy is not None else None
    if default:
        return str(default)
    return "GBP"


def field_kind_to_col_type(field: Any, entity: Any = None) -> str:
    """Map an IR field to a column rendering type for workspace templates.

    Args:
        field: FieldSpec IR object (core IR **or** runtime entity after
            ``convert_entities``).
        entity: Optional EntitySpec — when provided, checks if this field
                is the state-machine status field and returns ``"badge"``.

    Core IR uses ``FieldTypeKind.BOOL`` / ``DATE`` / … as ``type.kind``.
    Runtime entities from ``convert_entities`` collapse scalars to
    ``kind=scalar`` + ``scalar_type=BOOL|DATE|…``. Workspace list chrome
    must resolve both shapes or bool columns render as the Python
    ``"True"``/``"False"`` strings (agent_acceptance / pilot friction).
    """
    kind_val = _resolved_field_kind_token(field)
    mapped = _KIND_TO_COL_TYPE.get(kind_val)
    if mapped is not None:
        return mapped
    name = str(getattr(field, "name", "") or "")
    if name.endswith("_minor"):
        return "currency"
    if name.endswith("_bytes") or name in {"size", "filesize", "byte_size"}:
        return "bytes"
    # State-machine status field renders as badge
    if entity is not None:
        sm = entity.state_machine
        if sm and sm.status_field == field.name:
            return "badge"
    # URL-typed media keys → image thumbs; palette names → color swatches
    # (entity-fallback desks otherwise showed raw hex / bare URLs).
    media = _media_col_type_for_field_name(str(getattr(field, "name", "") or ""))
    if media is not None:
        return media
    return "text"


def build_surface_columns(
    entity_spec: Any, surface_spec: Any, enums: Any = None
) -> list[dict[str, Any]]:
    """Build column metadata from a list surface's field projection.

    Uses the surface's section elements to determine which entity fields to
    show and in what order, rather than dumping all entity fields.

    ``enums`` (the app's shared `enum` blocks) lets a badge column carry its
    declared `semantic:` value→tone map (#1493 slice 2); pass the appspec's
    ``enums`` so shared-enum bindings resolve (inline `enum[...]` bindings
    resolve without it).
    """
    if not entity_spec or not hasattr(entity_spec, "fields"):
        return []

    # Collect field names from surface sections (preserving order). Carry the
    # element-level (or fallback section-level) visible: predicate so the
    # request handler can hide columns the persona shouldn't see (#872).
    surface_fields: list[str] = []
    field_visible_conditions: dict[str, dict[str, Any] | None] = {}
    # #1470 Phase 2: per-field explicit format: override (None when unannotated).
    field_formats: dict[str, Any] = {}
    # oral #132: author ``field photo_url "Photo"`` must win over schema titles.
    field_labels: dict[str, str | None] = {}
    # #1626 R5 / P0-8: surface ``widget=color`` → list/queue type ``color`` (swatch).
    field_widgets: dict[str, str] = {}
    for section in surface_spec.sections:
        _sec_vis = getattr(section, "visible", None)
        _section_vis_cond = _sec_vis.model_dump() if _sec_vis is not None else None
        for element in section.elements:
            fn = element.field_name
            if fn and fn != "id" and fn not in surface_fields:
                surface_fields.append(fn)
                _el_vis = getattr(element, "visible", None)
                field_visible_conditions[fn] = (
                    _el_vis.model_dump() if _el_vis else _section_vis_cond
                )
                field_formats[fn] = getattr(element, "format", None)
                field_labels[fn] = getattr(element, "label", None)
                opts = getattr(element, "options", None) or {}
                if isinstance(opts, dict) and opts.get("widget"):
                    field_widgets[fn] = str(opts["widget"])

    if not surface_fields:
        return build_entity_columns(entity_spec, enums)

    # Build a lookup from entity fields
    field_map: dict[str, Any] = {f.name: f for f in entity_spec.fields}

    columns: list[dict[str, Any]] = []
    for fn in surface_fields:
        f, kind_val = _resolve_surface_field(field_map, fn)
        if f is None:
            continue
        _vis_cond = field_visible_conditions.get(fn)
        _fmt = field_formats.get(fn)
        ft = f.type
        # Ref and belongs_to fields
        if kind_val in ("ref", "belongs_to"):
            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
            ref_entity = getattr(ft, "ref_entity", None)
            ref_route = _ref_detail_route(ref_entity)
            # ref_entity / filter_ref_entity: Avatar default (user_chip) + hyperpart
            # opportunity scan need the target entity, not just ref_route.
            ref_col: dict[str, Any] = {
                "key": rel_name,
                "label": _column_label(rel_name, field_labels.get(fn)),
                "type": "ref",
                "sortable": False,
                "ref_route": ref_route,
                "ref_entity": ref_entity or "",
                "filter_ref_entity": ref_entity or "",
            }
            if _vis_cond:
                ref_col["visible_condition"] = _vis_cond
            if _fmt is not None:
                ref_col["format_kind"] = _fmt.kind
                ref_col["format_arg"] = _fmt.arg or ""
            columns.append(ref_col)
            continue
        # Skip non-displayable types
        if kind_val in ("uuid", "has_many", "has_one", "embeds"):
            continue
        col_type = field_kind_to_col_type(f, entity_spec)
        # #1626 R5: color picker fields must not render as raw hex text on desks.
        if field_widgets.get(fn) == "color":
            col_type = "color"
        if kind_val == "money":
            col_type = "currency"
        col_key = f"{fn}_minor" if kind_val == "money" else f.name
        col: dict[str, Any] = {
            "key": col_key,
            "label": _column_label(fn, field_labels.get(fn)),
            "type": col_type,
            "sortable": True,
        }
        if _vis_cond:
            col["visible_condition"] = _vis_cond
        if _fmt is not None:
            col["format_kind"] = _fmt.kind
            col["format_arg"] = _fmt.arg or ""
        if kind_val == "money":
            col["currency_code"] = _money_currency_code(field_map, fn, f)
        if col_type == "badge":
            # #1493 slice 2: declared `semantic:` binding + SM-terminal inference.
            _sem = status_tone_map(ft, enums, entity_spec.state_machine)
            if _sem:
                col["semantic_map"] = _sem
            if kind_val == "enum":
                ev = getattr(ft, "enum_values", None)
                if ev:
                    col["filterable"] = True
                    col["filter_options"] = list(ev)
            else:
                sm = entity_spec.state_machine
                if sm:
                    states = sm.states
                    if states:
                        col["filterable"] = True
                        col["filter_options"] = list(states)
        if col_type == "bool":
            col["filterable"] = True
            col["filter_options"] = bool_filter_options()
        columns.append(col)
    return columns


def _kind_token(ft: Any) -> str:
    kind = getattr(ft, "kind", None)
    if kind is None:
        return ""
    if hasattr(kind, "value"):
        return str(kind.value)
    return str(kind)


def _ref_entity_column(f: Any, ft: Any) -> dict[str, Any]:
    """Workspace column for ref/belongs_to — resolved display name + detail route."""
    rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
    ref_entity = getattr(ft, "ref_entity", None)
    ref_route = _ref_detail_route(ref_entity)
    return {
        "key": rel_name,
        "label": _column_label(rel_name),
        "type": "ref",
        "sortable": False,
        "ref_route": ref_route,
        "ref_entity": ref_entity or "",
        "filter_ref_entity": ref_entity or "",
    }


def _apply_badge_column_meta(
    col: dict[str, Any],
    ft: Any,
    kind_val: str,
    enums: Any,
    entity_spec: Any,
) -> None:
    """#1493 slice 2: semantic map + filter options for badge columns."""
    _sem = status_tone_map(ft, enums, entity_spec.state_machine)
    if _sem:
        col["semantic_map"] = _sem
    if kind_val == "enum":
        ev = getattr(ft, "enum_values", None)
        if ev:
            col["filterable"] = True
            col["filter_options"] = list(ev)
        return
    sm = entity_spec.state_machine
    if not sm:
        return
    states = sm.states
    if states:
        col["filterable"] = True
        col["filter_options"] = list(states)


def _field_to_entity_column(f: Any, entity_spec: Any, enums: Any = None) -> dict[str, Any] | None:
    """Map one entity field to a workspace column dict, or None if non-displayable."""
    if f.name == "id":
        return None
    ft = f.type
    kind_val = _kind_token(ft)
    # Show ref/belongs_to columns with resolved display name; hide other relation types
    if kind_val in ("ref", "belongs_to"):
        return _ref_entity_column(f, ft)
    if kind_val in ("uuid", "has_many", "has_one", "embeds"):
        return None
    if f.name.endswith("_id"):
        return None
    col_type = field_kind_to_col_type(f, entity_spec)
    col_key = f"{f.name}_minor" if kind_val == "money" else f.name
    col: dict[str, Any] = {
        "key": col_key,
        "label": _column_label(f.name),
        "type": col_type,
        "sortable": True,
    }
    if kind_val == "money":
        col["currency_code"] = getattr(ft, "currency_code", None) or "GBP"
    if col_type == "badge":
        _apply_badge_column_meta(col, ft, kind_val, enums, entity_spec)
    if col_type == "bool":
        col["filterable"] = True
        col["filter_options"] = bool_filter_options()
    return col


# Displays where fitness.repr_fields should win over LIST surface projection
# (headshot shelves / card galleries — cycle 1925). Queue/list/timeline keep
# list-surface identifiers (ticket_number) — cycle 1926.
CARD_LIKE_DISPLAYS: frozenset[str] = frozenset(
    {
        "grid",
        "media",
        "gallery",
        "card",
        "cards",
        "media_shelf",
    }
)


def prefer_fitness_repr_for_display(display: str | None) -> bool:
    """True when workspace region display is card/gallery (not queue/list)."""
    return str(display or "").lower().strip() in CARD_LIKE_DISPLAYS


def _fitness_repr_field_names(entity_spec: Any) -> list[str]:
    """Author ``fitness.repr_fields`` when present — domain-essential card/list projection.

    Accepts core IR entities (``.fitness.repr_fields``) and runtime BackendSpec
    entities (metadata ``fitness_repr_fields`` after convert — cycle 1925).
    """
    raw: list[Any] = []
    fitness = getattr(entity_spec, "fitness", None)
    if fitness is not None:
        raw = list(getattr(fitness, "repr_fields", None) or [])
    if not raw:
        meta = getattr(entity_spec, "metadata", None) or {}
        if isinstance(meta, dict):
            raw = list(meta.get("fitness_repr_fields") or [])
    out: list[str] = []
    for name in raw:
        s = str(name or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def build_entity_columns_full(entity_spec: Any, enums: Any = None) -> list[dict[str, Any]]:
    """Pre-compute the **full** (untruncated) auto-derived column list from an entity.

    Same one-time IR-derived computation as ``build_entity_columns`` but WITHOUT the
    2d column-economy truncation — every eligible field becomes a column, in
    declaration order. The caller applies economy: ``build_entity_columns`` truncates
    by declared salience (the build-time default), while the request-time path
    (ADR-0050 2d) applies ``resolve_column_economy_by_usage`` so a heavily-engaged
    field can survive. ``enums`` carries the shared `enum` blocks for badge
    `semantic:` maps (#1493 slice 2).

    When the entity declares ``fitness.repr_fields``, that list is the authoritative
    projection (order preserved) so workspace grid/queue cards do not dump raw
    admin schema (email / is_active / photo_url labels) — cycle 1925 agency_lead.
    Image/media fields present on the entity but omitted from repr are still
    injected so Goal B media shelves keep thumbs without schema theater.
    """
    columns: list[dict[str, Any]] = []
    if not entity_spec or not hasattr(entity_spec, "fields"):
        return columns

    field_map: dict[str, Any] = {f.name: f for f in entity_spec.fields}
    preferred = _fitness_repr_field_names(entity_spec)

    if preferred:
        seen: set[str] = set()
        # Media thumbs first when present so grid cards lead with pixels.
        for f in entity_spec.fields:
            if f.name in preferred:
                continue
            media = _media_col_type_for_field_name(f.name)
            if media != "image":
                continue
            col = _field_to_entity_column(f, entity_spec, enums)
            if col is None:
                continue
            key = str(col.get("key") or "")
            if key and key not in seen:
                columns.append(col)
                seen.add(key)
        for name in preferred:
            f = field_map.get(name)
            if f is None:
                continue
            col = _field_to_entity_column(f, entity_spec, enums)
            if col is None:
                continue
            key = str(col.get("key") or "")
            if key and key not in seen:
                columns.append(col)
                seen.add(key)
        return columns

    for f in entity_spec.fields:
        col = _field_to_entity_column(f, entity_spec, enums)
        if col is not None:
            columns.append(col)
    return columns


def build_entity_columns(entity_spec: Any, enums: Any = None) -> list[dict[str, Any]]:
    """Auto-derived columns with the **build-time** 2d economy applied (the default).

    Keeps the top-6 most salient auto-columns (``resolve_column_economy``) and sheds
    the low-signal tail (timestamps, long text), recovered via the default row
    drill/peek. A ≤6-column entity is byte-identical. The request-time usage path
    (ADR-0050 2d → L4) instead calls ``build_entity_columns_full`` + the usage-boosted
    resolver; this remains the cold-start / no-DB default.

    When ``fitness.repr_fields`` is set, the author list is already a deliberate
    projection — **do not** re-truncate with economy (cycle 1929: economy dropped
    ``ticket_number`` from support_tickets queues → #1304 AAA-* needles zero while
    row count stayed 3).
    """
    full = build_entity_columns_full(entity_spec, enums)
    if _fitness_repr_field_names(entity_spec):
        return full
    return resolve_column_economy(full)
