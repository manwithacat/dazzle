"""Timeline-family region builders.

Houses the timeline-family builders. Chronological / event-stream Surfaces:

  - _build_timeline       Timeline of TimelineEvents with rich fields
  - _build_activity_feed  chronological dot + bubble feed
  - _build_conversation   MessageScroller of Message (+Bubble) hyperparts (display: conversation)
  - _build_day_timeline   vertical scroll of slot cards (#1016)
  - _build_task_inbox     workflow-led prioritised due-action list (#1015)

No family-local helpers — all cross-cutting plumbing lives in `_shared`
(_region_title, _wrap_surface, _render_typed_value). The legacy
`_timeago_filter` is imported inline (lazy) where needed.

See issue #1065 for the full decomposition plan.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dazzle.render.fragment import (
    ActivityFeed,
    Bubble,
    DayTimelineRegion,
    DayTimelineSlot,
    Fragment,
    Message,
    MessageScroller,
    Surface,
    TaskInboxItem,
    TaskInboxRegion,
    TaskInboxSummaryChip,
    Timeline,
    TimelineEvent,
)
from dazzle.render.fragment.region._context import RegionContext
from dazzle.render.fragment.region._row_links import _resolve_row_links
from dazzle.render.fragment.region._shared import (
    _region_title,
    _render_typed_value,
    _wrap_surface,
    format_primary_display,
)
from dazzle.render.fragment.renderer._related_conversation import (
    conversation_bubble_tone,
    conversation_channel_label,
    conversation_time_label,
)
from dazzle.render.presentation import present
from dazzle.render.user_chip import looks_like_person_ref

# Body fields for activity-feed description (first non-empty wins).
# Comment entities use `content`; generic feeds often use description/title.
_ACTIVITY_DESCRIPTION_KEYS = (
    "description",
    "action",
    "title",
    "content",
    "body",
    "message",
    "text",
    "summary",
)
_ACTIVITY_ACTOR_KEYS = ("actor", "user", "author", "signatory_name", "created_by")


def _activity_description(item: dict[str, Any]) -> str:
    """Resolve a non-empty description string from a feed row dict."""
    for key in _ACTIVITY_DESCRIPTION_KEYS:
        raw = item.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def _activity_actor_label(item: dict[str, Any]) -> str:
    """Resolve actor display string (scalar or nested name/email)."""
    # Prefer precomputed ``*_display`` labels (FK join shells often id-only).
    for key in _ACTIVITY_ACTOR_KEYS:
        disp = item.get(f"{key}_display")
        if disp is not None and str(disp).strip():
            return str(disp).strip()
    for key in _ACTIVITY_ACTOR_KEYS:
        raw = item.get(key)
        if raw is None or raw == "":
            continue
        if isinstance(raw, dict):
            for sub in ("name", "email", "label", "title", "display"):
                v = raw.get(sub)
                if v is not None and str(v).strip():
                    return str(v).strip()
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def _activity_actor_col(key: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": key.replace("_", " ").title(),
        "type": "ref",
        "ref_entity": "User",
    }


def _present_timeline_person(value: Any, col: dict[str, Any]) -> str:
    """Avatar HTML from present(person, timeline_meta), or empty."""
    if not looks_like_person_ref(value, col):
        return ""
    pr = present("person", "timeline_meta", value, col)
    if pr.is_html and pr.html and "dz-avatar" in pr.html:
        return pr.html
    return ""


def _activity_actor_html(item: dict[str, Any]) -> str:
    """Person-ref actors emit present(person, timeline_meta) Avatar.

    Scalar leftover (``Ada``, ``System``) stays escaped text — do not invent
    a chip from a bare string (cycle 2159; oral #43).
    """
    for key in _ACTIVITY_ACTOR_KEYS:
        raw = item.get(key)
        if isinstance(raw, dict):
            html = _present_timeline_person(raw, _activity_actor_col(key))
            if html:
                return html
    for key in _ACTIVITY_ACTOR_KEYS:
        disp = item.get(f"{key}_display")
        raw = item.get(key)
        if not disp or raw is None or isinstance(raw, dict):
            continue
        name = str(disp).strip()
        if not name:
            continue
        html = _present_timeline_person({"name": name, "id": raw}, _activity_actor_col(key))
        if html:
            return html
    return ""


def _activity_empty_message(region: Any, ctx: RegionContext) -> str:
    return str(
        ctx.get("empty_message") or getattr(region, "empty_message", None) or "No activity yet"
    )


def _conversation_orientation(item: dict[str, Any]) -> str:
    """Map a conversation row to Bubble ``from_`` (in|out)."""
    raw = item.get("from") or item.get("direction") or item.get("from_")
    if raw is not None and str(raw).strip().lower() in ("in", "out"):
        return str(raw).strip().lower()
    # Support-ticket internal notes / agent replies → outbound surface.
    for key in ("is_internal", "internal", "is_agent", "outbound"):
        val = item.get(key)
        if val is True or (isinstance(val, str) and val.strip().lower() in ("true", "1", "yes")):
            return "out"
        if val is False or (isinstance(val, str) and val.strip().lower() in ("false", "0", "no")):
            return "in"
    return "in"


_TIMELINE_WHEN_TYPES = frozenset({"date", "datetime"})


def _timeline_when_col_key(columns: Any) -> str:
    """First date or datetime column is the timeline when-rail.

    Production columns type ``logged_at`` / ``created_at`` as
    ``datetime``. The rail used to match only ``type==date``, so
    fieldtest tester_activity hid when (oral #143). Leftover junk
    stays put via ``_timeago_filter``.
    """
    for col in columns or []:
        if not isinstance(col, dict):
            continue
        key = str(col.get("key") or "")
        if key and str(col.get("type") or "") in _TIMELINE_WHEN_TYPES:
            return key
    return ""


def _conversation_time(item: dict[str, Any]) -> tuple[str, str]:
    """Return (time_label, time_datetime) from common timestamp fields.

    Friendly profile dates and ISO/Postgres timestamps share
    ``conversation_time_label`` (oral #142). Leftover junk stays put.
    """
    for key in ("created_at", "timestamp", "time", "sent_at", "updated_at"):
        raw = item.get(key)
        if raw is None or raw == "":
            continue
        text = str(raw).strip()
        if not text:
            continue
        return conversation_time_label(text)
    return "", ""


def _media_initials(author: str) -> str:
    words = [w for w in author.strip().split() if w]
    if not words:
        return ""
    return "".join(w[0] for w in words[:2]).upper()


def _conversation_bubble_tone(item: dict[str, Any]) -> str:
    """Map customer_tone / escalation / note_phase / sentiment → Bubble danger.

    Peer Zendesk/Front/Intercom trails flag frustrated/urgent speech and
    raised/critical escalations so agents lean in; ops PagerDuty trails map
    note_phase escalate/mitigate the same way. Neutral/observe stays untoned.
    """
    for key in (
        "customer_tone",
        "tone",
        "sentiment",
        "customer_sentiment",
        "mood",
        "escalation",
        "escalation_level",
        "escalated",
        "note_phase",
        "phase",
        "timeline_phase",
        "incident_phase",
        "note_kind",
        "kind",
    ):
        raw = item.get(key)
        if raw is None or raw == "":
            continue
        tone = conversation_bubble_tone(str(raw))
        if tone:
            return tone
    return ""


def _conversation_message(
    text: str,
    orient: str,
    *,
    author: str = "",
    time_label: str = "",
    time_datetime: str = "",
    media_label: str = "",
    drill_url: str = "",
    bubble_tone: str = "",
) -> Message:
    """Build a Message row wrapping a Bubble for conversation stacks."""
    bubble = Bubble(
        text=text,
        from_=orient,  # type: ignore[arg-type]
        tone=bubble_tone or "",  # type: ignore[arg-type]
    )
    author_s = author.strip()
    if not author_s:
        author_s = "Agent" if orient == "out" else "Customer"
    media = media_label.strip() or _media_initials(author_s)
    return Message(
        bubble=bubble,
        author=author_s,
        time_label=time_label,
        time_datetime=time_datetime,
        media_label=media,
        from_=orient,  # type: ignore[arg-type]
        drill_url=(drill_url or "").strip(),
    )


def _activity_drill_by_id(items: list[dict[str, Any]], detail_url_template: str) -> dict[int, str]:
    """#1303 map of ``id(row)`` → resolved hub URL (empty template → {})."""
    if not detail_url_template:
        return {}
    row_links = _resolve_row_links(items, detail_url_template)
    out: dict[int, str] = {}
    for item, link in zip(items, row_links, strict=False):
        if link:
            out[id(item)] = str(link)
    return out


def _activity_feed_rows(
    items: list[Any],
    drill_by_id: dict[int, str],
    *,
    timeago: Callable[[Any], str],
) -> list[tuple[str, str, str] | tuple[str, str, str, str] | tuple[str, str, str, str, str]]:
    """Build ActivityFeed item tuples (optional 4th drill_url, 5th actor_html)."""
    rows: list[
        tuple[str, str, str] | tuple[str, str, str, str] | tuple[str, str, str, str, str]
    ] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        created = item.get("created_at")
        time_str = timeago(created) if created else ""
        actor = _activity_actor_label(item)
        actor_html = _activity_actor_html(item)
        description = _activity_description(item)
        if not description:
            # ActivityRow forbids empty description — skip rather than
            # crash the whole region (TR-8 comment_activity / Comment.content).
            continue
        drill = drill_by_id.get(id(item), "")
        if actor_html:
            rows.append((time_str, actor, description, drill, actor_html))
        elif drill:
            rows.append((time_str, actor, description, drill))
        else:
            rows.append((time_str, actor, description))
    return rows


class _BuildersTimelineMixin:
    """Mixin adding the 4 timeline-family `_build_*` methods to
    `WorkspaceRegionAdapter`. Same pattern as `_BuildersChartsMixin`.
    """

    def _build_timeline(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: timeline` regions render as a `Timeline` primitive
        matching `workspace/regions/timeline.html` byte-for-byte.

        Phase 4B.4 wave 2: extended to construct rich `TimelineEvent`
        instances carrying per-event date_label (already-formatted via
        `timeago` filter), title (from display_key), and secondary
        fields (per-column type-aware values, omitting the date and
        display_key columns).

        #1303 / cycle 1412: optional ``detail_url_template`` resolves to
        per-event ``drill_url`` (title hub link). Host request-time gates
        EDIT paths when UPDATE is denied (same as LIST/QUEUE/KANBAN).

        ctx shape:
            items: list of dicts (rows from the source entity)
            columns: list of `{key, label, type, ref_route}` dicts —
                same shape as LIST/DETAIL columns
            display_key: str — column key for the primary title
                (defaults to 'title' / 'name' / 'id' fallback)
            entity_name: str — fallback title when display_key value is None
            total: int — overflow indicator denominator
            empty_message: optional empty-state fallback
            detail_url_template: optional #1303 hub drill
        """
        from dazzle.render.filters import _timeago_filter

        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        columns = ctx.get("columns") or []
        display_key = str(ctx.get("display_key") or "")
        entity_name = str(ctx.get("entity_name") or "Event")
        detail_url_template = str(ctx.get("detail_url_template") or "")
        try:
            total = int(ctx.get("total") or 0)
        except (TypeError, ValueError):
            total = 0

        # Identify the when column (first date or datetime — oral #143).
        date_col_key = _timeline_when_col_key(columns)

        # #1303: resolve hub drills once (index-aligned with dict items).
        dict_items = [i for i in items if isinstance(i, dict)]
        row_links: tuple[str | None, ...] = (
            _resolve_row_links(dict_items, detail_url_template) if detail_url_template else ()
        )
        drill_by_id: dict[int, str] = {}
        for item, link in zip(dict_items, row_links, strict=False):
            if link:
                drill_by_id[id(item)] = str(link)

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
            primary = format_primary_display(primary, display_key, columns, item)
            # Secondary fields — every non-date, non-display column.
            fields: list[tuple[str, object]] = []
            for col in columns:
                if not isinstance(col, dict):
                    continue
                key = str(col.get("key") or "")
                if not key or key == display_key or key == date_col_key:
                    continue
                label = str(col.get("label") or key)
                # TIMELINE renders badges with `size='sm'` per legacy macro call.
                fields.append(
                    (
                        label,
                        _render_typed_value(item, col, badge_size="sm", host="timeline_meta"),
                    )
                )
            events.append(
                TimelineEvent(
                    title=str(primary),
                    date_label=date_label,
                    fields=tuple(fields),
                    drill_url=drill_by_id.get(id(item), ""),
                )
            )

        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No events yet."
        )
        body: Fragment = Timeline(events=tuple(events), total=total, empty_message=str(empty_msg))
        return _wrap_surface(title, "report", body)

    def _build_activity_feed(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: activity_feed` regions render as an ActivityFeed
        primitive — chronological feed with per-row dot, time line, and
        bubble carrying actor + description.

        Phase 4B.4 wave 1: dedicated builder (replaced prior alias to
        `_build_timeline`) so the typed-Fragment output matches
        `workspace/regions/activity_feed.html` byte-for-byte. Time
        strings are formatted via the legacy `timeago` filter so both
        paths produce the same relative-time labels.

        #1303 / cycle 1415: optional ``detail_url_template`` resolves to
        per-row ``drill_url`` (description hub link). Host request-time
        gates EDIT paths when UPDATE is denied (same as TIMELINE/LIST).

        ctx shape:
            items: list of entity/row dicts. Description is resolved from
              description | action | title | content | body | message | text |
              summary (first non-empty string). Actor from actor | user |
              author (string or nested display). created_at via timeago.
            detail_url_template: optional #1303 hub drill
        """
        from dazzle.render.filters import _timeago_filter

        title = _region_title(region)
        items: list[Any] = list(ctx.get("items", []) or [])
        empty_msg = _activity_empty_message(region, ctx)
        if not items:
            return _wrap_surface(title, "report", ActivityFeed(items=(), empty_message=empty_msg))

        dict_items = [i for i in items if isinstance(i, dict)]
        drill_by_id = _activity_drill_by_id(dict_items, str(ctx.get("detail_url_template") or ""))
        rows = _activity_feed_rows(items, drill_by_id, timeago=_timeago_filter)
        body: Fragment = (
            ActivityFeed(items=tuple(rows), empty_message=empty_msg)
            if rows
            else ActivityFeed(items=(), empty_message=empty_msg)
        )
        return _wrap_surface(title, "report", body)

    def _build_conversation(self, region: Any, ctx: RegionContext) -> Surface:
        """``display: conversation`` — MessageScroller of HM Message rows.

        Emitter path for **message-scroller** + **message** (+ nested Bubble).
        Live rows (``ctx["items"]``) map content/body to bubble text; actor
        keys + timestamps fill meta; ``is_internal`` (or ``from`` /
        ``direction`` in|out) picks orientation (internal notes → outbound).
        Static ``status_entries`` (``entries:``) dogfood the same spine when
        title is ``in``/``out``. Empty threads still mount scroller chrome
        with ``.dz-message-scroller__empty``.

        #1303 / cycle 1811: optional ``detail_url_template`` (from region
        ``action:``) resolves per-row ``drill_url`` so Message rows stamp
        open-discovery hub drills (activity/timeline parity). Host gates
        EDIT paths when UPDATE is denied.
        """
        title = _region_title(region)
        empty_msg = str(
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No conversation yet."
        )
        messages: list[Message] = []
        dict_items = [i for i in list(ctx.get("items", []) or []) if isinstance(i, dict)]
        drill_by_id = _activity_drill_by_id(dict_items, str(ctx.get("detail_url_template") or ""))

        for item in dict_items:
            text = _activity_description(item)
            if not text:
                continue
            orient = _conversation_orientation(item)
            author = (
                _activity_actor_label(item)
                or str(item.get("user_name") or item.get("name") or "").strip()
            )
            # Peer channel suffix on live trails: support portal/email/chat/phone
            # plus ops page_channel (bridge/slack/pager/status_page). Skip-set
            # defaults stay unsuffixed; clerk_stage_label humanizes the rest
            # (oral #181 — ``status_page`` not dumped as schema token).
            channel = conversation_channel_label(
                item.get("channel")
                or item.get("source_channel")
                or item.get("contact_channel")
                or item.get("page_channel")
                or item.get("notify_channel")
                or item.get("note_kind")
                or item.get("kind")
                or ""
            )
            if channel:
                author = f"{author} · {channel}" if author else channel
            time_label, time_dt = _conversation_time(item)
            media = str(item.get("media") or item.get("initials") or "").strip()
            messages.append(
                _conversation_message(
                    text,
                    orient,
                    author=author,
                    time_label=time_label,
                    time_datetime=time_dt,
                    media_label=media,
                    drill_url=drill_by_id.get(id(item), ""),
                    bubble_tone=_conversation_bubble_tone(item),
                )
            )

        if not messages:
            for raw in list(ctx.get("status_entries") or []):
                if not isinstance(raw, dict):
                    continue
                # Prefer body as speech; caption is author when body is set,
                # otherwise caption is legacy speech text (bubble dogfood).
                speech = str(raw.get("body") or raw.get("message") or "").strip()
                caption = str(raw.get("caption") or "").strip()
                if speech:
                    text = speech
                    author = str(raw.get("author") or caption or "").strip()
                else:
                    text = caption
                    author = str(raw.get("author") or "").strip()
                if not text:
                    continue
                tag = str(raw.get("title") or "").strip().lower()
                orient = tag if tag in ("in", "out") else "in"
                time_label = str(raw.get("time") or raw.get("time_label") or "").strip()
                time_dt = str(raw.get("datetime") or raw.get("time_datetime") or "").strip()
                media = str(raw.get("media") or "").strip()
                # Static dogfood entries may carry an explicit drill_url.
                static_drill = str(raw.get("drill_url") or "").strip()
                messages.append(
                    _conversation_message(
                        text,
                        orient,
                        author=author,
                        time_label=time_label,
                        time_datetime=time_dt,
                        media_label=media,
                        drill_url=static_drill,
                    )
                )

        # Region title doubles as scroller aria-label when present.
        scroller_label = title or "Conversation"
        body: Fragment = MessageScroller(
            messages=tuple(messages),
            label=scroller_label,
            empty_message=empty_msg,
        )
        return _wrap_surface(title, "report", body)

    def _build_day_timeline(self, region: Any, ctx: RegionContext) -> Surface:
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

    def _build_task_inbox(self, region: Any, ctx: RegionContext) -> Surface:
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
