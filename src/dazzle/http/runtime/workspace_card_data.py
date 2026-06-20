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
import logging
import math
import re
from typing import Any

# Display-name helpers moved to dazzle.render.display_names in #1094 so
# they're reachable from ui/ without crossing the back↔ui boundary.
# Re-exported here for back-internal callers.
from dazzle.render.display_names import _inject_display_names, _resolve_display_name  # noqa: F401

logger = logging.getLogger(__name__)

# v0.61.55 (#892): profile_card template-string interpolation. Matches
# `{{ field }}` and `{{ field.path.with.dots }}` — and (#1145 part 1)
# an optional ``| transform`` suffix that runs the resolved value
# through a registered helper (see ``_TIME_TRANSFORMS``). No
# expressions, no Jinja eval. Anything that doesn't match the strict
# shape is left as a literal `{{ ... }}` placeholder so the author
# notices.
_CARD_TEMPLATE_RE = re.compile(
    r"\{\{\s*([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)\s*"
    r"(?:\|\s*([A-Za-z_][\w]*)\s*)?\}\}"
)


def _now_utc() -> _dt.datetime:
    """#1145 part 1: indirect ``now`` for time-transform helpers.

    Tests monkeypatch this in the module namespace to control the
    "current time" against which ``minutes_until`` / ``age`` /
    ``until`` resolve. Production code reads the wall clock.
    """
    return _dt.datetime.now(tz=_dt.UTC)


def _coerce_to_datetime(value: Any) -> _dt.datetime | None:
    """Best-effort coercion of a row value to an aware datetime.

    Accepts ``datetime`` instances (assumed UTC when naive),
    ``date`` instances (midnight UTC), and ISO-8601 strings. HH:MM
    strings compose against today's UTC date — matches the
    day_timeline ``as_of: today`` shape so the same row value
    works in both places.
    """
    if isinstance(value, _dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=_dt.UTC)
    if isinstance(value, _dt.date):
        return _dt.datetime.combine(value, _dt.time(0, 0), tzinfo=_dt.UTC)
    if isinstance(value, _dt.time):
        return _dt.datetime.combine(_now_utc().date(), value, tzinfo=_dt.UTC)
    if isinstance(value, str) and value:
        try:
            stripped = value.rstrip("Z")
            if stripped.endswith("+00:00") or "T" in stripped or " " in stripped:
                parsed = _dt.datetime.fromisoformat(stripped)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.UTC)
        except ValueError:
            pass
        # HH:MM[:SS] compose with today's date — same shape as
        # day_timeline's `as_of: today` resolver.
        try:
            return _dt.datetime.combine(
                _now_utc().date(), _dt.time.fromisoformat(value), tzinfo=_dt.UTC
            )
        except ValueError:
            return None
    return None


def _transform_minutes_until(value: Any) -> str:
    """``minutes_until`` — render the gap between a target time and now.

    Output shape (matches AegisMark's `pipeline/views/today.py`
    `_minutes_until` contract):

    - target == now (within a minute) → ``"now"``
    - 1 ≤ delta < 60 minutes → ``"in {N} minutes"`` / ``"in 1 minute"``
    - 1 ≤ delta_hours < 24 → ``"in {N} hours"`` / ``"in 1 hour"``
    - past, same calendar day (UTC) → ``"earlier today"``
    - past, earlier than today → ``"overdue"``
    - future, later than today (≥24h) → ``"in {N} days"``
    """
    target = _coerce_to_datetime(value)
    if target is None:
        return ""
    now = _now_utc()
    delta = (target - now).total_seconds()
    minutes = int(round(delta / 60))
    if minutes == 0:
        return "now"
    if minutes > 0:
        if minutes < 60:
            return f"in {minutes} minute{'s' if minutes != 1 else ''}"
        hours = minutes // 60
        if hours < 24:
            return f"in {hours} hour{'s' if hours != 1 else ''}"
        days = hours // 24
        return f"in {days} day{'s' if days != 1 else ''}"
    # Past.
    if target.date() == now.date():
        return "earlier today"
    return "overdue"


