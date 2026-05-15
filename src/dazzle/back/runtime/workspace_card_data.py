"""Card-data shapers: cohort cells, day timeline slots, task inbox items.

Extracted from workspace_rendering.py in #1057 cut 3 (v0.67.102).
Pure synchronous shapers — no I/O, no DB, no IR dispatch. Take
already-fetched rows + config dicts in, return shaped data
structures (lists of dicts) ready for the typed-primitive
renderers.

Contents:
- `_CARD_TEMPLATE_RE`: regex for `{{ field.path }}` interpolation.
- `_resolve_path`: walk a dotted path against an item dict.
- `_initials_from`: 1–2 character initials from a name string.
- `_build_cohort_cells`: cohort_strip cell list.
- `_build_day_timeline_slots`: day_timeline slot list with overlap layout.
- `_build_task_inbox_payload`: (items, chips) tuple for task_inbox display.
- `_items_from_template`: profile_card item template interpolation.
"""

import datetime as _dt
import re
from typing import Any

# Display-name helpers moved to dazzle.render.display_names in #1094 so
# they're reachable from ui/ without crossing the back↔ui boundary.
# Re-exported here for back-internal callers.
from dazzle.render.display_names import _inject_display_names, _resolve_display_name  # noqa: F401

# v0.61.55 (#892): profile_card template-string interpolation. Matches
# `{{ field }}` and `{{ field.path.with.dots }}` only — no expressions,
# no filters, no Jinja eval. Anything that doesn't match the strict
# IDENT(.IDENT)* shape is left as a literal `{{ ... }}` placeholder so
# the author notices.
_CARD_TEMPLATE_RE = re.compile(r"\{\{\s*([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)\s*\}\}")


def _resolve_path(item: Any, path: str) -> Any:
    """Walk a dotted path against an item dict (#892).

    Used by profile_card to resolve `{{ tutor.full_name }}` against the
    fetched item. Returns ``None`` for any segment that's missing or
    not a dict. FK fields are dicts (with `__display__`/`name`/etc.) so
    a single-segment path on an FK column returns the dict; the caller
    can then `_resolve_display_name` it. For multi-segment paths the
    walk descends into the FK dict directly.
    """
    if not path:
        return None
    cur: Any = item
    for segment in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(segment)
        if cur is None:
            return None
    return cur


def _initials_from(name: str) -> str:
    """Compute initials from a name string for the avatar fallback (#892).

    Takes the first letter of up to the first 2 whitespace-separated
    words, uppercased. Empty / None input returns empty string.
    """
    if not name:
        return ""
    words = name.split()[:2]
    return "".join(w[0].upper() for w in words if w)


