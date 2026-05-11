"""Public API for the generic document creation toolkit (Phase 3).

Defines the `DocumentTemplate` protocol, the `DocumentContext`
sentinel base, the HTML + PDF rendering entry points, and the
`PdfOptions` knob set.

The PDF renderer imports WeasyPrint lazily — `render_document_html`
works without the optional dep installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from dazzle.render.fragment import Page
from dazzle.render.fragment.renderer import FragmentRenderer


class DocumentContext:
    """Base class for document-context dataclasses.

    Not strictly required — `DocumentTemplate` accepts any object —
    but inheriting from this base signals intent and pairs with the
    `dataclass`-aware patterns in downstream apps. Authors typically
    write:

        @dataclass
        class InvoiceContext(DocumentContext):
            customer_name: str
            line_items: tuple[tuple[str, int, int], ...]
            total_cents: int

    The base is deliberately empty — it exists for type-checking
    and discoverability, not behavior.
    """


@runtime_checkable
class DocumentTemplate(Protocol):
    """A callable that builds a typed-Fragment `Page` from a context.

    Any function with this signature qualifies. No subclass needed.
    Authors typically write:

        def render_invoice(ctx: InvoiceContext) -> Page:
            return Page(
                title=f"Invoice {ctx.invoice_number}",
                body=Stack(children=...),
                ...
            )

    The framework's HTML + PDF renderers consume this callable
    interface, so swapping a template implementation is a one-line
    change at the call site.
    """

    def __call__(self, ctx: Any, /) -> Page: ...


@dataclass(frozen=True, slots=True)
class PdfOptions:
    """Knobs for the WeasyPrint pipeline.

    Fields:
        page_size: CSS page-size value (e.g. ``"A4"``, ``"Letter"``,
            ``"11in 17in"``). Defaults to ``"A4"`` — the global
            non-US default.
        margin: CSS margin shorthand for the @page rule
            (e.g. ``"20mm"`` or ``"20mm 15mm"``). Defaults to
            ``"20mm"``.
        base_url: Base URL used to resolve relative ``href`` / ``src``
            attributes in the rendered HTML (e.g. ``file:///...`` for
            local assets). Optional; defaults to no base — relative
            URLs in the template will fail to resolve.
        presentational_hints: Whether WeasyPrint should honour
            HTML presentational hints (``align="center"``, etc.).
            Off by default — typed-Fragment output uses class-based
            styling, not HTML hints.
    """

    page_size: str = "A4"
    margin: str = "20mm"
    base_url: str | None = None
    presentational_hints: bool = False


def render_document_html(
    template: DocumentTemplate,
    ctx: Any,
    /,
) -> str:
    """Render the document to a complete HTML string.

    Always available — no optional deps required. The output is
    exactly what `FragmentRenderer().render(page)` produces: full
    `<!DOCTYPE html>` document with the `Page`'s title, css_links,
    js_scripts, and body.

    For embedding the document body inside another page (e.g. a
    settings preview pane), the caller should construct the inner
    fragment directly rather than going through this function.
    """
    page = template(ctx)
    if not isinstance(page, Page):
        raise TypeError(f"DocumentTemplate must return a Page, got {type(page).__name__}")
    return FragmentRenderer().render(page)


def _build_pdf_stylesheet(options: PdfOptions) -> Any:
    """Construct the @page CSS rule for WeasyPrint.

    Built lazily so this module imports without WeasyPrint
    installed. Caller is responsible for catching ImportError.
    """
    import weasyprint

    return weasyprint.CSS(
        string=(f"@page {{ size: {options.page_size}; margin: {options.margin}; }}")
    )


def render_document_pdf(
    template: DocumentTemplate,
    ctx: Any,
    /,
    options: PdfOptions | None = None,
) -> bytes:
    """Render the document to PDF bytes via WeasyPrint.

    Requires the optional `weasyprint` dep — raises ImportError
    with an install hint when missing. The renderer assembles the
    full HTML via `render_document_html`, then runs WeasyPrint
    over it with the `@page` CSS configured by ``options``.

    Output is the raw PDF byte stream. Callers wrap it in a
    `Response(media_type="application/pdf")` (or write to disk)
    as needed.
    """
    try:
        import weasyprint  # noqa: F401  (presence check)
    except ImportError as exc:
        raise ImportError(
            "render_document_pdf requires WeasyPrint. Install with: "
            "pip install 'dazzle-dsl[compliance]' (the same extras "
            "group already used by the compliance pipeline)."
        ) from exc

    opts = options or PdfOptions()
    html = render_document_html(template, ctx)

    import weasyprint  # safe — checked above

    page_css = _build_pdf_stylesheet(opts)
    html_doc = weasyprint.HTML(
        string=html,
        base_url=opts.base_url,
    )
    result = html_doc.write_pdf(
        stylesheets=[page_css],
        presentational_hints=opts.presentational_hints,
    )
    # WeasyPrint returns `bytes | None`; `write_pdf` only returns None
    # when given a target= argument, which we don't pass.
    assert result is not None, "WeasyPrint.write_pdf returned None unexpectedly"
    assert isinstance(result, bytes)
    return result
