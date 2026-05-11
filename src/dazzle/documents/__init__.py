"""Generic document creation toolkit (Phase 3, v0.67.41).

Build documents — invoices, receipts, certificates, mail-merged
letters, contracts, statements, reports — from typed-Fragment
templates plus variable data. Output formats:

  - HTML: always available. Pure typed-Fragment rendering.
  - PDF:  requires the optional `weasyprint` dep (already pinned
          under the `compliance` extras group). The PDF renderer
          imports lazily so consumers that only need HTML output
          stay free of the WeasyPrint native-dep chain.

The public API is intentionally narrow:

  ``DocumentTemplate``
      A `Callable[[ctx], Page]`. Any function that builds a typed-
      Fragment `Page` from a context object qualifies. No subclass
      required — the indirection is structural.

  ``render_document_html(template, ctx) -> str``
  ``render_document_pdf(template, ctx) -> bytes``
      Render the document. The PDF variant runs the HTML through
      WeasyPrint with a sensible page-size default; pass a
      `PdfOptions(...)` to override.

Designed for AI-agent + human authoring: a downstream Dazzle app
defines its document templates as ordinary Python functions, gives
them clear signatures, and the framework handles the rest.
"""

from dazzle.documents.api import (
    DocumentContext,
    DocumentTemplate,
    PdfOptions,
    render_document_html,
    render_document_pdf,
)

__all__ = (
    "DocumentContext",
    "DocumentTemplate",
    "PdfOptions",
    "render_document_html",
    "render_document_pdf",
)
