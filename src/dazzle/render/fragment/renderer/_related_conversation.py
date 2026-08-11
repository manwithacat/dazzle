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
_CONV_TONE_KEYS = frozenset(
    {
        "customer_tone",
        "tone",
        "sentiment",
        "customer_sentiment",
        "mood",
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
        "danger",
        "negative",
        "upset",
    }
)


def _header_key(header: str) -> str:
    return str(header or "").strip().lower().replace(" ", "_").replace("-", "_")


def conversation_roles(headers: tuple[str, ...]) -> list[str]:
    """Map related-tab header labels to conversation cell roles.

    Roles: ``text`` (bubble body), ``author``, ``time``, ``orient``
    (inbound/outbound from is_internal / direction), ``tone`` (customer
    sentiment → Bubble danger). Unknown headers stay empty — is_internal
    never becomes bubble text.
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
    """Map customer tone / sentiment cells → Bubble tone (``\"\"`` | ``danger``)."""
    s = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    if s in _CONV_TONE_DANGER:
        return "danger"
    return ""


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
) -> tuple[str, str, str, str, str]:
    """Apply one non-empty cell to conversation field slots (first-write wins)."""
    if role == "text":
        return (val if not text else text), author, time_raw, orient, bubble_tone
    if role == "author":
        return text, (val if not author else author), time_raw, orient, bubble_tone
    if role == "time":
        return text, author, (val if not time_raw else time_raw), orient, bubble_tone
    if role == "orient":
        return text, author, time_raw, conversation_orient(val), bubble_tone
    if role == "tone":
        return (
            text,
            author,
            time_raw,
            orient,
            (conversation_bubble_tone(val) if not bubble_tone else bubble_tone),
        )
    return text, author, time_raw, orient, bubble_tone


def conversation_row_fields(
    row: tuple[str, ...], roles: list[str]
) -> tuple[str, str, str, str, str] | None:
    """Extract (text, author, time_raw, orient, bubble_tone) from one related row.

    Returns None when the row has no speech text (skip empty bubbles).
    """
    text = ""
    author = ""
    time_raw = ""
    orient = "in"
    bubble_tone = ""
    for j, cell in enumerate(row):
        role = roles[j] if j < len(roles) else ""
        val = str(cell or "").strip()
        if not val:
            continue
        text, author, time_raw, orient, bubble_tone = _apply_conversation_role(
            role, val, text, author, time_raw, orient, bubble_tone
        )
    if not text:
        return None
    if not author:
        author = "Agent" if orient == "out" else "Customer"
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
                media_label=conversation_initials(author),
                from_=orient,  # type: ignore[arg-type]
                drill_url=(drill or "").strip(),
            )
        )
    return tuple(messages)
