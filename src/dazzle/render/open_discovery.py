"""Agent open-hop discovery attrs for drill / ref links (cycle 1714 leaf).

Lives under ``dazzle.render`` (not ``fragment``) so person-chip and other
pre-fragment call sites can stamp ``data-dz-open-*`` without importing the
fragment package (which would cycle through renderer → ingest → region).

Sole assembly for single-hop open discovery attrs. Multi-hop list-row chains
remain in ``fragment.renderer._data_row`` / ``region._row_links``.
"""

from __future__ import annotations

import html as _html


def entity_label_from_detail_url(url: str) -> str:
    """Human label for a resolved app path (detail or list).

    ``/app/user/u-9`` → ``User``; ``/app/payment-attempt/x`` → ``Payment Attempt``.
    Mirrors ``region._row_links.entity_label_from_detail_url`` (kept in sync).
    """
    if not url or str(url).strip() in ("", "#"):
        return "Related"
    path = str(url).split("?", 1)[0].strip("/")
    segs = [s for s in path.split("/") if s]
    if not segs:
        return "Related"
    if segs[0] == "app":
        if len(segs) < 2:
            return "Related"
        slug = segs[1]
    elif len(segs) >= 2:
        slug = segs[-2]
    else:
        slug = segs[0]
    words = [w for w in slug.replace("_", "-").split("-") if w]
    if not words:
        return "Related"
    return " ".join(w[:1].upper() + w[1:] for w in words)


# Special via tokens → phrase verb (keeps open_hop_label CC low).
_OPEN_HOP_VIA_VERB: dict[str, str] = {
    "create": "Create",
    "new": "Create",
    "edit": "Edit",
    "confirm": "Confirm",
    "revoke": "Revoke",
    "re-enable": "Re-enable",
    "reenable": "Re-enable",
}


def open_hop_label(entity_label: str, via_field: str = "") -> str:
    """User-facing hop phrase: ``Open Task`` / ``Open User via assigned to``.

    Cycle 1719 — ``via=create`` / ``via=new`` yields ``Create {Entity}`` for
    list/empty/related create CTAs (same attr grammar as VIEW hops).

    Cycle 1721 — ``via=edit`` yields ``Edit {Entity}`` for row pencil actions.

    Cycle 1805 — ``via=confirm`` / ``via=revoke`` / ``via=re-enable`` for
    ConfirmGate primary / revoke / re-enable action anchors.
    """
    ent = (entity_label or "Related").strip() or "Related"
    via = (via_field or "").strip()
    if not via or via == "id":
        return f"Open {ent}"
    verb = _OPEN_HOP_VIA_VERB.get(via.casefold())
    if verb is not None:
        return f"{verb} {ent}"
    words = [w for w in via.replace("-", "_").split("_") if w]
    if not words:
        return f"Open {ent}"
    field_phrase = " ".join(w.lower() for w in words)
    if field_phrase.casefold() == ent.casefold():
        return f"Open {ent}"
    return f"Open {ent} via {field_phrase}"


def _app_action_open_attrs(href: str, *, marker: str, via: str) -> str:
    """Shared /app/ open-discovery stamp for create/edit (and similar) actions.

    Cycle 1722 — collapse create_cta_open_attrs / edit_action_open_attrs clone
    pair (clone ratchet red main after 1721). Marker + via differ; path gate
    and ``drill_open_discovery_attrs`` assembly are identical.
    """
    url = (href or "").strip()
    if not url or url == "#" or url.startswith("#"):
        return ""
    path = url.split("?", 1)[0].strip()
    segs = [s for s in path.strip("/").split("/") if s]
    if not (path.startswith("/app/") and len(segs) >= 2 and segs[0] == "app"):
        return ""
    return f"{marker} {drill_open_discovery_attrs(url, via=via)}"


def create_cta_open_attrs(href: str) -> str:
    """Open-discovery attrs for create CTAs (list header, empty, related).

    Cycle 1719 — agents attr-read create hops without scraping the label.
    Marker ``data-dz-create-drill`` + ``data-dz-open-*`` with ``via=create``.
    Skips empty / fragment-only / non-app paths (parity with action cards).
    """
    return _app_action_open_attrs(href, marker="data-dz-create-drill", via="create")