def _transform_age(value: Any) -> str:
    """``age`` — render how long ago a timestamp occurred.

    - within a minute → ``"just now"``
    - < 1 hour → ``"{N} minutes ago"``
    - < 1 day → ``"{N} hours ago"``
    - else → ``"{N} days ago"``

    Future timestamps render as ``"just now"`` (clock skew / data
    entry off-by-one is more common than a genuine future event).
    """
    target = _coerce_to_datetime(value)
    if target is None:
        return ""
    delta = (_now_utc() - target).total_seconds()
    if delta < 60:
        return "just now"
    minutes = int(delta // 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def _transform_until(value: Any) -> str:
    """``until`` — render due-by relative to today.

    Day-granularity (vs ``minutes_until`` which is clock-granularity).
    Matches the typical "due_at | until" shape for inbox surfaces:

    - target.date() == today → ``"due today"``
    - target.date() == tomorrow → ``"due tomorrow"``
    - future → ``"due in {N} days"``
    - past → ``"overdue by {N} days"`` (or ``"overdue"`` at 1 day)
    """
    target = _coerce_to_datetime(value)
    if target is None:
        return ""
    today = _now_utc().date()
    delta_days = (target.date() - today).days
    if delta_days == 0:
        return "due today"
    if delta_days == 1:
        return "due tomorrow"
    if delta_days > 0:
        return f"due in {delta_days} days"
    overdue = -delta_days
    if overdue == 1:
        return "overdue"
    return f"overdue by {overdue} days"


_TIME_TRANSFORMS: dict[str, Any] = {
    "minutes_until": _transform_minutes_until,
    "age": _transform_age,
    "until": _transform_until,
}


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


def _apply_format_spec(value: Any, format_spec: str, *, context: str = "") -> str:
    """Apply a Python format spec (or ``str.format`` template) to a value.

    Shared (#1300) by bar_track's ``track_format`` and cohort_strip aggregate
    lenses' ``primary_aggregate.format``. Empty spec → ``str(value)``. A spec
    containing ``{`` is treated as a ``str.format`` template (``"{:.1f}"``);
    otherwise as a ``format()`` spec (``".1f"``). An invalid spec warns and
    falls back to the raw value — never raises into the render path.
    """
    if not format_spec:
        return str(value)
    try:
        if "{" in format_spec:
            return format_spec.format(value)
        return format(value, format_spec)
    except (ValueError, TypeError, KeyError, IndexError):
        logger.warning(
            "invalid format spec %r%s — rendering raw value",
            format_spec,
            f" ({context})" if context else "",
        )
        return str(value)


def _default_round_numeric(value: Any) -> str:
    """Render a numeric value cleanly when no explicit format is given (#1300).

    Cohort aggregate lenses (``avg``) emit a Decimal/float that stringifies as
    e.g. ``'7.7500000000000000'``. With no ``format:`` knob set we round to a
    sensible default: 2 decimal places with trailing zeros trimmed, and
    integral results rendered without a decimal point (``8.0`` → ``"8"``,
    ``7.75`` → ``"7.75"``, ``7.3333`` → ``"7.33"``). Non-numeric values pass
    through as ``str(value)`` unchanged (counts are already ints; a string
    primary is left alone).
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    # nan/inf have no sensible rounded form and would blow up `int(...)`
    # below (ValueError/OverflowError) — render them raw rather than crash.
    if not math.isfinite(num):
        return str(value)
    rounded = round(num, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def _build_cohort_cells(
    *,
    items: list[dict[str, Any]],
    config: Any,
    active_lens_id: str,
    source_display_field: str = "",
    row_action: Any = None,
    cohort_aggregate_values: dict[str, Any] | None = None,
    row_action_routes: dict[str, str] | None = None,
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
      3. The source entity's `display_field` column (#1299 — covers the
         self-referential `member_via: id` case, where there is no FK
         display sibling and the scalar value is the row's own UUID)
      4. The member_via field's scalar value (id-shaped fallback)
      5. The row's own `name` field
      6. Empty string

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
    # #1144 part 2: composite primary (tuple display). When set, the
    # cell's primary_value is the join of each part's resolved field.
    composite_primary = getattr(active_lens, "primary_composite", None)
    # #1144 Gap 1 phase 2: aggregate-primary lens. The per-member values
    # have been resolved upstream by ``compute_cohort_aggregate_primary``
    # and threaded through as ``cohort_aggregate_values``. The
    # ``via:`` junction-binding case is phase 3 — when set, the
    # upstream helper logs a warning and returns an empty dict, so
    # the cells below render without a value.
    aggregate_primary = getattr(active_lens, "primary_aggregate", None)
    aggregate_values = cohort_aggregate_values or {}
    # #1144 part 1: multi-band tone mapping (supersedes scalar
    # threshold when non-empty). Pre-sorted descending by `at` so
    # the highest band a value clears determines its tone.
    raw_bands = list(getattr(active_lens, "tone_bands", []) or [])
    tone_bands = sorted(raw_bands, key=lambda b: float(getattr(b, "at", 0.0)), reverse=True)

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
            if not member_name and source_display_field:
                # #1299: self-referential member_via (e.g. `member_via: id`)
                # has no `<member_via>_display` sibling — fk_value is the row's
                # own PK (a UUID), not a name. Use the source entity's
                # display_field column before the raw-id fallback below.
                member_name = str(item.get(source_display_field, "") or "")
            if not member_name:
                member_name = str(fk_value or "") or str(item.get("name", "") or "")
        # Primary value extraction. Three mutually-exclusive shapes
        # (IR validator enforces): composite, aggregate, scalar.
        if composite_primary is not None:
            parts_rendered: list[str] = []
            for part in composite_primary.parts:
                part_field = str(getattr(part, "field", "") or "")
                part_raw = _resolve_path(item, part_field) if part_field else None
                parts_rendered.append("" if part_raw is None else str(part_raw))
            primary_value = composite_primary.separator.join(parts_rendered)
            primary_raw = None  # tone derivation N/A for composites
        elif aggregate_primary is not None:
            # #1144 Gap 1 phase 2: per-member value resolved upstream
            # by compute_cohort_aggregate_primary. Missing key →
            # query failed / returned no rows → cell renders empty.
            primary_raw = aggregate_values.get(member_id)
            if primary_raw is None:
                primary_value = ""
            else:
                # #1300: honour the lens's `format:` knob (mirrors bar_track's
                # track_format); with no knob, default-round so an `avg` lens
                # stops rendering raw floats like '7.7500000000000000'.
                agg_format = str(getattr(aggregate_primary, "format", "") or "")
                primary_value = (
                    _apply_format_spec(
                        primary_raw, agg_format, context=f"cohort lens {active_lens_id!r}"
                    )
                    if agg_format
                    else _default_round_numeric(primary_raw)
                )
        else:
            primary_raw = _resolve_path(item, primary_field) if primary_field else None
            primary_value = "" if primary_raw is None else str(primary_raw)
        # Tone derivation. #1144 part 1 path takes precedence: walk
        # the sorted bands, take first whose `at` the value clears.
        # Fall back to the scalar `threshold:` trichotomy when bands
        # are empty (the pre-#1144 contract). Neutral when neither is
        # set or the value can't be coerced to a number.
        tone = "neutral"
        if primary_raw is not None:
            try:
                primary_num = float(primary_raw)
            except (TypeError, ValueError):
                primary_num = None
            if primary_num is not None:
                if tone_bands:
                    for band in tone_bands:
                        if primary_num >= float(getattr(band, "at", 0.0)):
                            tone = str(getattr(band, "tone", "neutral"))
                            break
                elif threshold is not None:
                    try:
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
        # #1148: pre-render the per-cell action button HTML when the
        # region declares `row_action:`. Same predicate semantics as
        # the list and day_timeline paths.
        action_html = ""
        if row_action is not None:
            from dazzle.render.fragment.region.workspace_card_bodies import (
                _eval_row_condition,
                _render_row_action_button,
            )

            vw = getattr(row_action, "visible_when", None)
            visible = True if vw is None else _eval_row_condition(vw, item)
            if visible:
                _aid = str(getattr(row_action, "action_id", ""))
                action_html = _render_row_action_button(
                    action_id=_aid,
                    label=str(getattr(row_action, "label", "")),
                    item=item,
                    bind=dict(getattr(row_action, "bind", {}) or {}),
                    extra_class="dz-cohort-strip-cell-action-btn",
                    action_url=(row_action_routes or {}).get(_aid, ""),
                )
        cells.append(
            {
                "member_id": member_id,
                "member_name": member_name,
                "primary_value": primary_value,
                "subtitle": "",  # secondary metadata — populated by adapters that have it
                "avatar_initials": _initials_from(member_name),
                "tone": tone,
                "drill_url": "",  # entity_card drill-down lands once that ship adds the route
                "action_html": action_html,
            }
        )
    return cells


def _build_day_timeline_slots(
    *,
    items: list[dict[str, Any]],
    config: Any,
    now: _dt.datetime,
    row_action: Any = None,
    row_action_routes: dict[str, str] | None = None,
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
    for time-bucketed display. Slot body is the
    ``_interpolate_card_template`` expansion of ``config.card`` against
    the row dict — same ``{{ field }}`` / ``{{ field.path }}`` grammar
    as ``profile_card`` / ``task_inbox`` use (#1146 part 1). Empty
    ``config.card`` keeps the body empty (minimal slot rendering).

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
    as_of_spec = str(getattr(config, "as_of", "") or "")

    def _resolve_date_anchor(item: dict[str, Any]) -> _dt.date | None:
        """#1146 part 2: resolve the date anchor for HH:MM timetables.

        ``as_of_spec`` is ``""`` (no composition), ``"today"`` (current
        UTC date), or a row field name. Returns ``None`` when the
        spec resolves to something unparseable — caller falls back
        to the pre-composition path.
        """
        if not as_of_spec:
            return None
        if as_of_spec == "today":
            return _dt.datetime.now(tz=_dt.UTC).date()
        raw = item.get(as_of_spec)
        if isinstance(raw, _dt.date) and not isinstance(raw, _dt.datetime):
            return raw
        if isinstance(raw, _dt.datetime):
            return raw.date()
        if isinstance(raw, str) and raw:
            try:
                return _dt.date.fromisoformat(raw[:10])
            except ValueError:
                return None
        return None

    def _to_dt(value: Any, *, anchor: _dt.date | None = None) -> _dt.datetime | None:
        """Coerce a row value to an aware datetime. Accepts:

        - ``datetime`` instances
        - ISO-8601 datetime strings
        - ``time`` instances or ``HH:MM[:SS]`` strings when ``anchor``
          is set (composes ``anchor`` + the time-of-day)
        """
        if isinstance(value, _dt.datetime):
            return value if value.tzinfo else value.replace(tzinfo=_dt.UTC)
        if isinstance(value, _dt.time) and anchor is not None:
            return _dt.datetime.combine(anchor, value, tzinfo=_dt.UTC)
        if isinstance(value, str) and value:
            # Full datetime first (handles existing rows).
            try:
                stripped = value.rstrip("Z")
                if stripped.endswith("+00:00") or "T" in stripped or " " in stripped:
                    parsed = _dt.datetime.fromisoformat(stripped)
                    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.UTC)
            except ValueError:
                pass
            # HH:MM / HH:MM:SS — only with an anchor.
            if anchor is not None:
                try:
                    return _dt.datetime.combine(
                        anchor, _dt.time.fromisoformat(value), tzinfo=_dt.UTC
                    )
                except ValueError:
                    return None
            return None
        return None

    # Pre-compute (item, starts, ends) tuples and sort chronologically.
    rows: list[tuple[dict[str, Any], _dt.datetime | None, _dt.datetime | None]] = []
    for item in items:
        # #1146 part 2: resolve a per-row date anchor when `as_of` is
        # set so HH:MM `time` values can compose to a full datetime.
        anchor = _resolve_date_anchor(item)
        starts = _to_dt(item.get(starts_at_field), anchor=anchor)
        if starts is None:
            continue  # row without a parseable starts_at is unrenderable
        ends = _to_dt(item.get(ends_at_field), anchor=anchor)
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
        # to the ISO timestamp range.
        label_raw = item.get("name") or item.get("title") or item.get("message") or ""
        label = str(label_raw) if label_raw else f"{starts.isoformat() if starts else ''}"
        # #1146 part 1: composite-card body interpolation. `config.card`
        # is a `{{ field }}` template (same grammar as profile_card,
        # task_inbox). Empty template → empty body (no regression for
        # configs that don't set `card:`).
        card_template = str(getattr(config, "card", "") or "")
        body = _interpolate_card_template(card_template, item) if card_template else ""
        # #1148: pre-render the per-slot action button HTML when the
        # region declares `row_action:`. Same predicate semantics as
        # the list display — visible_when false → empty action_html.
        action_html = ""
        if row_action is not None:
            from dazzle.render.fragment.region.workspace_card_bodies import (
                _eval_row_condition,
                _render_row_action_button,
            )

            vw = getattr(row_action, "visible_when", None)
            visible = True if vw is None else _eval_row_condition(vw, item)
            if visible:
                _aid = str(getattr(row_action, "action_id", ""))
                action_html = _render_row_action_button(
                    action_id=_aid,
                    label=str(getattr(row_action, "label", "")),
                    item=item,
                    bind=dict(getattr(row_action, "bind", {}) or {}),
                    extra_class="dz-day-timeline-slot-action-btn",
                    action_url=(row_action_routes or {}).get(_aid, ""),
                )
        slots.append(
            {
                "slot_id": slot_id,
                "label": label,
                "position": position,
                "body": body,
                "drill_url": "",
                "action_html": action_html,
            }
        )
    return slots


def _build_task_inbox_payload(
    *,
    items: list[dict[str, Any]],
    config: Any,
    items_per_source: dict[int, list[dict[str, Any]]] | None = None,
    entity_detail_urls: dict[str, str] | None = None,
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
    # #1303: entity → detail-URL template map (drill-gated upstream — empty
    # when the region opted out via `drill: none`). Per-source lookup
    # populates each item's drill_url.
    detail_urls = entity_detail_urls or {}

    if items_per_source:
        return _resolve_task_inbox_multi_source(sources, items_per_source, detail_urls)

    # Single-source MVP fallback — used when the upstream fan-out
    # hasn't been wired yet.
    primary_template = None
    primary_source = ""
    for src in sources:
        if getattr(src, "as_task", None) is not None:
            primary_template = getattr(src, "as_task", None)
            primary_source = str(getattr(src, "source", "") or "")
            break

    inbox_items: list[dict[str, Any]] = []
    if primary_template is not None and items:
        for entry in _items_from_template(
            items,
            primary_template,
            prefix="",
            detail_url_template=detail_urls.get(primary_source, ""),
        ):
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
    items: list[dict[str, Any]], template: Any, *, prefix: str, detail_url_template: str = ""
) -> list[dict[str, Any]]:
    """Materialise typed task items from an `as_task` template +
    pre-scoped row list. Shared by single- and multi-source paths.

    `prefix` namespaces the resulting `item_id` so multiple sources
    can produce items with the same row-level id without collision
    (e.g. source 0's row "i1" → item_id "src0-i1").

    `detail_url_template` (#1303), when set (e.g. "/app/assessment-event/{id}"),
    is substituted per row to populate each item's `drill_url` so the inbox
    item links to the entity detail. The task_inbox item renderer already
    wraps items in `<a href=drill_url>` when set; an unresolvable template
    (row missing the key) yields no link rather than crashing."""
    icon = str(getattr(template, "icon", "") or "")
    title_tmpl = str(getattr(template, "title", "") or "")
    meta_tmpl = str(getattr(template, "meta", "") or "")
    via_joins = dict(getattr(template, "via_joins", {}) or {})
    out: list[dict[str, Any]] = []
    for item in items:
        row_id = str(item.get("id", "") or "")
        if not row_id:
            continue
        item_id = f"{prefix}{row_id}" if prefix else row_id
        # #1145 part 2: resolve each via_joins alias against the row
        # (walking FK-hydrated sub-dicts) and stash under that alias
        # so the template can reference `{{ alias.field }}`. Pure
        # local-row resolution — no extra queries. Resolved values
        # written to a shallow copy so the input row isn't mutated.
        if via_joins:
            row = dict(item)
            for alias, path in via_joins.items():
                row[alias] = _resolve_path(item, path)
        else:
            row = item
        title = _interpolate_card_template(title_tmpl, row) if title_tmpl else ""
        meta = _interpolate_card_template(meta_tmpl, row) if meta_tmpl else ""
        urgency_raw = row.get("urgency") or row.get("severity") or row.get("priority") or "later"
        urgency = _coerce_urgency(str(urgency_raw))
        drill_url = ""
        if detail_url_template:
            try:
                drill_url = detail_url_template.format(**item)
            except (KeyError, IndexError, ValueError):
                drill_url = ""  # row missing the template key — no link
        out.append(
            {
                "item_id": item_id,
                "icon": icon,
                "title": title,
                "meta": meta,
                "urgency": urgency,
                "drill_url": drill_url,
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
    """Substitute `{{ field }}` / `{{ field.path }}` / `{{ field | transform }}`
    against an item (#892, transform suffix added in #1145 part 1).

    The grammar is intentionally minimal — see ``_CARD_TEMPLATE_RE``.
    Unresolved paths render as empty string (graceful degradation —
    profile_card cards with one missing field still render the rest).
    The output is a plain string emitted by the typed renderer's body
    slot after the caller has html-escaped it — no template injection
    surface.

    Registered transforms live in ``_TIME_TRANSFORMS`` —
    ``minutes_until``, ``age``, ``until``. Unknown transform names
    fall back to the raw value (string-rendered), matching the
    "graceful degradation" convention.
    """
    if not template:
        return ""

    def _sub(m: re.Match[str]) -> str:
        path = m.group(1)
        transform_name = m.group(2)  # None when no `| transform` suffix
        value = _resolve_path(item, path)
        if isinstance(value, dict):
            for key in ("__display__", "name", "title", "code", "label"):
                if key in value and value[key] is not None:
                    value = value[key]
                    break
            else:
                value = None
        if transform_name is not None:
            transform = _TIME_TRANSFORMS.get(transform_name)
            if transform is not None:
                return str(transform(value))
            # Unknown transform — fall through to raw value rendering.
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
    entity_detail_urls: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fan-out resolution: each source's pre-scoped row list maps to
    typed items (as_task) or a count chip (count_as).

    Order discipline: items are emitted in source-declaration order
    so the `urgency`-then-`deadline` sort downstream sees a stable
    base ordering. Chips emit in the same source order as the IR
    declares them.
    """
    detail_urls = entity_detail_urls or {}
    inbox_items: list[dict[str, Any]] = []
    inbox_chips: list[dict[str, Any]] = []
    for idx, src in enumerate(sources):
        rows = items_per_source.get(idx, []) or []
        as_task = getattr(src, "as_task", None)
        count_as = str(getattr(src, "count_as", "") or "")
        if as_task is not None:
            src_name = str(getattr(src, "source", "") or "")
            inbox_items.extend(
                _items_from_template(
                    rows,
                    as_task,
                    prefix=f"src{idx}-",
                    detail_url_template=detail_urls.get(src_name, ""),
                )
            )
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
