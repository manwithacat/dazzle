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


def open_hop_label(entity_label: str, via_field: str = "") -> str:
    """User-facing hop phrase: ``Open Task`` / ``Open User via assigned to``.

    Cycle 1719 — ``via=create`` / ``via=new`` yields ``Create {Entity}`` for
    list/empty/related create CTAs (same attr grammar as VIEW hops).

    Cycle 1721 — ``via=edit`` yields ``Edit {Entity}`` for row pencil actions.
    """
    ent = (entity_label or "Related").strip() or "Related"
    via = (via_field or "").strip()
    if not via or via == "id":
        return f"Open {ent}"
    if via.casefold() in ("create", "new"):
        return f"Create {ent}"
    if via.casefold() == "edit":
        return f"Edit {ent}"
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
