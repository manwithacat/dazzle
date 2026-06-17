"""Timeline-family region builders.

Houses the 4 timeline-family builders. All four produce a chronological
or event-stream Surface:

  - _build_timeline       Timeline of TimelineEvents with rich fields
  - _build_activity_feed  chronological dot + bubble feed
  - _build_day_timeline   vertical scroll of slot cards (#1016)
  - _build_task_inbox     workflow-led prioritised due-action list (#1015)

No family-local helpers — all cross-cutting plumbing lives in `_shared`
(_region_title, _wrap_surface, _render_typed_value). The legacy
`_timeago_filter` is imported inline (lazy) where needed.

See issue #1065 for the full decomposition plan.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    ActivityFeed,
    DayTimelineRegion,
    DayTimelineSlot,
    Fragment,
    Surface,
    TaskInboxItem,
    TaskInboxRegion,
    TaskInboxSummaryChip,
    Timeline,
    TimelineEvent,
)
from dazzle.render.fragment.region._shared import (
    _region_title,
    _render_typed_value,
    _wrap_surface,
)


class _BuildersTimelineMixin:
    """Mixin adding the 4 timeline-family `_build_*` methods to
    `WorkspaceRegionAdapter`. Same pattern as `_BuildersChartsMixin`.
    """

    def _build_timeline(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: timeline` regions render as a `Timeline` primitive
        matching `workspace/regions/timeline.html` byte-for-byte.

        Phase 4B.4 wave 2: extended to construct rich `TimelineEvent`
        instances carrying per-event date_label (already-formatted via
        `timeago` filter), title (from display_key), and secondary
        fields (per-column type-aware values, omitting the date and
        display_key columns). Click-through (`hx-get` on the content
        div) is not yet plumbed — read-only display only.

        ctx shape:
            items: list of dicts (rows from the source entity)
            columns: list of `{key, label, type, ref_route}` dicts —
                same shape as LIST/DETAIL columns
            display_key: str — column key for the primary title
                (defaults to 'title' / 'name' / 'id' fallback)
            entity_name: str — fallback title when display_key value is None
            total: int — overflow indicator denominator
            empty_message: optional empty-state fallback
        """
        from dazzle.render.filters import _timeago_filter

        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        columns = ctx.get("columns") or []
        display_key = str(ctx.get("display_key") or "")
        entity_name = str(ctx.get("entity_name") or "Event")
        try:
            total = int(ctx.get("total") or 0)
        except (TypeError, ValueError):
            total = 0

        # Identify the date column (first column with type=="date").
        date_col_key = ""
        for col in columns:
            if isinstance(col, dict) and col.get("type") == "date":
                date_col_key = str(col.get("key") or "")
                break

        events: list[TimelineEvent] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            # Date — always rendered via timeago filter for legacy parity.
            date_value = item.get(date_col_key) if date_col_key else None
            date_label = _timeago_filter(date_value) if date_value else ""
            # Title — display_key value, with fallback to name/entity_name.
            primary = item.get(display_key) if display_key else None
            if primary is None:
                primary = item.get("name") or entity_name
            # Secondary fields — every non-date, non-display column.
            fields: list[tuple[str, object]] = []
            for col in columns:
                if not isinstance(col, dict):
                    continue
                key = str(col.get("key") or "")
                if not key or key == display_key or col.get("type") == "date":
                    continue
                label = str(col.get("label") or key)
                # TIMELINE renders badges with `size='sm'` per legacy macro call.
                fields.append((label, _render_typed_value(item, col, badge_size="sm")))
            events.append(
                TimelineEvent(
                    title=str(primary),
                    date_label=date_label,
                    fields=tuple(fields),
                )
            )

        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No events yet."
        )
        body: Fragment = Timeline(events=tuple(events), total=total, empty_message=str(empty_msg))
        return _wrap_surface(title, "report", body)

    def _build_activity_feed(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: activity_feed` regions render as an ActivityFeed
        primitive — chronological feed with per-row dot, time line, and
        bubble carrying actor + description.

        Phase 4B.4 wave 1: dedicated builder (replaced prior alias to
        `_build_timeline`) so the typed-Fragment output matches
        `workspace/regions/activity_feed.html` byte-for-byte. Time
        strings are formatted via the legacy `timeago` filter so both
        paths produce the same relative-time labels.

        ctx shape:
            items: list of dicts with keys:
              - description: action description (required)
              - created_at: datetime (rendered via `timeago` filter)
              - actor or user: optional actor name
              - action / title: fallback description fields
        """
        from dazzle.render.filters import _timeago_filter

        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []

        body: Fragment
        if not items:
            empty_msg = (
                ctx.get("empty_message")
                or getattr(region, "empty_message", None)
                or "No activity yet"
            )
            body = ActivityFeed(items=(), empty_message=str(empty_msg))
        else:
            rows: list[tuple[str, str, str]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                created = item.get("created_at")
                time_str = _timeago_filter(created) if created else ""
                actor_raw = item.get("actor") or item.get("user") or ""
                actor = str(actor_raw) if actor_raw else ""
                description = str(
                    item.get("description") or item.get("action") or item.get("title") or ""
                )
                rows.append((time_str, actor, description))
            body = ActivityFeed(items=tuple(rows))

        return _wrap_surface(title, "report", body)

    def _build_day_timeline(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: day_timeline` regions render as a vertical
        chronological scroll of slot cards (#1016, v0.67.8).

        Reads `region.day_timeline_config` for the starts_at/ends_at
        field names + composite-card name, plus `ctx` for the resolved
        slots. The data resolution layer compares the now-window
        against each row's [starts_at, ends_at] range to set
        `position` on each slot.

        ctx shape:
            day_timeline_slots: list of dicts {"slot_id": str,
                "label": str, "position": "before"|"active"|"after"
                (default "after"), "body": str (pre-rendered HTML —
                adapter owns escape responsibility), "drill_url":
                str (default "")}.

        At most one slot may carry `position="active"` — the
        primitive enforces this. If the data resolution accidentally
        marks two active, the adapter's _build keeps the first and
        downgrades the rest to "after" rather than crashing.
        """
        title = _region_title(region)
        region_name = str(getattr(region, "name", "") or "day_timeline")
        empty_msg = getattr(region, "empty_message", None) or "No scheduled slots today."

        valid_positions = ("before", "active", "after")
        slots: list[DayTimelineSlot] = []
        active_seen = False
        for entry in ctx.get("day_timeline_slots") or []:
            if not isinstance(entry, dict):
                continue
            slot_id = str(entry.get("slot_id") or "")
            if not slot_id:
                continue
            label = str(entry.get("label") or "")
            position_raw = str(entry.get("position") or "after")
            position = position_raw if position_raw in valid_positions else "after"
            # Defensive: collapse extra "active" rows after the first
            # to "after" so we don't trip the primitive's at-most-one
            # invariant from a buggy upstream resolver.
            if position == "active":
                if active_seen:
                    position = "after"
                else:
                    active_seen = True
            slots.append(
                DayTimelineSlot(
                    slot_id=slot_id,
                    label=label,
                    position=position,  # type: ignore[arg-type]
                    body=str(entry.get("body") or ""),
                    drill_url=str(entry.get("drill_url") or ""),
                    action_html=str(entry.get("action_html") or ""),
                )
            )

        body: Fragment = DayTimelineRegion(
            region_name=region_name,
            slots=tuple(slots),
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "dashboard", body)

    def _build_task_inbox(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: task_inbox` regions render as a workflow-led
        prioritised list of due actions (#1015, v0.67.8).

        ctx shape:
            task_inbox_items: list of dicts {"item_id": str, "icon":
                str, "title": str, "meta": str (default ""),
                "urgency": "overdue"|"due"|"soon"|"later" (default
                "later"), "drill_url": str (default "")}.
            task_inbox_chips: list of dicts {"chip_id": str, "count":
                int, "label": str, "drill_url": str (default "")} —
                collapsed-summary chips for `count_as` sources.

        The data resolution layer is responsible for resolving
        `as_task` template strings against source rows AND for
        sorting items by the IR's `order` keys (urgency + deadline).
        This adapter just renders the resolved + sorted shape.
        """
        title = _region_title(region)
        region_name = str(getattr(region, "name", "") or "task_inbox")
        empty_msg = getattr(region, "empty_message", None)
        cfg = getattr(region, "task_inbox_config", None)
        # Empty-state copy comes from the IR config when set;
        # region.empty_message overrides if present.
        if empty_msg is None and cfg is not None:
            empty_msg = getattr(cfg, "empty_state", None)
        empty_msg = str(empty_msg or "All caught up.")

        valid_urgencies = ("overdue", "due", "soon", "later")
        items: list[TaskInboxItem] = []
        for entry in ctx.get("task_inbox_items") or []:
            if not isinstance(entry, dict):
                continue
            item_id = str(entry.get("item_id") or "")
            if not item_id:
                continue
            urgency_raw = str(entry.get("urgency") or "later")
            urgency = urgency_raw if urgency_raw in valid_urgencies else "later"
            items.append(
                TaskInboxItem(
                    item_id=item_id,
                    icon=str(entry.get("icon") or ""),
                    title=str(entry.get("title") or ""),
                    meta=str(entry.get("meta") or ""),
                    urgency=urgency,  # type: ignore[arg-type]
                    drill_url=str(entry.get("drill_url") or ""),
                )
            )

        chips: list[TaskInboxSummaryChip] = []
        for entry in ctx.get("task_inbox_chips") or []:
            if not isinstance(entry, dict):
                continue
            chip_id = str(entry.get("chip_id") or "")
            if not chip_id:
                continue
            try:
                count = int(entry.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            if count < 0:
                count = 0  # primitive rejects negative; defensive coercion
            chips.append(
                TaskInboxSummaryChip(
                    chip_id=chip_id,
                    count=count,
                    label=str(entry.get("label") or ""),
                    drill_url=str(entry.get("drill_url") or ""),
                )
            )

        body: Fragment = TaskInboxRegion(
            region_name=region_name,
            items=tuple(items),
            summary_chips=tuple(chips),
            empty_message=empty_msg,
        )
        return _wrap_surface(title, "dashboard", body)
