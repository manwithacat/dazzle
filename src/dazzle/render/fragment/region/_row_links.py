"""Per-row drill-down URL resolution (shared list/region helper).

Relocated from ``back.runtime.renderers.fragment_adapter`` into ``render`` by
ADR-0038 so the standalone list path (``back``) and the workspace region path
(``render.fragment.region``) share one pure substitution contract without
``render`` importing ``back``. Pure: stdlib + ``str.format`` only.
"""

from typing import Any
from uuid import UUID


def _format_link_value(value: Any) -> str:
    """Coerce a row field value to a URL path segment (#1603 dogfood).

    List payloads often hydrate refs as nested records
    (``{"id": UUID(...), "name": "..."}``) or UUID objects. ``format_map``
    would otherwise stringify the whole dict into the path. Prefer the
    scalar id when present.
    """
    if value is None:
        raise KeyError("null")
    if isinstance(value, UUID):
        return str(value)
    # Mapping / dict-shaped ref (hydrated FK)
    if isinstance(value, dict):
        inner = value.get("id")
        if inner is None:
            raise KeyError("dict without id")
        return _format_link_value(inner)
    # ORM / simple namespace object with .id
    if not isinstance(value, (str, bytes, int, float, bool)) and hasattr(value, "id"):
        inner = getattr(value, "id", None)
        if inner is not None:
            return _format_link_value(inner)
    return str(value)


def _item_format_map(item: dict[str, Any]) -> dict[str, str]:
    """Build a format mapping for one row (skip null / unwrappable values)."""

    class _NullMap(dict[str, str]):
        def __missing__(self, key: str) -> str:
            raise KeyError(key)

    mapping = _NullMap()
    for k, v in item.items():
        if v is None:
            continue
        try:
            mapping[k] = _format_link_value(v)
        except KeyError:
            continue
    return mapping


def _resolve_row_links(
    items: list[dict[str, Any]],
    detail_url_template: str,
    *,
    fallback_template: str = "",
    candidate_templates: tuple[str, ...] | list[str] = (),
) -> tuple[str | None, ...]:
    """Issue #1029 phase 1: per-row drill-down URL resolution.

    `detail_url_template` is a Python format string carrying named
    placeholders (typically `{id}`, but DSL authors may use `{slug}`,
    `{code}`, etc. — and #1603 `open: Entity via field` uses `{fk_field}`).
    For each item, substitute `{key}` with a URL-safe scalar from
    `item[key]` (unwrapping hydrated ref dicts / UUIDs) and emit the
    resolved URL.

    #1600 P2: ``candidate_templates`` is an ordered first-non-null open-via
    chain (polymorphic client FKs). When non-empty, try each hop before the
    primary template is used alone.

    #1614: when no candidate resolves (null open-via FKs), try
    ``fallback_template`` (typically same-entity ``.../{id}``) so the
    row keeps a drill + ``hx-trigger=click`` — which also shields action
    buttons from inheriting tbody ``load`` (#1613).

    Empty templates → empty tuple.
    """
    templates: list[str] = [t for t in (candidate_templates or ()) if t]
    if not templates and detail_url_template:
        templates = [detail_url_template]
    if not templates:
        return ()
    out: list[str | None] = []
    for item in items:
        mapping = _item_format_map(item)
        url: str | None = None
        for tmpl in templates:
            try:
                # #1603: skip hop when a placeholder is missing or null
                url = tmpl.format_map(mapping)
                break
            except (KeyError, IndexError, ValueError):
                continue
        if not url and fallback_template:
            try:
                url = fallback_template.format_map(mapping)
            except (KeyError, IndexError, ValueError):
                url = None
        out.append(url or None)
    return tuple(out)


def _try_format_url(tmpl: str, mapping: dict[str, str]) -> str | None:
    """Format one template; None when a placeholder is missing/null."""
    try:
        url = tmpl.format_map(mapping)
    except (KeyError, IndexError, ValueError):
        return None
    return url or None


