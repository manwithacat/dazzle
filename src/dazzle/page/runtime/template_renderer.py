"""Page renderer for server-rendered Dazzle pages.

Post-#1044 (v0.67.92+): the framework no longer ships Jinja2. The
``render_page`` entry point dispatches every PageContext through the
typed-substrate body renderers (form / detail / table / pdf_viewer)
and then delegates layout to ``dispatch_render_page``.

The pure-Python value-formatting helpers (``_currency_filter``,
``_date_filter``, ``_badge_tone_filter``, etc.) moved to
``dazzle.render.filters`` in #1090 — import from there directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.render.context import PageContext


def _render_typed_body(context: PageContext) -> str:
    """Dispatch a PageContext to the right typed renderer.

    Post-#1044: every framework surface lands here. The dispatch order
    matters — ``pdf_viewer`` is set in addition to ``detail`` on
    ``display: pdf_viewer`` surfaces, so it must branch first.

    v0.71.3: a non-empty ``active_guide_html`` (set by
    ``page_routes._inject_onboarding_step``) is prepended to whatever
    body the typed dispatch produces. The overlay sits before the
    surface body so it's the first thing the user lands on; the
    actual surface content stays below.
    """
    overlay = context.active_guide_html or ""
    body = _render_body_inner(context)
    return overlay + body


def _render_body_inner(context: PageContext) -> str:
    """Typed-body dispatch (no guide overlay)."""
    if context.form is not None:
        # ADR-0049 Phase 3b (D4): create/edit (mode: create/edit) surfaces render
        # exclusively via the typed substrate now — the legacy form_renderer is
        # deleted. Reaching here means the substrate dispatch was skipped (no
        # RuntimeServices on the request, so `_maybe_dispatch_inner_html`
        # returned None) — a real misconfiguration, not a blank page. Fail loudly.
        raise RuntimeError(
            "form surface reached the legacy body renderer, but mode: create/edit "
            "renders via the typed substrate now (ADR-0049). Attach RuntimeServices "
            "to the request (app.state.services) so the form dispatches to the "
            f"substrate. (page_title={context.page_title!r})"
        )
    if context.pdf_viewer is not None:
        from dazzle.page.runtime.pdf_viewer_renderer import render_pdf_viewer

        return render_pdf_viewer(context.detail, context.pdf_viewer)
    if context.detail is not None:
        # ADR-0049 Phase 2 (D4): detail (mode: view) surfaces render exclusively
        # via the typed substrate now — the legacy render_detail_view is deleted.
        # Reaching here means the substrate dispatch was skipped (no
        # RuntimeServices on the request) — fail loudly, not a blank page.
        raise RuntimeError(
            "detail surface reached the legacy body renderer, but mode: view "
            "renders via the typed substrate now (ADR-0049). Attach "
            "RuntimeServices to the request (app.state.services) so the detail "
            f"dispatches to the substrate. (page_title={context.page_title!r})"
        )
    if context.table is not None:
        # ADR-0049 Task 6 (D4): list surfaces render exclusively via the typed
        # substrate now — the legacy `render_filterable_table` is deleted.
        # Reaching here means the substrate dispatch was skipped (no
        # RuntimeServices on the request, so `_maybe_dispatch_inner_html`
        # returned None) — a real misconfiguration, not a blank page. Fail
        # loudly rather than render an empty 200.
        raise RuntimeError(
            "list surface reached the legacy body renderer, but lists render via "
            "the typed substrate now (ADR-0049). Attach RuntimeServices to the "
            "request (app.state.services) so the list dispatches to the substrate. "
            f"(page_title={context.page_title!r})"
        )
    return ""


def render_page(
    context: PageContext,
    *,
    partial: bool = False,
    content_only: bool = False,
    inner_html: str | None = None,
) -> str:
    """Render a full page from a PageContext."""
    if inner_html is not None:
        rendered_content = inner_html
    else:
        rendered_content = _render_typed_body(context)

    if content_only or partial:
        return rendered_content

    from dazzle.page.runtime.theme import get_sidebar_state
    from dazzle.render.dispatch import dispatch_render_page

    # #1294 — thread the persisted sidebar open/closed state (dz_sidebar
    # cookie, read by ThemeVariantMiddleware) into the chrome so SSR emits
    # the correct `data-dz-sidebar` on first paint (no flash on this, the
    # dominant app-surface render path). The JS controller is the universal
    # fallback for any path that defaults to "open".
    return dispatch_render_page(
        context,
        rendered_content,
        chrome=(context.layout != "single_column"),
        sidebar_state=get_sidebar_state(),
    )
