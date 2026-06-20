"""Cross-arm helpers shared across multiple FragmentRenderer emit methods.

Three helpers extracted from `_emit.py` in #1064 PR 2. All three are
pure functions (no `self` access) — the previous class-method form was
incidental, not architectural.

  - `_hx_attrs`           HTMX attribute-string builder (3 callers:
                          `_emit_button`, `_emit_link`, `_emit_interactive`)
  - `_pagination_pages`   bounded ellipsis-collapsed page list
                          (1 caller: `_emit_pagination`)
  - `_render_references`  chart reference-line / -band `<dl>` block
                          (1 caller: `_emit_bar_track`)

These were already pure: `_hx_attrs` and `_pagination_pages` were
`@staticmethod`; `_render_references` took `self` but only used `ctx`
for escaping. Extracting here lets follow-up family-mixin PRs import
each helper without depending on the dispatcher class.

See issue #1064 for the full decomposition plan; mirror of `_shared.py`
in `region_adapter` (#1065 PR 2 / v0.67.129).
"""

from __future__ import annotations

from html import escape as _escape

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.primitives import ReferenceBand, ReferenceLine


def _hx_attrs(
    *,
    hx_get: object,
    hx_post: object,
    hx_target: object,
    hx_swap: object | None,
    hx_trigger: object | None = None,
    hx_indicator: object | None = None,
    hx_confirm: object | None = None,
    hx_put: object | None = None,
    hx_delete: object | None = None,
    hx_vals: str = "",
    hx_ext: tuple[str, ...] = (),
) -> str:
    """Build the htmx attribute string for an interactive primitive.

    All values are escaped for attribute context. Wrapper types (URL,
    TargetSelector, HxTrigger) are validated at construction; this
    escape pass converts characters like `&` in query strings to their
    HTML entity form so the output is valid HTML5.

    Phase 4B.1.d added hx_put + hx_vals + hx_ext (queue transitions,
    JSON payloads, hx-ext extension list).
    """
    parts: list[str] = []
    if hx_get is not None:
        parts.append(f'hx-get="{_escape(str(hx_get), quote=True)}"')
    if hx_post is not None:
        parts.append(f'hx-post="{_escape(str(hx_post), quote=True)}"')
    if hx_put is not None:
        parts.append(f'hx-put="{_escape(str(hx_put), quote=True)}"')
    if hx_delete is not None:
        parts.append(f'hx-delete="{_escape(str(hx_delete), quote=True)}"')
    if hx_target is not None:
        parts.append(f'hx-target="{_escape(str(hx_target), quote=True)}"')
    if hx_swap is not None:
        parts.append(f'hx-swap="{_escape(str(hx_swap), quote=True)}"')
    if hx_trigger is not None:
        parts.append(f'hx-trigger="{_escape(str(hx_trigger), quote=True)}"')
    if hx_indicator is not None:
        parts.append(f'hx-indicator="{_escape(str(hx_indicator), quote=True)}"')
    if hx_confirm is not None:
        parts.append(f'hx-confirm="{_escape(str(hx_confirm), quote=True)}"')
    if hx_vals:
        # Use single quotes around the JSON value so internal double
        # quotes (a JSON dict's quoted keys) don't need escaping.
        # Single quotes inside the value are escaped to &#39;.
        escaped_vals = hx_vals.replace("'", "&#39;")
        parts.append(f"hx-vals='{escaped_vals}'")
    if hx_ext:
        parts.append(f'hx-ext="{_escape(",".join(hx_ext), quote=True)}"')
    return " ".join(parts)


def _pagination_pages(current: int, total: int, window: int = 2) -> list[int | None]:
    """Mirror of `dazzle.ui.runtime.template_renderer._pagination_pages`
    (#984). Returns a bounded ellipsis-collapsed page list.

    Examples (window=2):
        current=1,  total=5    → [1, 2, 3, 4, 5]
        current=7,  total=120  → [1, None, 5, 6, 7, 8, 9, None, 120]
    """
    if total <= 0:
        return []
    if total == 1:
        return [1]
    explicit_count = 2 * window + 3
    if total <= explicit_count + 2:
        return list(range(1, total + 1))
    pages: list[int | None] = [1]
    win_start = max(2, current - window)
    win_end = min(total - 1, current + window)
    if win_start > 2:
        pages.append(None)
    pages.extend(range(win_start, win_end + 1))
    if win_end < total - 1:
        pages.append(None)
    pages.append(total)
    return pages


def _render_references(
    block_class: str,
    reference_lines: tuple[ReferenceLine, ...],
    reference_bands: tuple[ReferenceBand, ...],
    ctx: RenderContext,
) -> str:
    """Shared helper — emit a `<dl class="<block>__references">` annotation
    list when a chart primitive carries reference_lines or reference_bands.
    Returns empty string when both tuples are empty.

    Used by TimeSeries, BarChart, BarTrack, BoxPlot. Future SVG-rendering
    ship will overlay references on the visual chart instead.
    """
    if not reference_lines and not reference_bands:
        return ""
    line_items = "".join(
        f'<div class="{block_class}__ref-line" '
        f'data-style="{ctx.escape_attr(line.style)}" '
        f'data-value="{line.value}">'
        f'<dt class="{block_class}__ref-label">{ctx.escape(line.label) or "ref"}</dt>'
        f'<dd class="{block_class}__ref-value">{line.value}</dd>'
        f"</div>"
        for line in reference_lines
    )
    band_items = "".join(
        f'<div class="{block_class}__ref-band" '
        f'data-color="{ctx.escape_attr(band.color)}" '
        f'data-from="{band.from_value}" '
        f'data-to="{band.to_value}">'
        f'<dt class="{block_class}__ref-label">{ctx.escape(band.label) or "band"}</dt>'
        f'<dd class="{block_class}__ref-range">'
        f"{band.from_value}–{band.to_value}</dd>"
        f"</div>"
        for band in reference_bands
    )
    return f'<dl class="{block_class}__references">{line_items}{band_items}</dl>'
