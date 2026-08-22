"""Cross-family helpers shared across every region-adapter builder.

These four helpers are used by ≥2 builder families AND in the case of
`_render_status_badge_html` are imported externally (by
`dazzle.render.fragment.renderer`). Extracting them here means each
follow-up builder-family file (`_builders_cards.py`, `_builders_charts.py`,
etc.) imports from a single, stable surface — no circular dependencies on
the dispatcher and no need to import sibling family modules.

Public-API note: `_render_status_badge_html` is re-exported by
`region_adapter/__init__.py` so the `from
dazzle.render.fragment.region import _render_status_badge_html`
call sites in `renderer.py` keep working unchanged.

See issue #1065 for the full decomposition plan.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from html import escape as _html_escape
from typing import Any

from dazzle.render.cell_chrome import (
    _render_color_swatch_html,
    _render_media_thumb_html,
)
from dazzle.render.channel_cell import clerk_email_cell_html, clerk_phone_cell_html
from dazzle.render.file_cell import clerk_file_cell_display
from dazzle.render.filters import _LEFTOVER_STAGE_TOKENS, clerk_percent_points_display
from dazzle.render.fragment import (
    URL,
    Fragment,
    Heading,
    Link,
    RawHTML,
    Region,
    Surface,
)
from dazzle.render.fragment.format_cell import ResolvedFormat, format_cell
from dazzle.render.rating_cell import clerk_rating_cell_html
from dazzle.render.tags_cell import clerk_tags_cell_html
from dazzle.render.user_chip import looks_like_person_ref

# Defensive ISO / Postgres timestamptz leak detector (parity with _data_row.py).
_ISO_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def format_minor_money_display(value: Any, *, currency_code: str = "GBP") -> str:
    """Clerk-facing money for expanded ``*_minor`` storage (oral #136).

    Leftover junk stays put (``format_cell`` / ``_currency``).
    """
    text = format_cell(value, "currency", currency_code=currency_code or "GBP")
    return text or ("" if value is None else str(value))


def _minor_currency_code(col: dict[str, Any], item: dict[str, Any] | None = None) -> str:
    """ISO code from the column, else the sibling ``{name}_currency`` cell."""
    code = str(col.get("currency_code") or "")
    key = str(col.get("key") or "")
    if not code and key.endswith("_minor") and item is not None:
        code = str(item.get(f"{key[:-6]}_currency") or "")
    return code or "GBP"


def _display_col_for_key(columns: Any, display_key: str) -> dict[str, Any] | None:
    return next(
        (
            c
            for c in (columns or [])
            if isinstance(c, dict) and str(c.get("key") or "") == display_key
        ),
        None,
    )


def format_primary_if_minor(
    primary: Any,
    display_key: str,
    columns: Any,
    item: dict[str, Any],
) -> Any:
    """Format queue/timeline titles when the primary column is ``*_minor``."""
    if not display_key.endswith("_minor"):
        return primary
    display_col = _display_col_for_key(columns, display_key)
    return format_minor_money_display(
        primary,
        currency_code=_minor_currency_code(display_col or {}, item),
    )


def format_primary_display(
    primary: Any,
    display_key: str,
    columns: Any,
    item: dict[str, Any],
) -> Any:
    """Clerk-facing primary title: money minors + badge/enum tokens.

    ``*_minor`` → sterling (oral #136). Badge ``debugging`` → ``Debugging``
    (oral #138). Leftover junk stays put (``format_cell``).
    """
    if primary is None or primary == "":
        return primary
    if display_key.endswith("_minor"):
        return format_primary_if_minor(primary, display_key, columns, item)
    display_col = _display_col_for_key(columns, display_key)
    kind = str((display_col or {}).get("type") or "")
    if kind != "badge":
        return primary
    text = format_cell(primary, "badge")
    return text if text else str(primary)


def _region_title(region: Any) -> str:
    """Extract a region's display title.

    Prefers the explicit `title` attribute, falls back to the snake-cased
    `name` attribute. Used by every `_build_*` method — consolidating it
    here removes ~19 verbatim copies of the same expression.
    """
    title = getattr(region, "title", None)
    if title:
        return str(title)
    return getattr(region, "name", "").replace("_", " ").title()


def _wrap_surface(title: str, kind: str, body: Fragment) -> Surface:
    """Wrap a body fragment in the standard region Surface chrome.

    Every `_build_*` method ends with `Surface(header=Heading(title,
    level=2), body=Region(kind=..., body=body))` — the only variation
    is `kind`. This helper consolidates the wrapping.
    """
    return Surface(
        header=Heading(title, level=2),
        body=Region(kind=kind, body=body),  # type: ignore[arg-type]
    )


def _render_status_badge_html(
    value: Any,
    *,
    size: str = "md",
    bordered: bool = False,
    display: Any = None,
    semantic_map: dict[str, str] | None = None,
) -> str:
    """Replicate the legacy `render_status_badge` macro byte-for-byte.

    Used by `_render_typed_value` for `type=="badge"` cells in DETAIL,
    LIST, TIMELINE etc. — the typed `Badge` primitive emits a different
    class scheme (`dz-badge--variant-X`) so for byte-equivalence with
    the legacy macro we replicate its HTML directly via `RawHTML`.

    Mirrors the macro's value-coalescing: None / "" / "—" → em-dash
    placeholder. Otherwise tone resolved via `_badge_tone_filter`,
    label via `_humanize_filter` (or `display` override). Note the
    macro emits a literal double-space before `data-dz-tone` because
    of the `{{ _size_class }} {{ _border_class }}` Jinja interpolation
    (when both are empty); we replicate that whitespace.
    """
    from html import escape as _esc

    from dazzle.render.filters import (
        _humanize_filter,
        badge_icon_html,
        resolve_status_tone,
    )

    if value in (None, "", "—"):
        return '<span class="dz-badge-empty" aria-label="No status">—</span>'
    # #1493 slice 2: a declared `semantic:` binding (semantic_map) wins over the
    # name guess; None/empty map → byte-identical to the legacy name guess.
    tone = resolve_status_tone(value, semantic_map)
    label = display if display is not None else _humanize_filter(value)
    label_str = str(label)
    size_class = "dz-badge-sm" if size == "sm" else ""
    border_class = "bordered" if bordered else ""
    # #1493 slice 2 part 3: WCAG colour+icon+text — non-neutral tones lead with a
    # glyph so the state isn't colour-only. Neutral → "" (byte-identical default).
    icon = badge_icon_html(tone)
    return (
        f'<span class="dz-badge {size_class} {border_class}" '
        f'data-dz-tone="{_esc(tone, quote=True)}" '
        f'role="status" '
        f'aria-label="Status: {_esc(label_str, quote=True)}">'
        f"{icon}{_esc(label_str)}</span>"
    )


def _render_file_cell(item: dict[str, Any], col: dict[str, Any]) -> Fragment:
    """Workspace file cell: filename download, not storage UUID (oral #170)."""
    key = str(col.get("key") or "")
    value = item.get(key) if key else None
    label = clerk_file_cell_display(item, key, value)
    if not label:
        return RawHTML("—")
    if label.lower() in _LEFTOVER_STAGE_TOKENS:
        return RawHTML(_html_escape(label))
    entity = str(col.get("entity_name") or "")
    record_id = str(item.get("id") or "")
    if entity and record_id and key:
        href = _html_escape(
            f"/_dazzle/documents/{entity}/{record_id}/{key}/file",
            quote=True,
        )
        return RawHTML(
            f'<a href="{href}" target="_blank" rel="noopener" '
            f'class="dz-detail-file-link">{_html_escape(label)}</a>'
        )
    return RawHTML(_html_escape(label))


def _render_typed_value(
    item: dict[str, Any],
    col: dict[str, Any],
    *,
    badge_size: str = "md",
    badge_bordered: bool = False,
    host: str = "list_cell",
) -> Fragment:
    """Render a single field value as a typed Fragment based on `col["type"]`.

    Mirrors the legacy `workspace/regions/detail.html` per-type dispatch:
        - "badge"    → RawHTML matching the legacy `render_status_badge`
                       macro byte-for-byte (Phase 4B.4 wave 2). Use
                       `badge_size`/`badge_bordered` kwargs to match
                       per-context macro args (DETAIL: bordered=True,
                       TIMELINE/LIST: size="sm" / defaults).
        - "bool"     → RawHTML via `bool_icon` filter (✓ / ✗ tinted)
        - "date"     → RawHTML via `date_filter` (DETAIL "%d %b %Y")
                       — note TIMELINE / LIST use `timeago` directly,
                       handled by the caller before this function.
        - "currency" → RawHTML via `currency_filter`
        - "ref"      → Link if ref_route is set, else escaped text
        - default    → escaped text with em-dash for None
    """
    key = str(col.get("key") or "")
    col_type = str(col.get("type") or "")
    value = item.get(key) if key else None

    if col_type == "badge":
        return RawHTML(
            _render_status_badge_html(
                value,
                size=badge_size,
                bordered=badge_bordered,
                semantic_map=col.get("semantic_map"),  # #1493 slice 2
            )
        )

    if col_type == "bool" or isinstance(value, bool):
        from dazzle.render.filters import _bool_icon_filter

        # Use the legacy bool_icon filter directly so the typed-Fragment
        # output is byte-equivalent: True → success-tinted ✓ check, False
        # → muted ✗ cross. Wrapped in RawHtml since the filter returns
        # a `Markup` HTML string with class attrs that don't map to a
        # general primitive (Phase 4B.4 wave 1).
        # Also treat bare Python bools as bool cells even when column
        # metadata lost type (convert_entities scalar-kind mismatch).
        return RawHTML(str(_bool_icon_filter(value)))

    if value is None or value == "":
        return RawHTML("—")

    # Explicit surface `format:` override when threaded onto workspace columns.
    format_kind = str(col.get("format_kind") or "")
    if format_kind:
        return RawHTML(
            _html_escape(
                format_cell(
                    value,
                    col_type or "text",
                    currency_code=str(col.get("currency_code") or ""),
                    override=ResolvedFormat(format_kind, col.get("format_arg") or None),
                )
            )
        )

    # #1623 / #1597: workspace list datetime must share entity-list presentation
    # (DisplayLocaleProfile: tenant TZ + locale.date_format) — not raw ISO dumps.
    if col_type == "datetime":
        return RawHTML(_html_escape(format_cell(value, "datetime")))

    if col_type == "date":
        return RawHTML(_html_escape(format_cell(value, "date")))

    if col_type == "currency":
        from dazzle.render.filters import _currency_filter

        return RawHTML(_currency_filter(value))

    if col_type == "bytes":
        return RawHTML(_html_escape(format_cell(value, "bytes")))

    if col_type in ("percentage", "percent_points"):
        return RawHTML(_html_escape(clerk_percent_points_display(value, key, typed=True)))

    if col_type == "color":
        # #1626 R5 / P0-8 — swatch on brand desk queues/cards (not raw hex).
        return RawHTML(_render_color_swatch_html(value))

    if col_type == "image":
        # Goal B media — logo/preview thumbs on grids/queues.
        return RawHTML(
            _render_media_thumb_html(value, alt=str(col.get("label") or col.get("key") or ""))
        )

    if col_type == "tags":
        html = clerk_tags_cell_html(value)
        return RawHTML(html) if html else RawHTML("—")

    if col_type == "rating":
        html = clerk_rating_cell_html(value)
        return RawHTML(html) if html else RawHTML("—")

    if col_type == "email":
        html = clerk_email_cell_html(value)
        return RawHTML(html) if html else RawHTML("—")

    if col_type == "phone":
        html = clerk_phone_cell_html(value)
        return RawHTML(html) if html else RawHTML("—")

    if col_type == "file":
        return _render_file_cell(item, col)

    if col_type == "ref":
        ref_route = str(col.get("ref_route") or "")
        # Resolve the display label: prefer a sibling ``<key>_display``, then the
        # FK dict's ``__display__`` (set by fk_display_only joins), then the id.
        # Never fall back to the raw dict repr — that produced ``{'id': ...}`` as
        # link text (#1389).
        display = item.get(f"{key}_display")
        if display is None:
            if isinstance(value, dict):
                display = value.get("__display__") or value.get("name") or value.get("id") or ""
            else:
                display = value
        display_str = str(display if display is not None else "")

        # Person-like refs: presentation matrix (host density; default list_cell).
        chip_probe = value if isinstance(value, dict) else {"name": display_str}
        if looks_like_person_ref(chip_probe if chip_probe is not None else {}, col):
            from dazzle.render.presentation import present

            if isinstance(value, dict):
                chip_val: Any = value
            elif display_str:
                chip_val = {"name": display_str, "id": value}
            else:
                chip_val = value
            result = present("person", host, chip_val, col)  # type: ignore[arg-type]
            if result.is_html and result.html and result.html != "—":
                return RawHTML(result.html)

        if ref_route:
            # Resolve the FK id. After repo.list(fk_display_only=True)
            # the column value can be either a scalar id (string/uuid)
            # or a dict carrying ``id`` + ``__display__``. Extract the
            # id explicitly so the URL never embeds a dict's repr —
            # which would produce strings like ``/users/{'id': ...}``
            # and trip the URL-scheme validator on the first ``:``.
            if isinstance(value, dict):
                id_value = str(value.get("id") or "")
            else:
                id_value = str(value or "")
            # Templated route (``/users/{id}``) gets the literal
            # placeholder substituted. Routes without a placeholder
            # fall back to plain path concatenation.
            if "{id}" in ref_route:
                url = ref_route.replace("{id}", id_value)
            elif ref_route.endswith("/"):
                url = f"{ref_route}{id_value}"
            else:
                url = f"{ref_route}/{id_value}"
            return Link(label=display_str, href=URL(url))
        return RawHTML(_html_escape(display_str))

    # Defensive temporal humanisation for mistyped `text` columns (parity
    # with entity list rows in _data_row.py).
    if isinstance(value, datetime):
        return RawHTML(_html_escape(format_cell(value, "datetime")))
    if isinstance(value, date):
        return RawHTML(_html_escape(format_cell(value, "date")))
    if isinstance(value, str):
        s = value.strip()
        if _ISO_DT_RE.match(s):
            return RawHTML(_html_escape(format_cell(s, "datetime")))
        if _ISO_DATE_RE.match(s):
            return RawHTML(_html_escape(format_cell(s, "date")))

    return RawHTML(_html_escape(str(value)))
