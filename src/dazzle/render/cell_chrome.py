"""Leaf HTML for list/queue/grid cell chrome (swatches + media thumbs).

No fragment/region/ingest imports — kept free of the renderer cycle so
workspace builders can import at module top without deferred-import debt.
"""

from __future__ import annotations

import html as _html_mod
import re
from collections.abc import Sequence
from typing import Any

# #1626 R5 / P0-8 — palette chips on brand desks (list + queue + card).
_HEX_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")

# Goal B media: allow only https image-like URLs (no javascript:/data:).
_MEDIA_THUMB_HOST_ALLOW = frozenset(
    {
        "placehold.co",
        "images.unsplash.com",
        "cdn.dazzle.dev",
        "raw.githubusercontent.com",
    }
)
_MEDIA_THUMB_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif")
_MEDIA_THUMB_BAD_CHARS = frozenset(" \n\r\t\"'<>")


def _render_color_swatch_html(value: Any) -> str:
    """#1626 R5 — compact palette swatch + hex for list/queue/card cells."""
    raw = "" if value is None else str(value).strip()
    if not raw or raw == "—":
        return "—"
    # Accept #RGB / #RRGGBB only; refuse free-text so we never inject CSS.
    if not _HEX_COLOR_RE.fullmatch(raw):
        return _html_mod.escape(raw, quote=False)
    hex_esc = _html_mod.escape(raw, quote=False)
    hex_attr = _html_mod.escape(raw, quote=True)
    return (
        f'<span class="dz-color-swatch" data-dz-color-swatch '
        f'style="background-color: {hex_attr}" title="{hex_attr}" '
        f'aria-label="Colour {hex_attr}"></span>'
        f'<span class="dz-color-swatch-hex">{hex_esc}</span>'
    )


def _media_host_and_path(raw: str) -> tuple[str, str] | None:
    """Split ``https://host/path?q`` → (host, path_q) or None if invalid."""
    if not raw.lower().startswith("https://"):
        return None
    rest = raw[8:]
    host, _, path_q = rest.partition("/")
    host = host.split("@")[-1].split(":")[0].lower()
    if not host or ".." in path_q or "\\" in path_q:
        return None
    return host, path_q


def _media_host_path_allowed(host: str, path_q: str) -> bool:
    """True when host is allow-listed and path looks like an image resource."""
    # placehold.co often uses ``/png`` without a file extension.
    if host == "placehold.co" or host.endswith(".placehold.co"):
        return True
    if host not in _MEDIA_THUMB_HOST_ALLOW:
        return False
    path_only = path_q.split("?", 1)[0].lower()
    return path_only.endswith(_MEDIA_THUMB_EXT) or "/png" in path_only or "/jpeg" in path_only


def _safe_media_image_url(value: Any) -> str | None:
    """Return a sanitised https image URL or None if unsafe/non-image."""
    raw = "" if value is None else str(value).strip()
    if not raw or raw == "—" or len(raw) > 500:
        return None
    if any(c in raw for c in _MEDIA_THUMB_BAD_CHARS):
        return None
    parts = _media_host_and_path(raw)
    if parts is None:
        return None
    host, path_q = parts
    if not _media_host_path_allowed(host, path_q):
        return None
    return raw


def _sanitize_media_alt(alt: str) -> str:
    """Prefer human alt text over schema field labels (cycle 1951 agency_lead).

    Callers often pass column labels (``Photo Url``, ``logo_url``). Those
    read as admin-schema dump when emitted as ``alt=`` — use a generic
    ``Photo`` / ``Preview`` instead. Real titles (person name, brand) pass through.
    """
    a = (alt or "").strip()
    if not a:
        return "Preview"
    compact = a.lower().replace("_", " ").replace("-", " ")
    compact = " ".join(compact.split())
    if compact.endswith(" url") or compact in {
        "photo",
        "image",
        "logo",
        "avatar",
        "thumbnail",
        "preview",
        "picture",
        "headshot",
        "media",
    }:
        return "Photo"
    return a


def _render_media_thumb_html(value: Any, *, alt: str = "") -> str:
    """Post-5.8 media depth — compact image thumb for logo/preview URL cells.

    Mounts HM dual-lock ``.dz-aspect-ratio`` (1/1) so field/media compose
    exercises the aspect-ratio hyperpart spine (not a bare fixed-size img).
    """
    url = _safe_media_image_url(value)
    if not url:
        raw = "" if value is None else str(value).strip()
        if not raw or raw == "—":
            return "—"
        return _html_mod.escape(raw, quote=False)
    src = _html_mod.escape(url, quote=True)
    alt_esc = _html_mod.escape(_sanitize_media_alt(alt), quote=True)
    # Square media frame: width 3rem; child fills via .dz-aspect-ratio > * CSS.
    return (
        f'<div class="dz-aspect-ratio" data-dz-ratio="1/1" data-dz-media-frame '
        f'style="width: 3rem;">'
        f'<img class="dz-media-thumb" data-dz-media-thumb src="{src}" '
        f'alt="{alt_esc}" loading="lazy" decoding="async" />'
        f"</div>"
    )


def related_card_media_and_text(cells: Sequence[Any], *, limit: int = 3) -> tuple[str, list[str]]:
    """Split related status_card cells into (thumb_html, text slots).

    A safe https image URL is a preview thumb — not the card title.
    Campaign hubs used to dump ``preview_url`` as primary text (oral #135).
    Leftover junk stays in the text slots; do not invent a thumb.
    """
    media_url = ""
    texts: list[str] = []
    for cell in cells:
        raw = "" if cell is None else str(cell).strip()
        if not raw or raw == "—":
            continue
        if not media_url and _safe_media_image_url(raw):
            media_url = raw
            continue
        texts.append(raw)
        if len(texts) >= limit:
            break
    if not media_url:
        texts = []
        for cell in cells:
            raw = "" if cell is None else str(cell).strip()
            if raw and raw != "—":
                texts.append(raw)
            if len(texts) >= limit:
                break
        return "", texts
    alt = texts[0] if texts else ""
    return _render_media_thumb_html(media_url, alt=alt), texts[:limit]