def entity_label_from_detail_url(url: str) -> str:
    """Human label for a resolved detail path (cycle 1571 dual-open labels).

    ``/app/user/u-9`` → ``User``; ``/app/payment-attempt/x`` → ``Payment attempt``.
    Used for secondary/context hop ``title`` / ``aria-label`` / ``data-dz-open-entity``.
    """
    if not url:
        return "Related"
    path = str(url).split("?", 1)[0].strip("/")
    segs = [s for s in path.split("/") if s]
    if len(segs) < 2:
        return "Related"
    # /app/<slug>/<id> → slug at -2; bare /<slug>/<id> same
    slug = segs[-2]
    words = [w for w in slug.replace("_", "-").split("-") if w]
    if not words:
        return "Related"
    return " ".join(w[:1].upper() + w[1:] for w in words)


def via_field_from_template(tmpl: str) -> str:
    """Extract the open-via placeholder from a detail URL template.

    ``/app/user/{assigned_to}`` → ``assigned_to``; ``/app/task/{id}`` → ``id``.
    Empty when the template has no named placeholder (cycle 1577).
    """
    if not tmpl or "{" not in tmpl:
        return ""
    start = tmpl.find("{")
    end = tmpl.find("}", start + 1)
    if start < 0 or end < 0:
        return ""
    return tmpl[start + 1 : end].strip()


def field_label_from_via(via: str) -> str:
    """Humanize an open-via field name: ``assigned_to`` → ``Assigned to``."""
    if not via:
        return ""
    words = [w for w in str(via).replace("-", "_").split("_") if w]
    if not words:
        return ""
    # Sentence case: first word capital, rest lower (relation phrases).
    head, *rest = words
    return " ".join([head[:1].upper() + head[1:].lower(), *[w.lower() for w in rest]])


def open_hop_label(entity_label: str, via_field: str = "") -> str:
    """User-facing hop phrase for dual-open actions (cycle 1577).

    Same-entity ``via id`` stays ``Open Task``; FK hops become
    ``Open User via assigned to`` so agents/users see the relation, not only
    the target entity slug from the URL.
    """
    ent = (entity_label or "Related").strip() or "Related"
    via = (via_field or "").strip()
    if not via or via == "id":
        return f"Open {ent}"
    words = [w for w in via.replace("-", "_").split("_") if w]
    if not words:
        return f"Open {ent}"
    field_phrase = " ".join(w.lower() for w in words)
    # Avoid "Open User via user" when via name matches entity
    if field_phrase.casefold() == ent.casefold():
        return f"Open {ent}"
    return f"Open {ent} via {field_phrase}"


def _resolve_row_open_chain(
    item: dict[str, Any],
    *,
    candidate_templates: tuple[str, ...] | list[str] = (),
    detail_url_template: str = "",
    fallback_template: str = "",
) -> tuple[tuple[str, str], ...]:
    """All resolvable open-via hops for one row (ordered, deduped).

    Returns ``(url, via_field)`` pairs. First-non-null drill still uses
    :func:`_resolve_row_links` (primary only). Dual-open product digs
    (``Task via id | User via assigned_to``) need the **second** hop as a
    separate affordance — otherwise the secondary target is dead when the
    primary ``{id}`` always resolves. Cycle 1566 framework-ux: emit every
    successful candidate so the row can show a context hop. Cycle 1577:
    retain the template placeholder so hop labels can name the relation.
    """
    templates: list[str] = [t for t in (candidate_templates or ()) if t]
    if not templates and detail_url_template:
        templates = [detail_url_template]
    if not templates and not fallback_template:
        return ()

    mapping = _item_format_map(item)
    hops: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tmpl in templates:
        url = _try_format_url(tmpl, mapping)
        if url is not None and url not in seen:
            seen.add(url)
            hops.append((url, via_field_from_template(tmpl)))
    if not hops and fallback_template:
        url = _try_format_url(fallback_template, mapping)
        if url is not None:
            hops.append((url, via_field_from_template(fallback_template) or "id"))
    return tuple(hops)
