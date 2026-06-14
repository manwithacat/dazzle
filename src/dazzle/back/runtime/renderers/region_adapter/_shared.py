"""Cross-family helpers shared across every region-adapter builder.

These four helpers are used by ≥2 builder families AND in the case of
`_render_status_badge_html` are imported externally (by
`dazzle.render.fragment.renderer`). Extracting them here means each
follow-up builder-family file (`_builders_cards.py`, `_builders_charts.py`,
etc.) imports from a single, stable surface — no circular dependencies on
the dispatcher and no need to import sibling family modules.

Public-API note: `_render_status_badge_html` is re-exported by
`region_adapter/__init__.py` so the `from
dazzle.back.runtime.renderers.region_adapter import _render_status_badge_html`
call sites in `renderer.py` keep working unchanged.

See issue #1065 for the full decomposition plan.
"""

from __future__ import annotations

from html import escape as _html_escape
from typing import Any

from dazzle.render.fragment import (
    URL,
    Fragment,
    Heading,
    Link,
    RawHTML,
    Region,
    Surface,
)


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
    value: Any, *, size: str = "md", bordered: bool = False, display: Any = None
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
        _badge_tone_filter,
        _humanize_filter,
    )

    if value in (None, "", "—"):
        return '<span class="dz-badge-empty" aria-label="No status">—</span>'
    tone = _badge_tone_filter(value)
    label = display if display is not None else _humanize_filter(value)
    label_str = str(label)
    size_class = "dz-badge-sm" if size == "sm" else ""
    border_class = "bordered" if bordered else ""
    return (
        f'<span class="dz-badge {size_class} {border_class}" '
        f'data-dz-tone="{_esc(tone, quote=True)}" '
        f'role="status" '
        f'aria-label="Status: {_esc(label_str, quote=True)}">'
        f"{_esc(label_str)}</span>"
    )


def _render_typed_value(
    item: dict[str, Any],
    col: dict[str, Any],
    *,
    badge_size: str = "md",
    badge_bordered: bool = False,
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
        return RawHTML(_render_status_badge_html(value, size=badge_size, bordered=badge_bordered))

    if col_type == "bool":
        from dazzle.render.filters import _bool_icon_filter

        # Use the legacy bool_icon filter directly so the typed-Fragment
        # output is byte-equivalent: True → success-tinted ✓ check, False
        # → muted ✗ cross. Wrapped in RawHtml since the filter returns
        # a `Markup` HTML string with class attrs that don't map to a
        # general primitive (Phase 4B.4 wave 1).
        return RawHTML(str(_bool_icon_filter(value)))

    if value is None or value == "":
        return RawHTML("—")

    if col_type == "date":
        from dazzle.render.filters import _date_filter

        return RawHTML(_date_filter(value))

    if col_type == "currency":
        from dazzle.render.filters import _currency_filter

        return RawHTML(_currency_filter(value))

    if col_type == "ref":
        ref_route = str(col.get("ref_route") or "")
        # Resolve the display label: prefer a sibling ``<key>_display``, then the
        # FK dict's ``__display__`` (set by fk_display_only joins), then the id.
        # Never fall back to the raw dict repr — that produced ``{'id': ...}`` as
        # link text (#1389).
        display = item.get(f"{key}_display")
        if display is None:
            if isinstance(value, dict):
                display = value.get("__display__") or value.get("id") or ""
            else:
                display = value
        display_str = str(display)
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

    return RawHTML(_html_escape(str(value)))
