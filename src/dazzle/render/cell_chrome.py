"""Leaf HTML for list/queue/grid cell chrome (swatches + media thumbs).

No fragment/region/ingest imports — kept free of the renderer cycle so
workspace builders can import at module top without deferred-import debt.
"""

from __future__ import annotations

import html as _html_mod
import re
from collections.abc import Iterable, Sequence
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


_UUID_CELL_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_FILE_EXT_RE = re.compile(r"\.[A-Za-z0-9]{2,5}$")
_HTTP_PREFIXES = ("http://", "https://")


def _header_norm(header: str) -> str:
    return (header or "").strip().lower().replace("_", " ")


def _looks_uuid_cell(raw: str) -> bool:
    text = (raw or "").strip()
    if _UUID_CELL_RE.match(text):
        return True
    compact = text.replace("-", "")
    return len(compact) >= 32 and all(c in "0123456789abcdefABCDEF" for c in compact)


def format_byte_size(value: Any) -> str:
    """Clerk-facing file size. Leftover junk stays put (oral #139)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value)
    if n < 0:
        return str(value)
    if n < 1000:
        return f"{n} B"
    if n < 1_000_000:
        kb = n / 1000
        return f"{kb:.0f} KB" if kb >= 10 else f"{kb:.1f} KB"
    mb = n / 1_000_000
    return f"{mb:.1f} MB" if mb < 10 else f"{mb:.0f} MB"


def _is_filename_header(header: str) -> bool:
    n = _header_norm(header)
    return n in {"filename", "file name", "original name", "original filename"} or n.endswith(
        " filename"
    )


def _is_name_header(header: str) -> bool:
    n = _header_norm(header)
    return _is_filename_header(header) or n in {"name", "title", "label"}


def _is_file_pointer_header(header: str) -> bool:
    return _header_norm(header) in {"file", "storage", "blob", "pointer", "path", "key"}


def _is_size_header(header: str) -> bool:
    n = _header_norm(header)
    return "size" in n or n.endswith("bytes") or n == "bytes"


def _is_uploader_header(header: str) -> bool:
    n = _header_norm(header)
    return any(token in n for token in ("upload", "author", "owner"))


def _is_storage_chrome(header: str, raw: str) -> bool:
    return _is_file_pointer_header(header) or _looks_uuid_cell(raw)


def _related_file_pairs(cells: Sequence[Any], headers: Sequence[Any]) -> list[tuple[str, str]]:
    header_list = [str(h or "") for h in (headers or ())]
    pairs: list[tuple[str, str]] = []
    for i, cell in enumerate(cells or ()):
        raw = "" if cell is None else str(cell).strip()
        if not raw or raw == "—":
            continue
        header = header_list[i] if i < len(header_list) else ""
        pairs.append((header, raw))
    return pairs


def _looks_like_filename_token(raw: str) -> bool:
    path = raw.split("?", 1)[0]
    if raw.lower().startswith(_HTTP_PREFIXES):
        return False
    return bool(_FILE_EXT_RE.search(path))


def _is_non_identity_meta(header: str, raw: str) -> bool:
    return (
        _is_storage_chrome(header, raw)
        or _is_size_header(header)
        or _is_uploader_header(header)
        or raw.isdigit()
    )


def _pick_related_file_name(pairs: list[tuple[str, str]]) -> str:
    for header, raw in pairs:
        if _is_storage_chrome(header, raw):
            continue
        if _is_filename_header(header) or _is_name_header(header):
            return raw
    for header, raw in pairs:
        if _is_storage_chrome(header, raw):
            continue
        if _looks_like_filename_token(raw):
            return raw
    for header, raw in pairs:
        if _is_non_identity_meta(header, raw):
            continue
        return raw
    for header, raw in pairs:
        if _is_filename_header(header) or _is_name_header(header):
            return raw
    return pairs[0][1] if pairs else ""


def _related_file_metas(pairs: list[tuple[str, str]], name: str, *, limit: int) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for header, raw in pairs:
        if raw == name or _is_storage_chrome(header, raw):
            continue
        if _is_size_header(header):
            ranked.append((0, format_byte_size(raw) if raw.isdigit() else raw))
        elif _is_uploader_header(header):
            ranked.append((2, raw))
        else:
            ranked.append((1, raw))
    ranked.sort(key=lambda item: item[0])
    return [raw for _, raw in ranked[:limit]]


def related_file_name_and_meta(
    cells: Sequence[Any],
    headers: Sequence[Any] = (),
    *,
    limit: int = 1,
) -> tuple[str, list[str]]:
    """Pick clerk file identity + meta for ``display: file_list``.

    Related file rows used to take the first two entity columns, so
    Attachment lists titled the uploader and hid ``filename`` (oral #139).
    Storage UUIDs stay off the name. Leftover junk stays put.
    """
    pairs = _related_file_pairs(cells, headers)
    name = _pick_related_file_name(pairs)
    return name, _related_file_metas(pairs, name, limit=limit)


_SEQUENCE_TITLE_KEYS = frozenset(
    {
        "attempt",
        "attempt_number",
        "quantity",
        "qty",
        "count",
        "version",
        "sequence",
        "seq",
        "index",
        "rank",
        "position",
        "ordinal",
        "line_number",
        "sort_order",
    }
)
_QUEUE_IDENTITY_HEADERS = frozenset(
    {
        "failure reason",
        "description",
        "title",
        "name",
        "headline",
        "notes",
        "body",
        "comment",
        "content",
        "summary",
        "label",
        "message",
        "subject",
        "scope summary",
        "suggested response",
    }
)
_QUEUE_IDENTITY_KEYS: tuple[str, ...] = (
    "title",
    "name",
    "subject",
    "headline",
    "notes",
    "body",
    "comment",
    "content",
    "summary",
    "label",
    "failure_reason",
    "message",
    "description",
    "scope_summary",
    "suggested_response",
)
_RISK_TITLE_KEYS = frozenset(
    {
        "severity",
        "priority",
        "category",
        "environment",
        "rating",
        "score",
        "quality_score",
        "confidence",
        "skill_level",
        "customer_tone",
    }
)


def _norm_title_key(key: str) -> str:
    return (key or "").strip().lower().replace(" ", "_")


def is_sequence_title_key(key: str) -> bool:
    """True when ``key`` is sequence/count chrome, not row identity (oral #140)."""
    k = _norm_title_key(key)
    return bool(k) and (
        k in _SEQUENCE_TITLE_KEYS or k.endswith(("_count", "_qty", "_rank", "_index"))
    )


def is_risk_title_key(key: str) -> bool:
    """True when ``key`` is severity/environment chrome, not row identity (oral #145)."""
    k = _norm_title_key(key)
    return bool(k) and (
        k in _RISK_TITLE_KEYS or k.endswith(("_severity", "_priority", "_score", "_rating"))
    )


def related_queue_columns_omit_identity(column_keys: Iterable[Any]) -> bool:
    """True when related ``columns:`` listed no clerk identity field."""
    keys = {str(k or "").strip().lower() for k in column_keys}
    return not bool(keys & {k.lower() for k in _QUEUE_IDENTITY_KEYS})


def related_queue_identity_from_record(record: Any) -> str:
    """First non-empty identity field on a related row dict.

    Device hub IssueReport queues listed ``severity, status, category``
    and hid ``description`` (oral #145). Leftover junk stays put.
    """
    if not isinstance(record, dict):
        return ""
    for key in _QUEUE_IDENTITY_KEYS:
        raw = record.get(key)
        if raw is None or isinstance(raw, dict):
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def _is_status_header(header: str) -> bool:
    n = _header_norm(header)
    return n in {"status", "state"} or n.endswith(" status")


def _is_date_header(header: str) -> bool:
    n = _header_norm(header)
    return n.endswith(" at") or "date" in n or n in {"created", "updated", "due", "when"}


def _is_reason_header(header: str) -> bool:
    """Bare ``reason`` is badge chrome; ``failure reason`` stays identity (oral #141)."""
    return _header_norm(header) == "reason"


def _is_queue_title_chrome(header: str, raw: str) -> bool:
    if _is_status_header(header) or _is_date_header(header) or _looks_uuid_cell(raw):
        return True
    if _is_reason_header(header):
        return True
    if is_risk_title_key(header):
        return True
    return is_sequence_title_key(header)


def _pick_related_queue_title(pairs: list[tuple[str, str]]) -> str:
    for header, raw in pairs:
        if _header_norm(header) in _QUEUE_IDENTITY_HEADERS:
            return raw
    for header, raw in pairs:
        if not _is_queue_title_chrome(header, raw):
            return raw
    return pairs[0][1] if pairs else ""


def related_queue_title_and_meta(
    cells: Sequence[Any],
    headers: Sequence[Any] = (),
    *,
    limit: int = 8,
) -> tuple[str, list[tuple[str, str]]]:
    """Pick clerk identity + labelled meta for ``display: queue`` related rows.

    Related payment queues used to take the first column, so invoice hub
    attempts titled ``1`` and hid ``card_declined`` (oral #140). Sequence
    numbers, status badges, dates, bare ``reason`` enums, and risk tokens
    (severity / environment) stay meta. Leftover junk stays put.
    """
    pairs = _related_file_pairs(cells, headers)
    title = _pick_related_queue_title(pairs)
    metas: list[tuple[str, str]] = []
    for header, raw in pairs:
        if raw == title or _looks_uuid_cell(raw):
            continue
        metas.append((header, raw))
        if len(metas) >= limit:
            break
    return title, metas
