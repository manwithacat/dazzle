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
        # Without ANY file field, pdf_viewer hook stays unset and
        # detail_renderer handles the surface via the typed dispatch.
        assert ctx.template == ""
        assert ctx.pdf_viewer is None

    def _compile_plain_file_surface(self, extra_field_lines: list[str] | None = None) -> Any:
        """A view surface over an entity whose file field has NO
        ``storage=`` binding — the plain-FileService shape
        (project_tracker Attachment)."""
        from dazzle.page.converters.template_compiler import compile_surface_to_context

        src_lines = [
            "module test",
            'app test "Test"',
            "",
            'entity Attachment "Attachment":',
            "  id: uuid pk",
            "  filename: str(255) required",
            "  file: file required",
        ]
        src_lines.extend(extra_field_lines or [])
        src_lines.extend(
            [
                "",
                'surface attachment_view "View":',
                "  uses entity Attachment",
                "  mode: view",
                "  display: pdf_viewer",
                "  section main:",
                '    field filename "Filename"',
            ]
        )
        frag = _parse("\n".join(src_lines) + "\n")
        surface = frag.surfaces[0]
        entity = next(e for e in frag.entities if e.name == "Attachment")
        return compile_surface_to_context(surface, entity, app_prefix="/app")

    def test_plain_file_field_populates_document_route_mode(self) -> None:
        """A plain ``file`` field (no storage=) activates the viewer in
        document-route mode: storage_name is None and the renderer
        derives the scope-gated ``/_dazzle/documents`` src (#162)."""
        ctx = self._compile_plain_file_surface()
        assert ctx.pdf_viewer is not None
        assert ctx.pdf_viewer.storage_name is None
        assert ctx.pdf_viewer.file_field == "file"

    def test_storage_bound_field_wins_over_plain(self) -> None:
        """When the entity carries both shapes, the storage-bound field
        keeps its pre-existing precedence — plain-file mode only
        activates when no storage binding exists."""
        ctx = self._compile_plain_file_surface(
            extra_field_lines=["  signed_copy: file storage=contracts"]
        )
        assert ctx.pdf_viewer is not None
        assert ctx.pdf_viewer.storage_name == "contracts"
        assert ctx.pdf_viewer.file_field == "signed_copy"

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

    def test_document_route_src_for_plain_file_field(self) -> None:
        """storage_name=None → the src is the scope-gated document
        range proxy (#162 P1): /_dazzle/documents/{entity}/{id}/{field}/file.
        The route resolves + gates the file server-side, so the src
        carries the record triple, not the stored file URL."""
        from dazzle.page.runtime.pdf_viewer_renderer import render_pdf_viewer
        from dazzle.render.context import (
            DetailContext,
            FieldContext,
            PdfViewerContext,
        )

        detail = DetailContext(
            entity_name="Attachment",
            title="Q3 report",
            fields=[FieldContext(name="filename", label="Filename")],
            item={"id": "u1", "filename": "q3.pdf", "file": "/files/abc/q3.pdf"},
            back_url="/app/attachment",
        )
        pdf_viewer = PdfViewerContext(storage_name=None, file_field="file")
        html = render_pdf_viewer(detail, pdf_viewer)
        assert 'src="/_dazzle/documents/Attachment/u1/file/file"' in html
        assert 'data-dz-widget="pdf-viewer"' in html

    def test_document_route_empty_src_without_file_value(self) -> None:
        """Null-safety parity with storage mode: a record whose file
        field is empty renders the chrome with an empty src."""
        from dazzle.page.runtime.pdf_viewer_renderer import render_pdf_viewer
        from dazzle.render.context import (
            DetailContext,
            FieldContext,
            PdfViewerContext,
        )

        detail = DetailContext(
            entity_name="Attachment",
            title="No file",
            fields=[FieldContext(name="filename", label="Filename")],
            item={"id": "u1", "filename": "empty"},
            back_url="/app/attachment",
        )
        pdf_viewer = PdfViewerContext(storage_name=None, file_field="file")
        html = render_pdf_viewer(detail, pdf_viewer)
        assert 'src=""' in html


# ---------------------------------------------------------------------------
# Runtime dispatch gate (#162 adoption): pdf_viewer surfaces must NOT
# dispatch to the substrate detail — the viewer renders via the
# render_page pdf branch, which only runs when dispatch returns None.
# Without this carve-out the ADR-0049 VIEW flip silently swallowed
# display: pdf_viewer at runtime (registered-but-never-mounted).
# ---------------------------------------------------------------------------


class TestDispatchGate:
    def test_pdf_viewer_surface_skips_substrate_dispatch(self) -> None:
        from types import SimpleNamespace

        from dazzle.http.runtime.page_routes import _maybe_dispatch_inner_html

        src = """module test
app test "Test"

entity Attachment "Attachment":
  id: uuid pk
  filename: str(255) required
  file: file required

surface attachment_view "View":
  uses entity Attachment
  mode: view
  display: pdf_viewer
  section main:
    field filename "Filename"
"""
        frag = _parse(src)
        surface = frag.surfaces[0]
        entity = next(e for e in frag.entities if e.name == "Attachment")

        from dazzle.page.converters.template_compiler import compile_surface_to_context

        render_ctx = compile_surface_to_context(surface, entity, app_prefix="/app")
        assert render_ctx.pdf_viewer is not None  # rig sanity

        # Real registry with the framework 'fragment' handler — the rig
        # must dispatch exactly like a booted app, else the substrate
        # path is never reachable and the assertion is vacuous.
        from dazzle.http.runtime.renderers.init import register_default_renderers
        from dazzle.http.runtime.services import RuntimeServices

        services = RuntimeServices()
        register_default_renderers(services)
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(services=services)),
            query_params={},
        )
        appspec = SimpleNamespace(get_surface=lambda n: surface if n == surface.name else None)
        prc = SimpleNamespace(
            surface_name=surface.name,
            deps=SimpleNamespace(appspec=appspec),
            request=request,
            auth_ctx=None,
        )

        assert _maybe_dispatch_inner_html(prc, render_ctx) is None
