"""User / person ref → Avatar hyperpart chip (default list/detail cell).

When a ``ref`` column points at a person-like entity (User, Contact, …)
or the loaded dict looks like a person, emit a ``.dz-avatar`` + name chip
instead of bare text. Contract root: ``.dz-avatar`` (HM avatar hyperpart).

Opt-out: column metadata ``avatar: false`` / ``person_chip: false``.
"""

from __future__ import annotations

import html as _html_mod
import re
from typing import Any

from dazzle.render.filters import _ref_display_name

# Target entity names that mean "show an avatar chip".
_PERSON_ENTITIES = frozenset(
    {
        "user",
        "person",
        "member",
        "employee",
        "contact",
        "staff",
        "assignee",
        "agent",
        "author",
        "owner",
        "profile",
        "account",
    }
)

# Field key heuristics when ref_entity is missing from the column dict.
_PERSON_FIELD_RE = re.compile(
    r"(assigned|assignee|author|owner|created_by|updated_by|reported_by|"
    r"submitted_by|requested_by|user|member|employee|contact|agent|actor|"
    r"reviewer|approver|manager)",
    re.I,
)
_AVATAR_URL_KEYS = ("avatar_url", "picture_url", "photo_url")
_NAME_KEYS = ("name", "first_name", "__display__")


def _col_ref_entity(col: dict[str, Any]) -> str:
    for key in ("ref_entity", "filter_ref_entity", "target_entity"):
        raw = col.get(key)
        if raw:
            return str(raw).strip()
    # Parse "/users/{id}" style routes.
    route = str(col.get("ref_route") or "")
    m = re.match(r"^/([a-z0-9_]+)/", route, re.I)
    if m:
        # API plural → rough singular
        plural = m.group(1).lower()
        if plural.endswith("ies"):
            return plural[:-3] + "y"
        if plural.endswith("s") and len(plural) > 1:
            return plural[:-1]
        return plural
    return ""


def _value_looks_like_person(value: dict[str, Any]) -> bool:
    if any(value.get(k) for k in _AVATAR_URL_KEYS):
        return True
    if value.get("email") and any(value.get(k) for k in _NAME_KEYS):
        return True
    return bool(value.get("first_name") or value.get("last_name") or value.get("forename"))


def looks_like_person_ref(value: Any, col: dict[str, Any] | None = None) -> bool:
    """True when this ref cell should render as an avatar chip."""
    col = col or {}
    if col.get("avatar") is False or col.get("person_chip") is False:
        return False
    entity = _col_ref_entity(col).lower()
    if entity in _PERSON_ENTITIES or entity.endswith("user"):
        return True
    if _PERSON_FIELD_RE.search(str(col.get("key") or "")):
        return True
    if not isinstance(value, dict):
        return False
    return _value_looks_like_person(value)


def initials_from_display(name: str) -> str:
    """Up to two initials from a display name."""
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        token = parts[0]
        return (token[:2] if len(token) > 1 else token[:1]).upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


def _hue_for_name(name: str) -> int:
    """Stable 0–359 hue so the same person keeps a consistent wash."""
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) % 360
    return h


def _avatar_markup(*, name: str, avatar_url: str, initials: str) -> str:
    if avatar_url:
        avatar_inner = f'<img src="{_html_mod.escape(avatar_url, quote=True)}" alt="" />'
        return f'<span class="dz-avatar" data-dz-size="sm" aria-hidden="true">{avatar_inner}</span>'
    hue = _hue_for_name(name)
    return (
        f'<span class="dz-avatar" data-dz-size="sm" data-dz-hue="{hue}" '
        f'style="--dz-avatar-hue:{hue}" '
        f'aria-hidden="true">{initials}</span>'
    )


def render_user_chip_html(value: Any, col: dict[str, Any] | None = None) -> str:
    """HTML for a person ref: ``.dz-user-chip`` wrapping ``.dz-avatar`` + name.

    Returns empty string when *value* is empty; callers should not use this
    for non-person refs (use plain ``_ref_display_name`` instead).
    """
    if value in (None, "", "—"):
        return "—"
    if not isinstance(value, dict):
        # Scalar UUID or name string — still chip if column metadata says person.
        if not looks_like_person_ref({"name": str(value)}, col or {}):
            return _html_mod.escape(str(value), quote=False)
        name = str(value)
        avatar_url = ""
    else:
        name = _ref_display_name(value)
        if not name:
            return "—"
        avatar_url = str(
            value.get("avatar_url") or value.get("picture_url") or value.get("photo_url") or ""
        )

    name_esc = _html_mod.escape(name, quote=False)
    name_attr = _html_mod.escape(name, quote=True)
    initials = _html_mod.escape(initials_from_display(name), quote=False)
    avatar = _avatar_markup(name=name, avatar_url=avatar_url, initials=initials)
    return (
        f'<span class="dz-user-chip" title="{name_attr}">'
        f"{avatar}"
        f'<span class="dz-user-chip__name">{name_esc}</span>'
        f"</span>"
    )
