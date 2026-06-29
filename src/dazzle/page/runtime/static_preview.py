"""
Static preview generator.

Generates self-contained HTML files from an AppSpec that can be opened
in a browser without a running server. Uses mock data and inlines all
CSS/JS dependencies via CDN links.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from dazzle.core import ir
from dazzle.core.ir import SurfaceMode
from dazzle.page.converters.template_compiler import compile_surface_to_context
from dazzle.page.runtime.mock_data import generate_mock_records
from dazzle.page.runtime.template_renderer import render_page

# ADR-0049 Task 6: `mode: list` renders via the typed substrate, whose dispatch
# seam lives in the http layer (page ↛ http). The caller (the CLI build service)
# injects a renderer that produces the substrate list body for a (surface, ctx);
# `render_page(ctx, inner_html=body)` then wraps it in the page chrome. (The
# legacy `render_filterable_table` was skeleton-only too, so the static list
# preview was always an empty skeleton — no content regression.)
ListBodyRenderer = Callable[[ir.SurfaceSpec, object], str]


def _render_list_preview(
    ctx: object, surface: ir.SurfaceSpec, list_body_renderer: ListBodyRenderer | None
) -> str:
    """Render a list surface's static preview page. The substrate list body is
    produced by the injected `list_body_renderer` (the http dispatch seam the
    page layer can't reach) and wrapped in the page chrome via `inner_html`.
    Without a renderer, `render_page` raises loudly (ADR-0049 D4)."""
    body = list_body_renderer(surface, ctx) if list_body_renderer is not None else None
    return render_page(ctx, inner_html=body)  # type: ignore[arg-type]


def generate_preview_files(
    appspec: ir.AppSpec,
    output_dir: str | Path,
    *,
    list_body_renderer: ListBodyRenderer | None = None,
) -> list[Path]:
    """
    Generate static preview HTML files for all surfaces.

    Each surface produces one or more HTML files:
    - List surfaces: entity-list.html, entity-list--empty.html
    - Create surfaces: entity-create.html
    - Edit surfaces: entity-edit.html
    - View surfaces: entity-detail.html

    Args:
        appspec: Complete application specification.
        output_dir: Directory to write HTML files to.

    Returns:
        List of generated file paths.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    domain = appspec.domain

    for surface in appspec.surfaces:
        entity: ir.EntitySpec | None = None
        if domain and surface.entity_ref:
            entity = domain.get_entity(surface.entity_ref)

        entity_name = entity.name if entity else (surface.entity_ref or "item")
        from dazzle.core.strings import entity_slug

        slug = entity_slug(entity_name)

        ctx = compile_surface_to_context(surface, entity)
        ctx.app_name = appspec.title or appspec.name.replace("_", " ").title()

        if surface.mode == SurfaceMode.LIST:
            # Generate with mock data
            if entity:
                mock_items = generate_mock_records(entity, count=5)
                if ctx.table:
                    ctx.table.rows = mock_items
                    ctx.table.total = len(mock_items)

            html = _render_list_preview(ctx, surface, list_body_renderer)
            file_path = output_path / f"{slug}-list.html"
            file_path.write_text(html, encoding="utf-8")
            generated.append(file_path)

            # Generate empty state variant
            if ctx.table:
                ctx.table.rows = []
                ctx.table.total = 0
            empty_html = _render_list_preview(ctx, surface, list_body_renderer)
            empty_path = output_path / f"{slug}-list--empty.html"
            empty_path.write_text(empty_html, encoding="utf-8")
            generated.append(empty_path)

        elif surface.mode == SurfaceMode.CREATE:
            html = render_page(ctx)
            file_path = output_path / f"{slug}-create.html"
            file_path.write_text(html, encoding="utf-8")
            generated.append(file_path)

        elif surface.mode == SurfaceMode.EDIT:
            # Fill with mock data for edit preview
            if entity and ctx.form:
                mock = generate_mock_records(entity, count=1)
                if mock:
                    ctx.form.initial_values = mock[0]
                    # Replace {id} placeholders
                    item_id = mock[0].get("id", "preview-id")
                    ctx.form.action_url = ctx.form.action_url.replace("{id}", str(item_id))
                    if ctx.form.cancel_url:
                        ctx.form.cancel_url = ctx.form.cancel_url.replace("{id}", str(item_id))

            html = render_page(ctx)
            file_path = output_path / f"{slug}-edit.html"
            file_path.write_text(html, encoding="utf-8")
            generated.append(file_path)

        elif surface.mode == SurfaceMode.VIEW:
            # Fill with mock data for detail preview
            if entity and ctx.detail:
                mock = generate_mock_records(entity, count=1)
                if mock:
                    ctx.detail.item = mock[0]
                    item_id = mock[0].get("id", "preview-id")
                    if ctx.detail.edit_url:
                        ctx.detail.edit_url = ctx.detail.edit_url.replace("{id}", str(item_id))
                    if ctx.detail.delete_url:
                        ctx.detail.delete_url = ctx.detail.delete_url.replace("{id}", str(item_id))
                    for _t in ctx.detail.transitions:
                        if _t.api_url and "{id}" in _t.api_url:
                            _t.api_url = _t.api_url.replace("{id}", str(item_id))

            html = render_page(ctx)
            file_path = output_path / f"{slug}-detail.html"
            file_path.write_text(html, encoding="utf-8")
            generated.append(file_path)

    return generated