def create_cta_open_attr_suffix(href: str) -> str:
    """Leading-space open attrs for appending onto an ``<a …>`` tag, or ``""``."""
    extra = create_cta_open_attrs(href)
    return f" {extra}" if extra else ""


def edit_action_open_attrs(href: str) -> str:
    """Open-discovery attrs for row edit pencil actions.

    Cycle 1721 — agents attr-read UPDATE hops without scraping the pencil
    icon / ``data-dazzle-action``. Marker ``data-dz-update-drill`` (not
    ``data-dz-edit-*`` — that prefix is the HM grid-edit sole-emitter family
    under ``ingest/``) + ``data-dz-open-*`` with ``via=edit``. Skips empty /
    fragment-only / non-app paths (parity with create CTAs).
    """
    return _app_action_open_attrs(href, marker="data-dz-update-drill", via="edit")


def edit_action_open_attr_suffix(href: str) -> str:
    """Leading-space open attrs for appending onto an edit ``<a …>`` tag, or ``""``."""
    extra = edit_action_open_attrs(href)
    return f" {extra}" if extra else ""


def confirm_action_open_attrs(href: str, *, via: str = "confirm") -> str:
    """Open-discovery attrs for ConfirmGate action anchors.

    Cycle 1805 — agents attr-read confirm / revoke / re-enable hops without
    scraping button copy. Markers:

    * ``data-dz-confirm-drill`` — primary commit / re-enable (via=confirm|re-enable)
    * ``data-dz-revoke-drill`` — live-state revoke (via=revoke)

    Skips empty / fragment-only / non-app paths (parity with create/edit).
    """
    via_norm = (via or "confirm").strip() or "confirm"
    via_cf = via_norm.casefold()
    if via_cf == "revoke":
        marker = "data-dz-revoke-drill"
    else:
        marker = "data-dz-confirm-drill"
        if via_cf in ("reenable",):
            via_norm = "re-enable"
    return _app_action_open_attrs(href, marker=marker, via=via_norm)


def confirm_action_open_attr_suffix(href: str, *, via: str = "confirm") -> str:
    """Leading-space open attrs for ConfirmGate ``<a …>`` tags, or ``""``."""
    extra = confirm_action_open_attrs(href, via=via)
    return f" {extra}" if extra else ""


def _app_link_open_kind(path: str, action: str, segs: list[str]) -> str:
    """Classify an ``/app/…`` Link as ``edit`` / ``create`` / ``view``."""
    path_norm = path.rstrip("/")
    action_cf = (action or "").casefold()
    if path_norm.endswith("/edit") or action_cf.endswith(".edit"):
        return "edit"
    leaf = segs[-1].casefold() if segs else ""
    if leaf in ("create", "new") or action_cf.endswith(".create"):
        return "create"
    if path_norm.endswith("/create") or path_norm.endswith("/new"):
        return "create"
    return "view"


def link_open_discovery_attr_suffix(href: str, *, data_action: str = "") -> str:
    """Open-discovery attr suffix for typed ``Link`` emission.

    Cycle 1723 — detail chrome Edit / CREATE primary Links must not look
    like VIEW ref hops. Classification:

    * ``nav.*`` actions → no open stamp (shell/nav)
    * path ends ``/edit`` or action ends ``.edit`` → update-drill
    * create/new path or action ends ``.create`` → create-drill
    * other ``/app/<entity>…`` → ref-link drill (VIEW hop)
    * non-app / empty → ``""``
    """
    url = (href or "").strip()
    if not url or url == "#" or url.startswith("#"):
        return ""
    action = (data_action or "").strip()
    if action.casefold().startswith("nav."):
        return ""
    path = url.split("?", 1)[0].strip()
    segs = [s for s in path.strip("/").split("/") if s]
    if not path.startswith("/app/") or len(segs) < 2 or segs[0] != "app":
        return ""
    kind = _app_link_open_kind(path, action, segs)
    if kind == "edit":
        return edit_action_open_attr_suffix(url)
    if kind == "create":
        return create_cta_open_attr_suffix(url)
    return f" data-dz-ref-link-drill {drill_open_discovery_attrs(url)}"


