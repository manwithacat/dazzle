"""
Static preview generator.

Generates self-contained HTML files from an AppSpec that can be opened
in a browser without a running server. Uses mock data and inlines all
CSS/JS dependencies via CDN links.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dazzle.core import ir
from dazzle.core.ir import SurfaceMode
from dazzle_dnr_ui.converters.template_compiler import compile_surface_to_context
from dazzle_dnr_ui.runtime.mock_data import generate_mock_records
from dazzle_dnr_ui.runtime.template_renderer import render_page

if TYPE_CHECKING:
    pass


def generate_preview_files(
    appspec: ir.AppSpec,
    output_dir: str | Path,
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
        slug = entity_name.lower().replace("_", "-")

        ctx = compile_surface_to_context(surface, entity)
        ctx.app_name = appspec.title or appspec.name.replace("_", " ").title()

        if surface.mode == SurfaceMode.LIST:
            # Generate with mock data
            if entity:
                mock_items = generate_mock_records(entity, count=5)
                if ctx.table:
                    ctx.table.rows = mock_items
                    ctx.table.total = len(mock_items)

            html = render_page(ctx)
            file_path = output_path / f"{slug}-list.html"
            file_path.write_text(html, encoding="utf-8")
            generated.append(file_path)

            # Generate empty state variant
            if ctx.table:
                ctx.table.rows = []
                ctx.table.total = 0
            empty_html = render_page(ctx)
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

            html = render_page(ctx)
            file_path = output_path / f"{slug}-detail.html"
            file_path.write_text(html, encoding="utf-8")
            generated.append(file_path)

    return generated
