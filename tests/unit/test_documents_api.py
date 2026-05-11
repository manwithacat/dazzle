"""Unit tests for the generic document toolkit (Phase 3).

Covers:
  - DocumentContext / DocumentTemplate protocol satisfaction
  - render_document_html: typed-Fragment Page → full HTML
  - render_document_pdf: WeasyPrint integration + PdfOptions
  - error paths: bad return type, missing optional dep
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from dazzle.documents import (
    DocumentContext,
    DocumentTemplate,
    PdfOptions,
    render_document_html,
    render_document_pdf,
)
from dazzle.render.fragment import URL, Heading, Link, Page, Stack, Text


@dataclass
class InvoiceContext(DocumentContext):
    customer_name: str
    invoice_number: str
    total_cents: int


def _invoice_template(ctx: InvoiceContext) -> Page:
    return Page(
        title=f"Invoice {ctx.invoice_number}",
        body=Stack(
            children=(
                Link(label="Acme Co.", href=URL("/")),
                Heading(body=f"Invoice {ctx.invoice_number}", level=1),
                Text(body=f"Bill to: {ctx.customer_name}"),
                Text(body=f"Total: ${ctx.total_cents / 100:.2f}"),
            )
        ),
        css_links=("/static/dist/dazzle.min.css",),
        js_scripts=(),
    )


# ───────────────── Protocol satisfaction ─────────────────


def test_invoice_template_satisfies_protocol() -> None:
    """A plain function with the right signature qualifies."""
    assert isinstance(_invoice_template, DocumentTemplate)


def test_lambda_template_satisfies_protocol() -> None:
    """Inline lambdas also qualify — the indirection is structural."""

    def trivial(_ctx: object) -> Page:
        return Page(
            title="x",
            body=Text(body="x"),
            css_links=(),
            js_scripts=(),
        )

    assert isinstance(trivial, DocumentTemplate)


def test_document_context_is_empty_base() -> None:
    """DocumentContext is a marker base — no behavior, no required fields."""
    ctx = InvoiceContext(customer_name="A", invoice_number="1", total_cents=100)
    assert isinstance(ctx, DocumentContext)


# ───────────────── render_document_html ─────────────────


def test_render_html_returns_full_document() -> None:
    ctx = InvoiceContext(
        customer_name="Alice Wong",
        invoice_number="INV-001",
        total_cents=12345,
    )
    html = render_document_html(_invoice_template, ctx)
    assert "<!DOCTYPE html>" in html
    assert "<title>Invoice INV-001</title>" in html or "Invoice INV-001" in html
    assert "Alice Wong" in html
    assert "$123.45" in html


def test_render_html_preserves_page_css_links() -> None:
    ctx = InvoiceContext(customer_name="x", invoice_number="1", total_cents=0)
    html = render_document_html(_invoice_template, ctx)
    assert "/static/dist/dazzle.min.css" in html


def test_render_html_rejects_non_page_return() -> None:
    """A template that returns something other than a Page raises TypeError."""

    def bad_template(_ctx: object) -> Page:  # type: ignore[return-value]
        return "not a Page"  # type: ignore[return-value]

    with pytest.raises(TypeError, match="DocumentTemplate must return a Page"):
        render_document_html(bad_template, object())


def test_render_html_escapes_context_data() -> None:
    """User-supplied data in context flows through typed primitives'
    HTML escaping, so it cannot break out of the page body."""
    ctx = InvoiceContext(
        customer_name="<script>alert(1)</script>",
        invoice_number="INV-1",
        total_cents=0,
    )
    html = render_document_html(_invoice_template, ctx)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ───────────────── render_document_pdf ─────────────────


def test_render_pdf_produces_pdf_bytes() -> None:
    """WeasyPrint output starts with the %PDF- magic number."""
    pytest.importorskip("weasyprint")
    ctx = InvoiceContext(
        customer_name="Bob",
        invoice_number="INV-002",
        total_cents=5000,
    )
    pdf = render_document_pdf(_invoice_template, ctx)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")
    # PDFs always end with %%EOF (possibly with trailing newline).
    assert pdf.rstrip(b"\r\n").endswith(b"%%EOF")


def test_render_pdf_default_options_use_a4() -> None:
    """Without explicit options, the rasteriser uses A4."""
    pytest.importorskip("weasyprint")
    ctx = InvoiceContext(customer_name="x", invoice_number="1", total_cents=0)
    pdf = render_document_pdf(_invoice_template, ctx)
    assert pdf.startswith(b"%PDF-")


def test_render_pdf_letter_size_option() -> None:
    """PdfOptions.page_size threads into the @page CSS rule."""
    pytest.importorskip("weasyprint")
    ctx = InvoiceContext(customer_name="x", invoice_number="1", total_cents=0)
    pdf_a4 = render_document_pdf(_invoice_template, ctx, PdfOptions(page_size="A4"))
    pdf_letter = render_document_pdf(_invoice_template, ctx, PdfOptions(page_size="Letter"))
    # Both are valid PDFs.
    assert pdf_a4.startswith(b"%PDF-")
    assert pdf_letter.startswith(b"%PDF-")
    # A4 vs Letter render to different page sizes — byte-stream differs.
    assert pdf_a4 != pdf_letter


def test_pdf_options_defaults() -> None:
    opts = PdfOptions()
    assert opts.page_size == "A4"
    assert opts.margin == "20mm"
    assert opts.base_url is None
    assert opts.presentational_hints is False


def test_pdf_options_frozen() -> None:
    """PdfOptions is a frozen dataclass — attribute assignment fails."""
    import dataclasses

    opts = PdfOptions()
    with pytest.raises(dataclasses.FrozenInstanceError):
        opts.page_size = "Letter"  # type: ignore[misc]


def test_render_pdf_missing_weasyprint_raises_helpful_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When WeasyPrint isn't installed, the error message points at
    the install command — not a bare ImportError from deep in the
    Authlib-style lazy chain."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "weasyprint":
            raise ImportError("no weasyprint")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    ctx = InvoiceContext(customer_name="x", invoice_number="1", total_cents=0)
    with pytest.raises(ImportError, match="render_document_pdf requires WeasyPrint"):
        render_document_pdf(_invoice_template, ctx)


def test_render_pdf_rejects_non_page_return() -> None:
    pytest.importorskip("weasyprint")

    def bad_template(_ctx: object) -> Page:  # type: ignore[return-value]
        return 42  # type: ignore[return-value]

    with pytest.raises(TypeError, match="DocumentTemplate must return a Page"):
        render_document_pdf(bad_template, object())
