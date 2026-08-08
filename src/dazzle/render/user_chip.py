"""User / person ref → Avatar hyperpart chip (default list/detail cell).

When a ``ref`` column points at a person-like entity (User, Contact, …)
or the loaded dict looks like a person, emit a ``.dz-avatar`` + name chip
instead of bare text. Contract root: ``.dz-avatar`` (HM avatar hyperpart).

When the loaded person dict carries preview meta (email / role /
department / title), the chip is composed as a guest inside HM
``.dz-hover-card`` so hover/focus shows a rich preview (no region verb).

Opt-out: column metadata ``avatar: false`` / ``person_chip: false`` /
``hover_card: false``.
"""

from __future__ import annotations

import html as _html_mod
import re
from typing import Any

from dazzle.render.filters import _ref_display_name
from dazzle.render.open_discovery import drill_open_discovery_attrs

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


def _ref_id_from_value(value: Any) -> str:
    """FK id for building a ref_route URL."""
    if isinstance(value, dict):
        return str(value.get("id") or "")
    if value in (None, "", "—"):
        return ""
    return str(value)


def ref_route_url(value: Any, col: dict[str, Any] | None = None) -> str:
    """Resolve ``col['ref_route']`` against *value*'s id, or empty if unusable."""
    col = col or {}
    ref_route = str(col.get("ref_route") or "")
    if not ref_route:
        return ""
    id_value = _ref_id_from_value(value)
    if not id_value:
        return ""
    if "{id}" in ref_route:
        return ref_route.replace("{id}", id_value)
    if ref_route.endswith("/"):
        return f"{ref_route}{id_value}"
    return f"{ref_route}/{id_value}"


def wrap_user_chip_link(chip_html: str, value: Any, col: dict[str, Any] | None = None) -> str:
    """Wrap a chip in ``a.dz-user-chip-link`` when ``ref_route`` resolves.

    List rows, detail cells, and workspace regions share this seam so person
    chips stay clickable wherever they appear (cycle 1364 parity with region).

    Cycle 1714 — stamp ``data-dz-open-*`` (queue/grid/ref-link parity) so agents
    attr-read person hops without scraping the avatar label alone. Prefer the
    column ``key`` as open-via (e.g. ``assigned_to``) when present.
    """
    if not chip_html or chip_html == "—":
        return chip_html
    url = ref_route_url(value, col)
    if not url:
        return chip_html
    href = _html_mod.escape(url, quote=True)
    via = str((col or {}).get("key") or "id").strip() or "id"
    open_attrs = drill_open_discovery_attrs(url, via=via)
    return (
        f'<a href="{href}" class="dz-user-chip-link" data-dz-user-chip-drill '
        f"{open_attrs}>{chip_html}</a>"
    )


_HOVER_DESC_KEYS = (
    "email",
    "role",
    "department",
    "title",
    "job_title",
    "status",
)


def _hover_preview_parts(value: Any) -> tuple[str, str] | None:
    """Return ``(title, description)`` when *value* has hover-card preview meta.

    Description is a middot-joined subset of email/role/department/title.
    Name-only dicts skip the wrap (no useful panel body).
    """
    if not isinstance(value, dict):
        return None
    name = _ref_display_name(value)
    if not name:
        return None
    bits: list[str] = []
    for key in _HOVER_DESC_KEYS:
        raw = value.get(key)
        if raw in (None, "", "—"):
            continue
        text = str(raw).strip()
        if text and text not in bits and text != name:
            bits.append(text)
    if not bits:
        return None
    return name, " · ".join(bits)


def wrap_hover_card_preview(
    trigger_html: str,
    *,
    title: str,
    description: str = "",
) -> str:
    """Compose guest: wrap *trigger_html* in dual-lock ``.dz-hover-card``.

    Trigger is host-owned (often a user chip or chip link) — we do **not**
    stamp ``.dz-hover-card__trigger`` on links so click navigation is not
    stolen by ``dz-hover-card.js`` ``preventDefault``. Fine pointers open
    via CSS ``:hover`` / ``:focus-within`` on the root.
    """
    if not trigger_html or trigger_html == "—":
        return trigger_html
    title_esc = _html_mod.escape(title, quote=False)
    desc_html = (
        f'<p class="dz-hover-card__description">{_html_mod.escape(description, quote=False)}</p>'
        if description
        else ""
    )
    return (
        f'<div class="dz-hover-card" data-dz-hover-card>'
        f"{trigger_html}"
        f'<div class="dz-hover-card__content" role="tooltip">'
        f'<p class="dz-hover-card__title">{title_esc}</p>'
        f"{desc_html}"
        f"</div></div>"
    )


def render_user_chip_html(
    value: Any,
    col: dict[str, Any] | None = None,
    *,
    density: str = "avatar_name",
) -> str:
    """HTML for a person ref: ``.dz-user-chip`` wrapping ``.dz-avatar`` + name.

    *density* (presentation matrix):

    * ``avatar_name`` — avatar + visible name (list/detail default)
    * ``avatar_only`` — avatar with ``title`` / ``aria-label`` only (queue meta)

    Returns empty string when *value* is empty; callers should not use this
    for non-person refs (use plain ``_ref_display_name`` instead).

    Does **not** wrap the chip in a navigation link — call
    :func:`wrap_user_chip_link` (or use :func:`render_user_chip_linked_html`)
    when ``ref_route`` should produce ``a.dz-user-chip-link``.
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
    if density == "avatar_only":
        # Queue meta density: identity *is* the avatar; name via a11y only.
        return (
            f'<span class="dz-user-chip dz-user-chip--avatar-only" '
            f'title="{name_attr}" aria-label="{name_attr}">'
            f"{avatar}"
            f"</span>"
        )
    return (
        f'<span class="dz-user-chip" title="{name_attr}">'
        f"{avatar}"
        f'<span class="dz-user-chip__name">{name_esc}</span>'
        f"</span>"
    )


def render_user_chip_linked_html(
    value: Any,
    col: dict[str, Any] | None = None,
    *,
    density: str = "avatar_name",
) -> str:
    """Chip HTML, link-wrapped when ``ref_route`` is present on *col*.

    Compose guest: when the person dict carries preview meta (email/role/…),
    wrap the chip in ``.dz-hover-card`` (HM hover-card hyperpart). Opt-out
    via column ``hover_card: false``. ``avatar_only`` density stays compact
    (queue meta) — no floating panel.
    """
    col = col or {}
    chip = render_user_chip_html(value, col, density=density)
    linked = wrap_user_chip_link(chip, value, col)
    if col.get("hover_card") is False or density == "avatar_only":
        return linked
    preview = _hover_preview_parts(value)
    if not preview:
        return linked
    title, description = preview
    return wrap_hover_card_preview(linked, title=title, description=description)
