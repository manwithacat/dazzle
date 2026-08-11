"""RelatedDisplayMode.conversation helpers (cycle 1893).

Maps pre-formatted related-tab cells → Message/Bubble rows so detail hubs
can render MessageScroller chrome without bloating `_render_tables.py`.
"""

from __future__ import annotations

from dazzle.render.fragment.primitives import Bubble, Message, RelatedTab

_CONV_TEXT_KEYS = frozenset(
    {
        "content",
        "body",
        "message",
        "text",
        "note",
        "comment",
        "description",
        "summary",
    }
)
_CONV_AUTHOR_KEYS = frozenset({"author", "user", "actor", "from", "sender", "writer"})
_CONV_ORIENT_KEYS = frozenset(
    {"is_internal", "internal", "direction", "from_", "outbound", "is_agent"}
)
# Peer support tools (Zendesk/Front/Intercom) surface customer tone on the
# trail — map these columns to Bubble danger when frustrated/urgent.
# Ops desks (PagerDuty/Opsgenie) use note_phase / timeline phase similarly.
_CONV_TONE_KEYS = frozenset(
    {
        "customer_tone",
        "tone",
        "sentiment",
        "customer_sentiment",
        "mood",
        # Escalation column (raised/critical) also drives Bubble danger.
        "escalation",
        "escalation_level",
        "escalated",
        # Ops timeline phase (cycle 1917) — escalate/critical → danger.
        "note_phase",
        "phase",
        "timeline_phase",
        "incident_phase",
    }
)
# Inbound channel (portal/email/chat/phone) — append to author for trail label.
# Ops page_channel (bridge/slack/pager/status_page) uses the same suffix path.
_CONV_CHANNEL_KEYS = frozenset(
    {
        "channel",
        "source_channel",
        "contact_channel",
        "via",
        "origin",
        "page_channel",
        "notify_channel",
        "page",
    }
)
_CONV_ORIENT_OUT = frozenset({"yes", "true", "1", "out", "outbound", "internal", "agent"})
_CONV_ORIENT_IN = frozenset({"no", "false", "0", "in", "inbound", "customer", "external"})
_CONV_TONE_DANGER = frozenset(
    {
        "frustrated",
        "urgent",
        "angry",
        "escalated",
        "raised",
        "critical",
        "danger",
        "negative",
        "upset",
        # Ops timeline lean-in phases (PagerDuty bridge trail).
        "escalate",
        "mitigate",
    }
)
# Channel values that are noise when default — skip author suffix.
# ``portal`` is the product default inbound path (not a lean-in signal).
# ``bridge`` is the ops default page path (parity with portal skip).
_CONV_CHANNEL_SKIP = frozenset({"", "none", "unknown", "n/a", "na", "portal", "bridge"})


def _header_key(header: str) -> str:
    return str(header or "").strip().lower().replace(" ", "_").replace("-", "_")


def conversation_roles(headers: tuple[str, ...]) -> list[str]:
    """Map related-tab header labels to conversation cell roles.

    Roles: ``text`` (bubble body), ``author``, ``time``, ``orient``
    (inbound/outbound from is_internal / direction), ``tone`` (customer
    sentiment / escalation → Bubble danger), ``channel`` (path suffix on
    author). Unknown headers stay empty — is_internal never becomes bubble
    text.
    """
    roles: list[str] = []
    for h in headers:
        key = _header_key(h)
        if key in _CONV_TEXT_KEYS:
            roles.append("text")
        elif key in _CONV_AUTHOR_KEYS:
            roles.append("author")
        elif (
            "time" in key
            or "date" in key
            or key.startswith("created")
            or key.startswith("sent")
            or key.startswith("updated")
        ):
            roles.append("time")
        elif key in _CONV_ORIENT_KEYS:
            roles.append("orient")
        elif key in _CONV_TONE_KEYS:
            roles.append("tone")
        elif key in _CONV_CHANNEL_KEYS:
            roles.append("channel")
        else:
            roles.append("")
    if "text" not in roles:
        for i, role in enumerate(roles):
            if role == "":
                roles[i] = "text"
                break
    return roles


def conversation_orient(raw: str) -> str:
    """Yes/true/out/internal → outbound Message chrome; else inbound."""
    s = str(raw or "").strip().lower()
    if s in _CONV_ORIENT_OUT:
        return "out"
    if s in _CONV_ORIENT_IN:
        return "in"
    return "in"