def _view_drill_open_attr_suffix(href: str, *, marker: str) -> str:
    """VIEW-style open-discovery suffix for a chrome surface (marker varies).

    Cycle 1823 — collapse breadcrumb / command clone pair (clone ratchet).
    Cycle 1824 — FTS search_box result hops share the same helper
    (``data-dz-search-drill``). Marker differs per surface; path gate and
    ``drill_open_discovery_attrs`` assembly are identical. Skips Home
    (``/`` / bare ``/app``), fragment-only, and non-app paths.
    """
    url = (href or "").strip()
    if not url or url == "#" or url.startswith("#"):
        return ""
    path = url.split("?", 1)[0].strip()
    segs = [s for s in path.strip("/").split("/") if s]
    if not path.startswith("/app/") or len(segs) < 2 or segs[0] != "app":
        return ""
    return f" {marker} {drill_open_discovery_attrs(url)}"


def breadcrumb_open_attr_suffix(href: str) -> str:
    """Open-discovery attr suffix for breadcrumb trail hops.

    Cycle 1806 — agents attr-read parent list/detail crumbs without scraping
    labels. Marker ``data-dz-breadcrumb-drill`` + VIEW-style ``data-dz-open-*``
    (``via=id`` → ``Open {Entity}``). Skips Home (``/`` / bare ``/app``),
    fragment-only, and non-app paths — same gate as ref-link VIEW hops.
    """
    return _view_drill_open_attr_suffix(href, marker="data-dz-breadcrumb-drill")


def command_open_attr_suffix(href: str) -> str:
    """Open-discovery attr suffix for command-palette result hops.

    Cycle 1823 — agents attr-read ⌘K / palette destinations without scraping
    labels. Marker ``data-dz-command-drill`` + VIEW-style ``data-dz-open-*``
    (``via=id`` → ``Open {Entity}``). Same path gate as breadcrumb / ref-link
    VIEW hops: requires ``/app/<entity>…``; skips bare ``/app``, fragment-only,
    and non-app paths.
    """
    return _view_drill_open_attr_suffix(href, marker="data-dz-command-drill")


def search_open_attr_suffix(href: str) -> str:
    """Open-discovery attr suffix for FTS ``search_box`` result hops.

    Cycle 1824 — agents attr-read ``display: search_box`` result destinations
    without scraping titles. Marker ``data-dz-search-drill`` + VIEW-style
    ``data-dz-open-*`` (``via=id`` → ``Open {Entity}``). Same path gate as
    command / breadcrumb VIEW hops.
    """
    return _view_drill_open_attr_suffix(href, marker="data-dz-search-drill")


def hub_open_discovery_attrs(drill_url: str, *, via: str = "id") -> tuple[str, str]:
    """Primary dual-open attrs (link attrs, host chain attrs) for one hop."""
    via_field = (via or "id").strip() or "id"
    via_attr = _html.escape(via_field, quote=True)
    href = _html.escape(drill_url, quote=True)
    ent = entity_label_from_detail_url(drill_url)
    ent_attr = _html.escape(ent, quote=True)
    phrase = open_hop_label(ent, via_field)
    phrase_attr = _html.escape(phrase, quote=True)
    aria = _html.escape(phrase, quote=True)
    link_attrs = (
        f'data-dz-open-via="{via_attr}" '
        f'data-dz-open-entity="{ent_attr}" '
        f'data-dz-open-role="primary" '
        f'data-dz-open-hop="0" '
        f'data-dz-open-label="{phrase_attr}" '
        f'aria-label="{aria}" '
        f'title="{phrase_attr}" '
    )
    host_attrs = (
        f' data-dz-open-chain="{href}"'
        f' data-dz-open-chain-via="{via_attr}"'
        f' data-dz-open-hops="1"'
        f' data-dz-open-chain-label="{phrase_attr}"'
        f' data-dz-open-chain-entity="{ent_attr}"'
    )
    return link_attrs, host_attrs


def drill_open_discovery_attrs(drill_url: str, *, via: str = "id") -> str:
    """Single-anchor open discovery (link + chain attrs concatenated)."""
    link_attrs, host_attrs = hub_open_discovery_attrs(drill_url, via=via)
    return (link_attrs + host_attrs).strip()
