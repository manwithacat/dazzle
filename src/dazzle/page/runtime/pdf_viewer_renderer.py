"""PDF-viewer renderer (Phase 4, v0.67.81+).

Inline Python port of `components/pdf_viewer_page.html` (the DSL hook
wrapper) and `components/pdf_viewer.html` (the chrome component).
Mirrors `form_renderer` — emits HTML via `html.escape` + Python string
composition, no Jinja env. (The sibling `detail_renderer`/`table_renderer`
were deleted in ADR-0049; list/view now render via the typed substrate.)

The bridge contract is preserved: the root `<div class="dz-pdf-viewer">`
carries `data-dz-widget="pdf-viewer"` (and never `x-data`), so the
keyboard handler in `static/js/pdf-viewer.js` mounts the same way.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.context import DetailContext, PdfViewerContext
from dazzle.render.html import esc as _esc

_BACK_SVG = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true">'
    '<path d="m12 19-7-7 7-7"></path><path d="M19 12H5"></path></svg>'
)
_PREV_SVG = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true">'
    '<path d="m15 18-6-6 6-6"></path></svg>'
)
_NEXT_SVG = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true">'
    '<path d="m9 18 6-6-6-6"></path></svg>'
)
_CLOSE_SVG = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true">'
    '<path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>'
)


def render_pdf_viewer_component(
    *,
    src: str,
    back_url: str,
    title: str = "Document",
    prev_url: str | None = None,
    next_url: str | None = None,
    panels: list[dict[str, Any]] | None = None,
    panel_html: str | None = None,
    panel_label: str | None = None,
    footer_slot_html: str | None = None,
    show_kbd_legend: bool = True,
) -> str:
    """Port of `components/pdf_viewer.html`.

    Returns the full `<div class="dz-pdf-viewer">…</div>` page chrome
    (back/title/sibling nav, panels, footer, help dialog) around the HM
    `pdf` Hyperpart document region (hx-pdf P3 — was a native <embed>).
    """
    title_or_default = title or "Document"

    # Root wrapper attrs
    root_attrs = [
        'class="dz-pdf-viewer"',
        'data-dz-widget="pdf-viewer"',
        f'data-dz-back-url="{_esc(back_url, quote=True)}"',
    ]
    if prev_url:
        root_attrs.append(f'data-dz-prev-url="{_esc(prev_url, quote=True)}"')
    if next_url:
        root_attrs.append(f'data-dz-next-url="{_esc(next_url, quote=True)}"')

    # Header
    sibling_nav = ""
    if prev_url or next_url:
        prev_attrs = "" if prev_url else ' aria-disabled="true" tabindex="-1"'
        next_attrs = "" if next_url else ' aria-disabled="true" tabindex="-1"'
        sibling_nav = (
            '<nav class="dz-pdf-viewer-nav" aria-label="Sibling navigation">'
            f'<a href="{_esc(prev_url or "#", quote=True)}" '
            f'class="dz-pdf-viewer-nav-link"{prev_attrs} aria-label="Previous">'
            f"{_PREV_SVG}</a>"
            f'<a href="{_esc(next_url or "#", quote=True)}" '
            f'class="dz-pdf-viewer-nav-link"{next_attrs} aria-label="Next">'
            f"{_NEXT_SVG}</a>"
            "</nav>"
        )

    header = (
        '<header class="dz-pdf-viewer-header">'
        f'<a href="{_esc(back_url, quote=True)}" class="dz-pdf-viewer-back" aria-label="Back">'
        f'{_BACK_SVG}<span class="dz-pdf-viewer-back-label">Back</span></a>'
        f'<h1 class="dz-pdf-viewer-title">{_esc(title_or_default)}</h1>'
        f"{sibling_nav}"
        "</header>"
    )

    # Panel list normalisation (cycle 2a/5a compat)
    if panels:
        _panels = panels
    elif panel_html is not None:
        _panels = [
            {
                "name": "panel",
                "label": panel_label or "Related",
                "key": "p",
                "html": panel_html,
            }
        ]
    else:
        _panels = []

    # hx-pdf P3: the document region is the HM pdf Hyperpart — dz-pdf.js
    # renders via the VENDORED PDF.js (no browser-plugin <embed>). The
    # storage-proxy src passes through verbatim; the page chrome around
    # it (back/title/sibling nav/panels/footer) stays Dazzle-owned.
    embed = (
        f'<section class="dz-pdf dz-pdf-viewer-embed" data-dz-pdf '
        f'data-dz-pdf-src="{_esc(src, quote=True)}" '
        f'data-dz-pdf-lib="/static/vendor/pdfjs/pdf.min.mjs" '
        f'data-dz-pdf-worker="/static/vendor/pdfjs/pdf.worker.min.mjs" '
        f'aria-label="{_esc(title_or_default, quote=True)} PDF">'
        '<header class="dz-pdf-toolbar" data-dz-pdf-toolbar>'
        '<button type="button" class="dz-button" data-dz-size="sm" '
        'data-dz-variant="outline" data-dz-pdf-prev>Previous</button>'
        "<label>Page "
        '<input class="dz-pdf-page-input" data-dz-pdf-page value="1" '
        'inputmode="numeric" aria-label="Page number">'
        "</label>"
        '<span class="dz-pdf-page-count" data-dz-pdf-page-count></span>'
        '<button type="button" class="dz-button" data-dz-size="sm" '
        'data-dz-variant="outline" data-dz-pdf-next>Next</button>'
        '<span class="dz-pdf-toolbar-spacer"></span>'
        '<button type="button" class="dz-button" data-dz-size="sm" '
        'data-dz-variant="outline" data-dz-pdf-zoom-out aria-label="Zoom out">−</button>'
        '<button type="button" class="dz-button" data-dz-size="sm" '
        'data-dz-variant="outline" data-dz-pdf-zoom-in aria-label="Zoom in">+</button>'
        '<button type="button" class="dz-button" data-dz-size="sm" '
        'data-dz-variant="outline" data-dz-pdf-fit-width>Fit width</button>'
        "</header>"
        '<div class="dz-pdf-status" data-dz-pdf-status aria-live="polite"></div>'
        '<div class="dz-pdf-stage" data-dz-pdf-viewer>'
        f'<noscript><a href="{_esc(src, quote=True)}">Download PDF</a></noscript>'
        "</div>"
        "</section>"
    )

    panel_blocks: list[str] = []
    for panel in _panels:
        p_name = _esc(panel.get("name", ""), quote=True)
        p_label = panel.get("label", "")
        p_key = _esc(panel.get("key", ""), quote=True)
        p_html = panel.get("html", "")
        panel_blocks.append(
            '<input type="checkbox" '
            f'id="dz-panel-toggle-{p_name}" class="dz-pdf-viewer-panel-toggle" '
            f'data-dz-panel-name="{p_name}" data-dz-panel-key="{p_key}" '
            f'aria-label="Toggle {_esc(p_label, quote=True)}" />'
            f'<aside class="dz-pdf-viewer-panel" data-dz-panel="{p_name}" '
            f'role="complementary" aria-label="{_esc(p_label, quote=True)}">'
            '<header class="dz-pdf-viewer-panel-header">'
            f'<h2 class="dz-pdf-viewer-panel-title">{_esc(p_label)}</h2>'
            '<button type="button" class="dz-pdf-viewer-panel-close" '
            f'data-dz-panel-close aria-label="Close {_esc(p_label, quote=True)} panel">'
            f"{_CLOSE_SVG}</button>"
            "</header>"
            f'<div class="dz-pdf-viewer-panel-body">{p_html}</div>'
            "</aside>"
        )

    body = f'<div class="dz-pdf-viewer-body">{embed}{"".join(panel_blocks)}</div>'

    # Footer: slot + keyboard legend
    footer_parts: list[str] = []
    if footer_slot_html:
        footer_parts.append(f'<div class="dz-pdf-viewer-footer-slot">{footer_slot_html}</div>')
    if show_kbd_legend:
        legend = [
            '<kbd class="dz-pdf-viewer-kbd">Esc</kbd>',
            '<span class="dz-pdf-viewer-kbd-label">Back</span>',
        ]
        if prev_url or next_url:
            legend.extend(
                [
                    '<span class="dz-pdf-viewer-kbd-sep">·</span>',
                    '<kbd class="dz-pdf-viewer-kbd">j</kbd>',
                    '<span class="dz-pdf-viewer-kbd-label">Previous</span>',
                    '<kbd class="dz-pdf-viewer-kbd">k</kbd>',
                    '<span class="dz-pdf-viewer-kbd-label">Next</span>',
                ]
            )
        for panel in _panels:
            p_key = _esc(panel.get("key", ""))
            p_label = _esc(panel.get("label", ""))
            legend.extend(
                [
                    '<span class="dz-pdf-viewer-kbd-sep">·</span>',
                    f'<kbd class="dz-pdf-viewer-kbd">{p_key}</kbd>',
                    f'<span class="dz-pdf-viewer-kbd-label">{p_label}</span>',
                ]
            )
        legend.extend(
            [
                '<span class="dz-pdf-viewer-kbd-sep">·</span>',
                '<kbd class="dz-pdf-viewer-kbd">?</kbd>',
                '<span class="dz-pdf-viewer-kbd-label">Help</span>',
            ]
        )
        footer_parts.append("".join(legend))

    footer = (
        '<footer class="dz-pdf-viewer-footer" aria-label="Keyboard shortcuts">'
        f"{''.join(footer_parts)}"
        "</footer>"
    )

    # Help dialog
    help_rows = [
        '<div class="dz-pdf-viewer-help-row">'
        "<dt><kbd>Esc</kbd></dt>"
        "<dd>Back (or close this overlay first)</dd></div>"
    ]
    if prev_url or next_url:
        help_rows.append(
            '<div class="dz-pdf-viewer-help-row">'
            "<dt><kbd>j</kbd> / <kbd>&larr;</kbd></dt><dd>Previous</dd></div>"
            '<div class="dz-pdf-viewer-help-row">'
            "<dt><kbd>k</kbd> / <kbd>&rarr;</kbd></dt><dd>Next</dd></div>"
        )
    for panel in _panels:
        p_key = _esc(panel.get("key", ""))
        p_label = _esc(panel.get("label", ""))
        help_rows.append(
            f'<div class="dz-pdf-viewer-help-row">'
            f"<dt><kbd>{p_key}</kbd></dt><dd>Toggle {p_label}</dd></div>"
        )
    help_rows.append(
        '<div class="dz-pdf-viewer-help-row"><dt><kbd>?</kbd></dt><dd>Show this overlay</dd></div>'
    )

    help_dialog = (
        '<dialog class="dz-pdf-viewer-help" data-dz-help-overlay '
        'aria-labelledby="dz-pdf-viewer-help-title">'
        '<header class="dz-pdf-viewer-help-header">'
        '<h2 id="dz-pdf-viewer-help-title" class="dz-pdf-viewer-help-title">'
        "Keyboard shortcuts</h2>"
        '<button type="button" class="dz-pdf-viewer-help-close" '
        'data-dz-help-close aria-label="Close shortcuts">'
        f"{_CLOSE_SVG}</button>"
        "</header>"
        f'<dl class="dz-pdf-viewer-help-list">{"".join(help_rows)}</dl>'
        "</dialog>"
    )

    return f"<div {' '.join(root_attrs)}>{header}{body}{footer}{help_dialog}</div>"


def render_pdf_viewer(
    detail: DetailContext | None,
    pdf_viewer: PdfViewerContext,
) -> str:
    """Port of `components/pdf_viewer_page.html`.

    Build the proxy URL from `detail.item[file_field]` + `storage_name`
    and emit the full chrome via `render_pdf_viewer_component`. Mirrors
    the wrapper's null-safety: missing detail or missing file value
    produce an empty `src` (matching the legacy Jinja `if _pdf_key else ""`
    fallback).
    """
    item = detail.item if detail and detail.item else {}
    pdf_key = item.get(pdf_viewer.file_field) if item else None
    src = f"/api/storage/{pdf_viewer.storage_name}/proxy?key={pdf_key}" if pdf_key else ""
    back_url = detail.back_url if detail else "/"
    title = detail.title if detail else "Document"
    return render_pdf_viewer_component(src=src, back_url=back_url, title=title)