def _build_cohort_cells(
    *,
    items: list[dict[str, Any]],
    config: Any,
    active_lens_id: str,
) -> list[dict[str, Any]]:
    """Build cohort_strip cell dicts from already-scoped source rows (#1018).

    Each cell carries the member halo (id/name/subtitle/initials) plus
    the active lens's primary value with optional RAG tone. The
    active lens determines which field on the row supplies the
    primary value; the threshold (when set) determines the tone tint.

    `items` are the rows from the source-entity query — RBAC scope is
    already enforced by that query, the data-resolution layer just
    shapes results. `config` is `WorkspaceRegion.cohort_strip_config`.
    `active_lens_id` is the resolved active lens (already falling
    through ?lens param → config.default_lens → first lens upstream).

    Member name resolution priority:
      1. The `member_via` FK target's `__display__` (resolved by
         _inject_display_names upstream)
      2. `<member_via>_display` sibling key
      3. The member_via field's scalar value (id-shaped fallback)
      4. The row's own `name` field
      5. Empty string

    Tone derivation: when the active lens declares a numeric
    `threshold`, the renderer compares the primary value:
      - >= threshold → "good"
      - < threshold but within 10% of it → "warn"
      - < 90% of threshold → "bad"
    Polarity is above-good (typical for completion %, attendance %,
    SLA score). Reversing for below-good metrics is deferred until
    a real consumer needs it (encoded as a per-lens flag).
    """
    if not items or config is None:
        return []
    member_via = str(getattr(config, "member_via", "") or "")
    lenses = list(getattr(config, "lenses", []) or [])
    if not lenses or not member_via:
        return []
    # Resolve the active lens object (caller may have passed an id
    # that already fell back to the first lens).
    active_lens = next(
        (lens for lens in lenses if str(getattr(lens, "id", "")) == active_lens_id),
        lenses[0],
    )
    primary_field = str(getattr(active_lens, "primary", "") or "")
    threshold = getattr(active_lens, "threshold", None)

    cells: list[dict[str, Any]] = []
    for item in items:
        member_id = str(item.get("id", "") or "")
        if not member_id:
            continue  # row missing id is unrenderable; skip
        # Member name resolution (FK display name first, scalar fallback last).
        fk_value = item.get(member_via)
        if isinstance(fk_value, dict):
            member_name = _resolve_display_name(fk_value)
        else:
            member_name = str(item.get(f"{member_via}_display", "") or "")
            if not member_name:
                member_name = str(fk_value or "") or str(item.get("name", "") or "")
        # Primary value extraction.
        primary_raw = _resolve_path(item, primary_field) if primary_field else None
        primary_value = "" if primary_raw is None else str(primary_raw)
        # Tone derivation when threshold is configured.
        tone = "neutral"
        if threshold is not None and primary_raw is not None:
            try:
                primary_num = float(primary_raw)
                threshold_num = float(threshold)
            except (TypeError, ValueError):
                pass
            else:
                if primary_num >= threshold_num:
                    tone = "good"
                elif primary_num >= threshold_num * 0.9:
                    tone = "warn"
                else:
                    tone = "bad"
        cells.append(
            {
                "member_id": member_id,
                "member_name": member_name,
                "primary_value": primary_value,
                "subtitle": "",  # secondary metadata — populated by adapters that have it
                "avatar_initials": _initials_from(member_name),
                "tone": tone,
                "drill_url": "",  # entity_card drill-down lands once that ship adds the route
            }
        )
    return cells


def _build_day_timeline_slots(
    *,
    items: list[dict[str, Any]],
    config: Any,
    now: _dt.datetime,
) -> list[dict[str, Any]]:
    """Build day_timeline slot dicts from already-scoped source rows (#1016).

    Each slot carries (slot_id, label, position, body, drill_url).
    `position` is determined by comparing `now` against each row's
    [starts_at, ends_at] window — the slot whose window contains
    `now` becomes ``"active"``; earlier windows are ``"before"``;
    later windows are ``"after"``. At most one slot can be active.

    `items` are the rows from the source-entity query — RBAC scope
    is already enforced upstream. `config` is
    ``WorkspaceRegion.day_timeline_config``.

    Slot label uses a sensible default: "{starts_at_value} — {ends_at_value}"
    for time-bucketed display. Body is left empty in the IR-pure
    path; richer composite-card rendering against `config.card`
    is deferred until composite-card lookup wires up.

    Defensive paths: rows missing the configured starts_at field
    are skipped; rows whose timestamps don't parse as datetime are
    treated as ``"after"`` (latest-tier fallback rather than
    silently dropping the row).
    """
    if not items or config is None:
        return []
    starts_at_field = str(getattr(config, "starts_at", "") or "")
    ends_at_field = str(getattr(config, "ends_at", "") or "")
    if not starts_at_field or not ends_at_field:
        return []

    def _to_dt(value: Any) -> _dt.datetime | None:
        """Coerce a row value to an aware datetime. Accepts
        datetime instances and ISO-8601 strings."""
        if isinstance(value, _dt.datetime):
            return value if value.tzinfo else value.replace(tzinfo=_dt.UTC)
        if isinstance(value, str) and value:
            try:
                # Strip trailing Z and treat as UTC; otherwise rely on
                # fromisoformat to handle offset suffixes.
                stripped = value.rstrip("Z")
                if stripped.endswith("+00:00") or "T" in stripped or " " in stripped:
                    parsed = _dt.datetime.fromisoformat(stripped)
                    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.UTC)
            except ValueError:
                return None
        return None

    # Pre-compute (item, starts, ends) tuples and sort chronologically.
    rows: list[tuple[dict[str, Any], _dt.datetime | None, _dt.datetime | None]] = []
    for item in items:
        starts = _to_dt(item.get(starts_at_field))
        if starts is None:
            continue  # row without a parseable starts_at is unrenderable
        ends = _to_dt(item.get(ends_at_field))
        rows.append((item, starts, ends))
    rows.sort(key=lambda triple: triple[1] or _dt.datetime.min.replace(tzinfo=_dt.UTC))

    # Position assignment — exactly one row may be "active". A row is
    # active when its [starts, ends] window contains `now`; if `ends`
    # is None we treat the row as a point-in-time event and consider
    # it active only if it equals `now` to within a minute.
    active_seen = False
    slots: list[dict[str, Any]] = []
    now_aware = now if now.tzinfo else now.replace(tzinfo=_dt.UTC)
    for item, starts, ends in rows:
        slot_id = str(item.get("id", "") or "")
        if not slot_id:
            continue
        position = "after"
        if not active_seen and starts is not None:
            window_end = ends if ends is not None else starts
            if starts <= now_aware <= window_end:
                position = "active"
                active_seen = True
            elif window_end < now_aware:
                position = "before"
            else:
                position = "after"
        elif starts is not None and (ends or starts) < now_aware:
            position = "before"
        # Human-readable label: prefer name/title field, fall back
        # to the ISO timestamp range. The composite `card:` template
        # would render richer content; deferred ship.
        label_raw = item.get("name") or item.get("title") or item.get("message") or ""
        label = str(label_raw) if label_raw else f"{starts.isoformat() if starts else ''}"
        slots.append(
            {
                "slot_id": slot_id,
                "label": label,
                "position": position,
                "body": "",
                "drill_url": "",
            }
        )
    return slots


