"""PageContext → Page primitive adapter (Plan 17 P2).

The Fragment substrate ships a typed `Page` primitive that wraps an
HTML document. This module is the bridge from the runtime's
`PageContext` (carrying surface-level metadata + an already-rendered
inner HTML body) to a `Page` primitive ready for the Fragment renderer.

Asset URLs (css_links, js_scripts) and theme are intentionally passed
in by the caller as kwargs rather than scraped from PageContext — the
existing template path resolves them via dazzle.toml + asset bundle
detection at render time, and the caller (page_routes) already has
those resolutions in scope. Replicating that resolution logic here
would duplicate a moving target; passing in is honest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.render.fragment import Page
from dazzle.render.fragment.escape import RawHTML

if TYPE_CHECKING:
    from dazzle_ui.runtime.template_context import PageContext


def build_page(
    ctx: PageContext,
    inner_html: str,
    *,
    css_links: tuple[str, ...] = (),
    js_scripts: tuple[str, ...] = (),
    theme: str | None = None,
    favicon: str = "/static/assets/dazzle-favicon.svg",
    extra_meta: tuple[tuple[str, str], ...] = (),
) -> Page:
    """Build a Page primitive from PageContext + already-rendered inner HTML.

    `inner_html` is the surface body the Fragment adapter produced —
    typically a `<section class="dz-surface">…</section>` block. This is
    wrapped in `RawHTML` so it composes into Page.body as a single Fragment
    leaf without re-escaping.
    """
    page_title = ctx.page_title.strip() if ctx.page_title else ""
    app_name = (ctx.app_name or "Dazzle").strip()
    title = f"{page_title} — {app_name}" if page_title else app_name
    return Page(
        title=title,
        body=RawHTML(inner_html),
        theme=theme,
        css_links=css_links,
        js_scripts=js_scripts,
        favicon=favicon,
        meta=extra_meta,
    )


def dispatch_render_page(
    ctx: PageContext,
    inner_html: str,
    *,
    css_links: tuple[str, ...] = (),
    js_scripts: tuple[str, ...] = (),
    theme: str | None = None,
    favicon: str = "/static/assets/dazzle-favicon.svg",
    extra_meta: tuple[tuple[str, str], ...] = (),
) -> str:
    """Build a Page and render it to HTML — convenience wrapper.

    Page chrome is a one-shot render (the document is structurally
    fixed); no need for renderer-registry indirection like surface
    bodies have. Direct construction + render is the fastest path.
    """
    from dazzle.render.fragment.renderer import FragmentRenderer

    page = build_page(
        ctx,
        inner_html,
        css_links=css_links,
        js_scripts=js_scripts,
        theme=theme,
        favicon=favicon,
        extra_meta=extra_meta,
    )
    return FragmentRenderer().render(page)
