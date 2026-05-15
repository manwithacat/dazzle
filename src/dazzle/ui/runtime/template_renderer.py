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
    """
    if context.form is not None:
        from dazzle.ui.runtime.form_renderer import render_form_field

        return "".join(render_form_field(f) for f in context.form.fields)
    if context.pdf_viewer is not None:
        from dazzle.ui.runtime.pdf_viewer_renderer import render_pdf_viewer

        return render_pdf_viewer(context.detail, context.pdf_viewer)
    if context.detail is not None:
        from dazzle.ui.runtime.detail_renderer import render_detail_view

        return render_detail_view(context.detail)
    if context.table is not None:
        from dazzle.ui.runtime.table_renderer import render_filterable_table

        return render_filterable_table(context.table, page_title=context.page_title)
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

    from dazzle.render.dispatch import dispatch_render_page

    return dispatch_render_page(
        context,
        rendered_content,
        chrome=(context.layout != "single_column"),
    )