def _build_task_inbox_payload(
    *,
    items: list[dict[str, Any]],
    config: Any,
    items_per_source: dict[int, list[dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build (task_inbox_items, task_inbox_chips) from already-scoped
    source rows (#1015).

    The task_inbox config declares N sources, each either an
    ``as_task`` per-row template or a ``count_as`` collapsed-summary
    chip. Two resolution paths:

    * **Multi-source (preferred when available)** — `items_per_source`
      maps each source index to its already-scoped row list (one
      query per source, scoped via the source's own entity-level
      RBAC). Each source contributes its own typed items (for
      `as_task` sources) or chip count (for `count_as` sources).
      The upstream fan-out that builds this dict scopes per-entity
      and applies each source's `filter:` expression.
    * **Single-source MVP fallback** — when `items_per_source` is
      None or empty, falls through to the prior behavior: folds the
      region's primary `items` list against the FIRST `as_task`
      source, emits chips with count=0 for `count_as` sources. Used
      when the upstream fan-out hasn't been wired (or the
      task_inbox sits over a single homogeneous entity).

    `items` is the region's primary source query result (used by the
    fallback path). `config` is ``WorkspaceRegion.task_inbox_config``.
    """
    if config is None:
        return [], []
    sources = list(getattr(config, "sources", []) or [])
    if not sources:
        return [], []

    if items_per_source:
        return _resolve_task_inbox_multi_source(sources, items_per_source)

    # Single-source MVP fallback — used when the upstream fan-out
    # hasn't been wired yet.
    primary_template = None
    for src in sources:
        if getattr(src, "as_task", None) is not None:
            primary_template = getattr(src, "as_task", None)
            break

    inbox_items: list[dict[str, Any]] = []
    if primary_template is not None and items:
        for entry in _items_from_template(items, primary_template, prefix=""):
            inbox_items.append(entry)

    inbox_chips: list[dict[str, Any]] = []
    for idx, src in enumerate(sources):
        count_as = str(getattr(src, "count_as", "") or "")
        if not count_as:
            continue
        inbox_chips.append(
            {
                "chip_id": f"src{idx}",
                "count": 0,
                "label": count_as,
                "drill_url": "",
            }
        )

    return inbox_items, inbox_chips


def _items_from_template(
    items: list[dict[str, Any]], template: Any, *, prefix: str
) -> list[dict[str, Any]]:
    """Materialise typed task items from an `as_task` template +
    pre-scoped row list. Shared by single- and multi-source paths.

    `prefix` namespaces the resulting `item_id` so multiple sources
    can produce items with the same row-level id without collision
    (e.g. source 0's row "i1" → item_id "src0-i1")."""
    icon = str(getattr(template, "icon", "") or "")
    title_tmpl = str(getattr(template, "title", "") or "")
    meta_tmpl = str(getattr(template, "meta", "") or "")
    out: list[dict[str, Any]] = []
    for item in items:
        row_id = str(item.get("id", "") or "")
        if not row_id:
            continue
        item_id = f"{prefix}{row_id}" if prefix else row_id
        title = _interpolate_card_template(title_tmpl, item) if title_tmpl else ""
        meta = _interpolate_card_template(meta_tmpl, item) if meta_tmpl else ""
        urgency_raw = item.get("urgency") or item.get("severity") or item.get("priority") or "later"
        urgency = _coerce_urgency(str(urgency_raw))
        out.append(
            {
                "item_id": item_id,
                "icon": icon,
                "title": title,
                "meta": meta,
                "urgency": urgency,
                "drill_url": "",
            }
        )
    return out


def _coerce_urgency(value: str) -> str:
    """Map a free-form urgency/severity/priority string to one of
    the four task_inbox bands (overdue / due / soon / later)."""
    normalized = value.strip().lower()
    if normalized in ("overdue", "due", "soon", "later"):
        return normalized
    # Common aliases — severity-style and priority-style values.
    if normalized in ("critical", "high", "blocker", "urgent"):
        return "overdue"
    if normalized in ("medium", "warning", "warn"):
        return "due"
    if normalized in ("low", "minor", "info"):
        return "soon"
    return "later"


def _interpolate_card_template(template: str, item: dict[str, Any]) -> str:
    """Substitute `{{ field }}` / `{{ field.path }}` against an item (#892).

    The grammar is intentionally minimal — see ``_CARD_TEMPLATE_RE``.
    Unresolved paths render as empty string (graceful degradation —
    profile_card cards with one missing field still render the rest).
    The output is a plain string emitted by the typed renderer's body
    slot after the caller has html-escaped it — no template injection
    surface.
    """
    if not template:
        return ""

    def _sub(m: re.Match[str]) -> str:
        path = m.group(1)
        value = _resolve_path(item, path)
        if isinstance(value, dict):
            for key in ("__display__", "name", "title", "code", "label"):
                if key in value and value[key] is not None:
                    return str(value[key])
            return ""
        return "" if value is None else str(value)

    return _CARD_TEMPLATE_RE.sub(_sub, template)


def _coerce_pipeline_progress(raw: Any) -> tuple[int | None, bool]:
    """Coerce a pipeline_steps `progress:` value to (clamped_int, overshoot).

    v0.61.78 (#911): the `progress:` field accepts either a literal
    numeric string ("74") from the parser or a numeric result from
    an aggregate count query. Returns:
      - (None, False) when raw is None / empty / unparseable — caller
        renders no bar (preserves the no-progress shape)
      - (clamped, False) when 0 <= raw <= 100
      - (100, True) when raw > 100 — clamp to 100, flag overshoot for
        themes that want to surface "over capacity" visually
      - (0, False) when raw < 0 — clamp to 0
    """
    if raw is None or raw == "":
        return None, False
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, False
    if value > 100:
        return 100, True
    if value < 0:
        return 0, False
    return int(round(value)), False


def _resolve_task_inbox_multi_source(
    sources: list[Any],
    items_per_source: dict[int, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fan-out resolution: each source's pre-scoped row list maps to
    typed items (as_task) or a count chip (count_as).

    Order discipline: items are emitted in source-declaration order
    so the `urgency`-then-`deadline` sort downstream sees a stable
    base ordering. Chips emit in the same source order as the IR
    declares them.
    """
    inbox_items: list[dict[str, Any]] = []
    inbox_chips: list[dict[str, Any]] = []
    for idx, src in enumerate(sources):
        rows = items_per_source.get(idx, []) or []
        as_task = getattr(src, "as_task", None)
        count_as = str(getattr(src, "count_as", "") or "")
        if as_task is not None:
            inbox_items.extend(_items_from_template(rows, as_task, prefix=f"src{idx}-"))
        elif count_as:
            inbox_chips.append(
                {
                    "chip_id": f"src{idx}",
                    "count": len(rows),
                    "label": count_as,
                    "drill_url": "",
                }
            )
    return inbox_items, inbox_chips
