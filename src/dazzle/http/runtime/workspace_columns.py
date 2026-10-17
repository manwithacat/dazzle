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
- ``build_region_columns(entity_spec, column_specs)`` — a region's authored
  ``columns:`` (#1792). Both this and ``build_surface_columns`` resolve through
  ``build_projected_columns``, which carries the ``width`` / ``truncate`` hints.
- ``build_entity_columns(entity_spec, *, media_thumbs=False)`` — fallback
  column derivation from the entity's full field list when a surface doesn't
  pin its own projection. Applies the 2d field-economy default-flip (#1491):
  keeps the top-6 most salient columns (``resolve_column_economy``) and
  sheds the low-signal tail, which the default row drill/peek recovers.
  Image/file fields are auto-derived only for card-like displays
  (``media_thumbs=True`` — see ``CARD_LIKE_DISPLAYS``, #1792 U5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dazzle.core.ir.money import is_money_field_name
from dazzle.core.ir.workspaces import DisplayMode
from dazzle.page.app_paths import detail_path, entity_slug
from dazzle.page.runtime.column_economy_resolver import resolve_column_economy
from dazzle.render.channel_cell import email_field_name, phone_field_name
from dazzle.render.filters import clerk_percent_points_field, clerk_stage_label, status_tone_map
from dazzle.render.iban_cell import iban_field_name
from dazzle.render.rating_cell import rating_field_name
from dazzle.render.tags_cell import tags_field_name
from dazzle.render.temperature_cell import temperature_field_name


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


def enum_filter_options(values: Any) -> list[tuple[str, str]]:
    """Workspace enum FilterBar: query tokens ride, labels clerk-humanized.

    List surfaces already title-case via ``_infer_filter_type``. Workspace
    dumped ``in_progress`` as the option text. Leftover junk stays put
    (oral #147).
    """
    out: list[tuple[str, str]] = []
    for raw in values or ():
        if isinstance(raw, dict):
            token = str(raw.get("value") or "")
            given = str(raw.get("label") or "")
        elif isinstance(raw, (tuple, list)) and len(raw) >= 2:
            token = str(raw[0])
            given = str(raw[1])
        else:
            token = str(raw)
            given = ""
        if not token:
            continue
        label = given if given and given != token else clerk_stage_label(token)
        out.append((token, label))
    return out


def ref_detail_route(ref_entity: Any) -> str:
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
    "file": "file",
    "email": "email",
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


def _name_heuristic_col_type(name: str) -> str | None:
    """Column type from field name when the IR kind is unmapped."""
    if name.endswith("_minor"):
        return "currency"
    if name.endswith("_bytes") or name in {"size", "filesize", "byte_size"}:
        return "bytes"
    if clerk_percent_points_field(name):
        return "percentage"
    if tags_field_name(name):
        return "tags"
    if rating_field_name(name):
        return "rating"
    if temperature_field_name(name):
        return "temperature"
    if phone_field_name(name):
        return "phone"
    if email_field_name(name):
        return "email"
    if iban_field_name(name):
        return "iban"
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
    # INT cents (acme Invoice.amount) — not decimal majors (oral #175).
    if str(kind_val or "").strip().lower() in {"int", "integer"} and is_money_field_name(name):
        return "currency"
    named = _name_heuristic_col_type(name)
    if named is not None:
        return named
    # State-machine status field renders as badge
    if entity is not None:
        sm = entity.state_machine
        if sm and sm.status_field == field.name:
            return "badge"
    # URL-typed media keys → image thumbs; palette names → color swatches
    # (entity-fallback desks otherwise showed raw hex / bare URLs).
    media = _media_col_type_for_field_name(name)
    if media is not None:
        return media
    return "text"


@dataclass(frozen=True)
class ProjectedField:
    """One author-named list column, before it is resolved against the entity (#1792).

    Both projections feed :func:`build_projected_columns`: a list surface's
    ``field`` lines (:func:`build_surface_columns`) and a region's
    ``columns:`` (:func:`build_region_columns`). ``width`` / ``truncate`` are the
    shared :class:`dazzle.core.ir.ColumnSpec` hints.
    """

    name: str
    label: str | None = None
    visible_condition: dict[str, Any] | None = None
    format: Any = None
    widget: str = ""
    width: str | None = None
    truncate: bool | None = None


def build_surface_columns(entity_spec: Any, surface_spec: Any) -> list[dict[str, Any]]:
    """Build column metadata from a list surface's field projection.

    Uses the surface's section elements to determine which entity fields to
    show and in what order, rather than dumping all entity fields.
    """
    if not entity_spec or not hasattr(entity_spec, "fields"):
        return []

    # Collect field names from surface sections (preserving order). Carry the
    # element-level (or fallback section-level) visible: predicate so the
    # request handler can hide columns the persona shouldn't see (#872).
    # #1470 Phase 2: per-field explicit format: override (None when unannotated).
    # oral #132: author ``field photo_url "Photo"`` must win over schema titles.
    # #1626 R5 / P0-8: surface ``widget=color`` → list/queue type ``color`` (swatch).
    entries: list[ProjectedField] = []
    seen: set[str] = set()
    for section in surface_spec.sections:
        _sec_vis = getattr(section, "visible", None)
        _section_vis_cond = _sec_vis.model_dump() if _sec_vis is not None else None
        for element in section.elements:
            fn = element.field_name
            if not fn or fn == "id" or fn in seen:
                continue
            seen.add(fn)
            _el_vis = getattr(element, "visible", None)
            opts = getattr(element, "options", None) or {}
            entries.append(
                ProjectedField(
                    name=fn,
                    label=getattr(element, "label", None),
                    visible_condition=_el_vis.model_dump() if _el_vis else _section_vis_cond,
                    format=getattr(element, "format", None),
                    widget=str(opts["widget"])
                    if isinstance(opts, dict) and opts.get("widget")
                    else "",
                    width=getattr(element, "width", None),
                    truncate=getattr(element, "truncate", None),
                )
            )

    if not entries:
        return build_entity_columns(entity_spec)
    return build_projected_columns(entity_spec, entries)


def build_region_columns(
    entity_spec: Any, column_specs: Any, label_surface: Any = None
) -> list[dict[str, Any]]:
    """Column metadata for a region's authored ``columns:`` (#1792).

    Order is authoritative and only the named fields render — naming an
    image/file field shows it on any display (the U5 media opt-in). Labels come
    from ``label_surface`` (the entity's list surface) when it labels the field,
    else the title-cased field name.
    """
    if not entity_spec or not hasattr(entity_spec, "fields"):
        return []
    labels: dict[str, str | None] = {}
    if label_surface is not None:
        for section in getattr(label_surface, "sections", None) or []:
            for element in section.elements:
                labels.setdefault(element.field_name, getattr(element, "label", None))
    entries = [
        ProjectedField(
            name=spec.field,
            label=labels.get(spec.field),
            width=spec.width,
            truncate=spec.truncate,
        )
        for spec in column_specs
    ]
    return build_projected_columns(entity_spec, entries)


def _apply_entry_meta(col: dict[str, Any], entry: ProjectedField) -> None:
    """Author metadata every projected column carries: visibility, format, ColumnSpec hints."""
    if entry.visible_condition:
        col["visible_condition"] = entry.visible_condition
    if entry.format is not None:
        col["format_kind"] = entry.format.kind
        col["format_arg"] = entry.format.arg or ""
    if entry.width is not None:
        col["width"] = entry.width
    if entry.truncate is not None:
        col["truncate"] = entry.truncate


def _projected_col_type(f: Any, kind_val: str, entity_spec: Any, entry: ProjectedField) -> str:
    """Column type for a projected scalar field (widget / money overrides win)."""
    if kind_val == "money":
        return "currency"
    # #1626 R5: color picker fields must not render as raw hex text on desks.
    if entry.widget in ("color", "tags"):
        return entry.widget
    return field_kind_to_col_type(f, entity_spec)


def _projected_column(
    field_map: dict[str, Any], entity_spec: Any, entry: ProjectedField
) -> dict[str, Any] | None:
    """One author-named field as a column dict, or None when it can't render."""
    fn = entry.name
    f, kind_val = _resolve_surface_field(field_map, fn)
    if f is None or kind_val in ("uuid", "has_many", "has_one", "embeds"):
        return None
    ft = f.type
    if kind_val in ("ref", "belongs_to"):
        # ref_entity / filter_ref_entity: Avatar default (user_chip) + hyperpart
        # opportunity scan need the target entity, not just ref_route.
        col = _ref_entity_column(f, ft)
        col["label"] = _column_label(col["key"], entry.label)
        _apply_entry_meta(col, entry)
        return col
    col_type = _projected_col_type(f, kind_val, entity_spec, entry)
    col = {
        "key": f"{fn}_minor" if kind_val == "money" else f.name,
        "label": _column_label(fn, entry.label),
        "type": col_type,
        "sortable": True,
    }
    _apply_entry_meta(col, entry)
    if kind_val == "money":
        col["currency_code"] = _money_currency_code(field_map, fn, f)
    elif col_type == "currency":
        col["currency_code"] = "GBP"
    if col_type == "badge":
        # #1493 slice 2: declared `semantic:` binding + SM-terminal inference.
        _apply_badge_column_meta(col, ft, kind_val, entity_spec)
    if col_type == "bool":
        col["filterable"] = True
        col["filter_options"] = bool_filter_options()
    return col


def build_projected_columns(
    entity_spec: Any, entries: list[ProjectedField]
) -> list[dict[str, Any]]:
    """Resolve author-named fields to column dicts, in the author's order.

    The one path both list-surface field lines and region ``columns:`` take
    (#1792), so a column renders the same whichever DSL named it.
    """
    field_map: dict[str, Any] = {f.name: f for f in entity_spec.fields}
    columns: list[dict[str, Any]] = []
    for entry in entries:
        col = _projected_column(field_map, entity_spec, entry)
        if col is not None:
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
    ref_route = ref_detail_route(ref_entity)
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
    entity_spec: Any,
) -> None:
    """#1493 slice 2: semantic map + filter options for badge columns."""
    _sem = status_tone_map(ft, entity_spec.state_machine)
    if _sem:
        col["semantic_map"] = _sem
    if kind_val == "enum":
        ev = getattr(ft, "enum_values", None)
        if ev:
            col["filterable"] = True
            col["filter_options"] = enum_filter_options(ev)
        return
    sm = entity_spec.state_machine
    if not sm:
        return
    states = sm.states
    if states:
        col["filterable"] = True
        col["filter_options"] = enum_filter_options(states)


def _field_to_entity_column(f: Any, entity_spec: Any) -> dict[str, Any] | None:
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
    elif col_type == "currency":
        col["currency_code"] = "GBP"
    if col_type == "badge":
        _apply_badge_column_meta(col, ft, kind_val, entity_spec)
    if col_type == "bool":
        col["filterable"] = True
        col["filter_options"] = bool_filter_options()
    if col_type == "file":
        col["entity_name"] = str(getattr(entity_spec, "name", "") or "")
    return col


# #1792 U5: region display modes whose rows render as cards — `grid`
# (`GridCell` per row, image thumbs lead the card) and `kanban` (`KanbanCard`
# per item). Only these get image/file fields auto-derived into their columns;
# a `list` / `queue` / `status_list` / `timeline` / table row shows a media or
# file field only when the author names it (list-surface field projection or
# `fitness.repr_fields`).
CARD_LIKE_DISPLAYS: frozenset[str] = frozenset({DisplayMode.GRID.value, DisplayMode.KANBAN.value})

# Column types that are media/attachment chrome rather than scannable row data.
_MEDIA_COL_TYPES = frozenset({"image", "file"})


def media_thumbs_for_display(display: Any) -> bool:
    """True when a region ``display`` renders card rows (#1792 U5).

    Accepts a ``DisplayMode`` member, its string value, or ``None`` (an
    entity table / unset display → ``False``).
    """
    if display is None:
        return False
    value = getattr(display, "value", display)
    return str(value).lower() in CARD_LIKE_DISPLAYS


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


def build_entity_columns_full(
    entity_spec: Any, *, media_thumbs: bool = False
) -> list[dict[str, Any]]:
    """Pre-compute the **full** (untruncated) auto-derived column list from an entity.

    Same one-time IR-derived computation as ``build_entity_columns`` but WITHOUT the
    2d column-economy truncation — every eligible field becomes a column, in
    declaration order. The caller applies economy: ``build_entity_columns`` truncates
    by declared salience (the build-time default), while the request-time path
    (ADR-0050 2d) applies ``resolve_column_economy_by_usage`` so a heavily-engaged
    field can survive.

    When the entity declares ``fitness.repr_fields``, that list is the authoritative
    projection (order preserved) so workspace grid/queue cards do not dump raw
    admin schema (email / is_active / photo_url labels) — cycle 1925 agency_lead.

    ``media_thumbs`` (#1792 U5) is True only for card-like displays
    (``CARD_LIKE_DISPLAYS``): there, image fields omitted from repr are injected
    first so Goal B media cards lead with pixels. Otherwise nothing is
    injected, and the no-repr derivation drops image/file columns — a table or
    list row shows them only when the author names them (repr or a list
    surface's field projection).
    """
    columns: list[dict[str, Any]] = []
    if not entity_spec or not hasattr(entity_spec, "fields"):
        return columns

    field_map: dict[str, Any] = {f.name: f for f in entity_spec.fields}
    preferred = _fitness_repr_field_names(entity_spec)

    if preferred:
        seen: set[str] = set()
        # Media thumbs first when present so grid cards lead with pixels.
        for f in entity_spec.fields if media_thumbs else ():
            if f.name in preferred:
                continue
            media = _media_col_type_for_field_name(f.name)
            if media != "image":
                continue
            col = _field_to_entity_column(f, entity_spec)
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
            col = _field_to_entity_column(f, entity_spec)
            if col is None:
                continue
            key = str(col.get("key") or "")
            if key and key not in seen:
                columns.append(col)
                seen.add(key)
        return columns

    for f in entity_spec.fields:
        col = _field_to_entity_column(f, entity_spec)
        if col is None:
            continue
        if not media_thumbs and col.get("type") in _MEDIA_COL_TYPES:
            continue
        columns.append(col)
    return columns


def build_entity_columns(entity_spec: Any, *, media_thumbs: bool = False) -> list[dict[str, Any]]:
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
    full = build_entity_columns_full(entity_spec, media_thumbs=media_thumbs)
    if _fitness_repr_field_names(entity_spec):
        return full
    return resolve_column_economy(full)
