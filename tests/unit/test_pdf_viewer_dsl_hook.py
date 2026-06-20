"""Tests for #942 cycle 4 — the ``display: pdf_viewer`` DSL hook.

Post-#1045: the wrapper renders via the typed `pdf_viewer_renderer`
(Python) rather than `components/pdf_viewer_page.html` (Jinja).

Covers:
- Parser accepts ``display: pdf_viewer`` on a surface body and stores
  it on ``SurfaceSpec.display``
- Parser rejects unknown values (only ``pdf_viewer`` is recognised today)
- Template compiler routes a VIEW-mode surface with display=pdf_viewer
  through the typed dispatch (``template=""``) and populates the
  ``pdf_viewer`` ctx with the entity's first file-storage field
- Template compiler ignores ``display: pdf_viewer`` when the entity
  has no file-storage field (falls back to generic detail layout)
- The renderer builds a proxy URL from ``detail.item[file_field]`` +
  ``storage_name``
"""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl


def _parse(src: str) -> Any:
    """Parse a DSL fragment and return the ModuleFragment."""
    result = parse_dsl(src, "/tmp/test.dsl")
    return result[5]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestParser:
    def test_display_pdf_viewer_round_trips(self) -> None:
        frag = _parse(
            """module test
app test "Test"

entity Document "Document":
  id: uuid pk
  title: str(200) required
  source_pdf: file storage=docs

surface document_view "View":
  uses entity Document
  mode: view
  display: pdf_viewer
  section main:
    field title "Title"
"""
        )
        assert len(frag.surfaces) == 1
        assert frag.surfaces[0].display == "pdf_viewer"

    def test_display_default_is_none(self) -> None:
        frag = _parse(
            """module test
app test "Test"

entity Doc "Doc":
  id: uuid pk
  title: str(200) required

surface doc_view "View":
  uses entity Doc
  mode: view
  section main:
    field title "Title"
"""
        )
        assert frag.surfaces[0].display is None

    def test_display_unknown_value_rejected(self) -> None:
        with pytest.raises(Exception) as exc_info:
            _parse(
                """module test
app test "Test"

entity Doc "Doc":
  id: uuid pk
  title: str(200) required

surface doc_view "View":
  uses entity Doc
  mode: view
  display: foo_viewer
  section main:
    field title "Title"
"""
            )
        assert "pdf_viewer" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Template compiler routing
# ---------------------------------------------------------------------------


class TestCompilerRouting:
    def _compile_view_surface(
        self, with_file_field: bool = True, display: str | None = "pdf_viewer"
    ) -> Any:
        from dazzle.page.converters.template_compiler import compile_surface_to_context

        src_lines = [
            "module test",
            'app test "Test"',
            "",
            'entity Document "Document":',
            "  id: uuid pk",
            "  title: str(200) required",
        ]
        if with_file_field:
            src_lines.append("  source_pdf: file storage=cohort_pdfs")
        src_lines.extend(
            [
                "",
                'surface doc_view "View":',
                "  uses entity Document",
                "  mode: view",
            ]
        )
        if display is not None:
            src_lines.append(f"  display: {display}")
        src_lines.extend(
            [
                "  section main:",
                '    field title "Title"',
            ]
        )
        frag = _parse("\n".join(src_lines) + "\n")
        surface = frag.surfaces[0]
        entity = next(e for e in frag.entities if e.name == "Document")
        return compile_surface_to_context(surface, entity, app_prefix="/app")

    def test_routes_to_typed_pdf_viewer_renderer(self) -> None:
        ctx = self._compile_view_surface()
        # Post-#1045: typed dispatch — template is empty, pdf_viewer is set.
        assert ctx.template == ""
        assert ctx.pdf_viewer is not None
        assert ctx.pdf_viewer.storage_name == "cohort_pdfs"
        assert ctx.pdf_viewer.file_field == "source_pdf"

    def test_falls_back_when_no_file_field(self) -> None:
        ctx = self._compile_view_surface(with_file_field=False)
        # Without a file-storage field, pdf_viewer hook stays unset and
        # detail_renderer handles the surface via the typed dispatch.
        assert ctx.template == ""
        assert ctx.pdf_viewer is None

    def test_no_display_means_generic_detail(self) -> None:
        ctx = self._compile_view_surface(display=None)
        assert ctx.template == ""
        assert ctx.pdf_viewer is None

    def test_detail_context_still_populated(self) -> None:
        """The renderer relies on detail.item being filled in by
        ``_handle_detail`` at request time. The compiler must keep
        the DetailContext intact even when pdf_viewer is set."""
        ctx = self._compile_view_surface()
        assert ctx.detail is not None
        assert ctx.detail.entity_name == "Document"
        assert ctx.detail.back_url == "/app/document"


# ---------------------------------------------------------------------------
# Typed renderer (post-#1045 replacement for Jinja wrapper)
# ---------------------------------------------------------------------------


class TestTypedRenderer:
    def test_proxy_url_built_from_storage_and_file_field(self) -> None:
        from dazzle.page.runtime.pdf_viewer_renderer import render_pdf_viewer
        from dazzle.render.context import (
            DetailContext,
            FieldContext,
            PdfViewerContext,
        )

        detail = DetailContext(
            entity_name="Document",
            title="My Doc",
            fields=[FieldContext(name="title", label="Title")],
            item={"id": "u1", "title": "My Doc", "source_pdf": "u1/abc/file.pdf"},
            back_url="/app/document",
        )
        pdf_viewer = PdfViewerContext(
            storage_name="cohort_pdfs",
            file_field="source_pdf",
        )
        html = render_pdf_viewer(detail, pdf_viewer)
        assert 'src="/api/storage/cohort_pdfs/proxy?key=u1/abc/file.pdf"' in html
        assert 'data-dz-widget="pdf-viewer"' in html
        assert 'data-dz-back-url="/app/document"' in html

    def test_empty_src_when_record_missing_file_value(self) -> None:
        from dazzle.page.runtime.pdf_viewer_renderer import render_pdf_viewer
        from dazzle.render.context import (
            DetailContext,
            FieldContext,
            PdfViewerContext,
        )

        detail = DetailContext(
            entity_name="Doc",
            title="No file",
            fields=[FieldContext(name="title", label="Title")],
            item={"id": "u1", "title": "No file"},
            back_url="/app/doc",
        )
        pdf_viewer = PdfViewerContext(storage_name="docs", file_field="missing_field")
        html = render_pdf_viewer(detail, pdf_viewer)
        assert 'src=""' in html