def conversation_bubble_tone(raw: str) -> str:
    """Map customer tone / escalation cells → Bubble tone (``\"\"`` | ``danger``)."""
    s = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    if s in _CONV_TONE_DANGER:
        return "danger"
    return ""


def conversation_channel_label(raw: str) -> str:
    """Normalize inbound channel for author suffix (empty when noise/default)."""
    s = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    if s in _CONV_CHANNEL_SKIP:
        return ""
    return s


def conversation_time_label(raw: str) -> tuple[str, str]:
    """Short clock label + full datetime attr from a pre-formatted cell."""
    text = str(raw or "").strip()
    if not text:
        return "", ""
    sep = "T" if "T" in text else (" " if " " in text and len(text) >= 16 else "")
    if not sep:
        return text, text
    clock = text.split(sep, 1)[1]
    clock = clock.replace("Z", "").split("+", 1)[0].split("-", 1)[0]
    label = clock[:5] if len(clock) >= 5 else clock
    return label, text


def conversation_initials(author: str) -> str:
    words = [w for w in author.strip().split() if w]
    if not words:
        return ""
    return "".join(w[0] for w in words[:2]).upper()


def _apply_conversation_role(
    role: str,
    val: str,
    text: str,
    author: str,
    time_raw: str,
    orient: str,
    bubble_tone: str,
    channel: str,
) -> tuple[str, str, str, str, str, str]:
    """Apply one non-empty cell to conversation field slots (first-write wins)."""
    if role == "text":
        return (val if not text else text), author, time_raw, orient, bubble_tone, channel
    if role == "author":
        return text, (val if not author else author), time_raw, orient, bubble_tone, channel
    if role == "time":
        return text, author, (val if not time_raw else time_raw), orient, bubble_tone, channel
    if role == "orient":
        return text, author, time_raw, conversation_orient(val), bubble_tone, channel
    if role == "tone":
        return (
            text,
            author,
            time_raw,
            orient,
            (conversation_bubble_tone(val) if not bubble_tone else bubble_tone),
            channel,
        )
    if role == "channel":
        return (
            text,
            author,
            time_raw,
            orient,
            bubble_tone,
            (conversation_channel_label(val) if not channel else channel),
        )
    return text, author, time_raw, orient, bubble_tone, channel


def conversation_row_fields(
    row: tuple[str, ...], roles: list[str]
) -> tuple[str, str, str, str, str] | None:
    """Extract (text, author, time_raw, orient, bubble_tone) from one related row.

    Returns None when the row has no speech text (skip empty bubbles).
    Channel is folded into the author label (``Name · chat``) when present.
    """
    text = ""
    author = ""
    time_raw = ""
    orient = "in"
    bubble_tone = ""
    channel = ""
    for j, cell in enumerate(row):
        role = roles[j] if j < len(roles) else ""
        val = str(cell or "").strip()
        if not val:
            continue
        text, author, time_raw, orient, bubble_tone, channel = _apply_conversation_role(
            role, val, text, author, time_raw, orient, bubble_tone, channel
        )
    if not text:
        return None
    if not author:
        author = "Agent" if orient == "out" else "Customer"
    if channel:
        author = f"{author} · {channel}"
    return text, author, time_raw, orient, bubble_tone


def related_conversation_messages(t: RelatedTab) -> tuple[Message, ...]:
    """Build Message rows from pre-formatted related-tab cells."""
    roles = conversation_roles(t.headers)
    messages: list[Message] = []
    for i, row in enumerate(t.rows):
        fields = conversation_row_fields(row, roles)
        if fields is None:
            continue
        text, author, time_raw, orient, bubble_tone = fields
        time_label, time_dt = conversation_time_label(time_raw)
        drill = t.row_drill[i] if t.row_drill and i < len(t.row_drill) else ""
        # Initials from bare author (strip channel suffix for media chip).
        author_base = author.split(" · ", 1)[0] if " · " in author else author
        messages.append(
            Message(
                bubble=Bubble(
                    text=text,
                    from_=orient,  # type: ignore[arg-type]
                    tone=bubble_tone or "",  # type: ignore[arg-type]
                ),
                author=author,
                time_label=time_label,
                time_datetime=time_dt,
                media_label=conversation_initials(author_base),
                from_=orient,  # type: ignore[arg-type]
                drill_url=(drill or "").strip(),
            )
        )
    return tuple(messages)
