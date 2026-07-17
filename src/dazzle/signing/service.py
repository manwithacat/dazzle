"""PDF generation + PKCS#7 signing for native document signing (#1283).

Two-stage pipeline:

1. ``generate_pdf`` renders an HTML letter body to a PDF using ``fpdf2``
   (pure-Python, no system deps). The caller supplies organisation
   branding (header, country, footer) so the framework stays
   project-agnostic.

2. ``sign_pdf`` applies a PKCS#7 digital signature with an optional
   RFC 3161 timestamp, producing a PAdES B-T (Basic + Timestamp)
   document. The signing identity is loaded from the
   ``SIGNING_CERT_PFX_B64`` + ``SIGNING_CERT_PASSWORD`` env vars (a
   project-level CA + signing cert chain, minted by
   ``dazzle.signing.cert.generate_cert_chain``).

Both ``fpdf2`` and ``pyhanko`` live behind the ``[signing]`` extra and
are imported lazily so consumers that never touch a signable entity
stay free of the dep chain.

Lifted from cyfuture's working stack (``services/signing_service.py``).
Project-specific branding strings were inlined there; here they are
explicit parameters on the ``PdfBranding`` dataclass so any Dazzle
downstream can supply its own header/footer.
"""

from __future__ import annotations

import base64
import functools
import io
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from dazzle.i18n.display_locale import get_display_locale
from dazzle.signing.tokens import SigningError

if TYPE_CHECKING:
    from pyhanko.sign.signers import SimpleSigner

log = logging.getLogger(__name__)

DEFAULT_TSA_URL = "http://timestamp.digicert.com"


@dataclass(frozen=True)
class PdfBranding:
    """Project-level branding for the generated PDF.

    All fields are required so the rendered PDF carries a clear
    organisation identity. Use ``location`` to set the legal
    jurisdiction recorded on the PKCS#7 signature.
    """

    organisation: str
    organisation_tagline: str = ""
    footer_text: str = ""
    location: str = "United Kingdom"


def _sanitize_html_for_pdf(html: str) -> str:
    """Map HTML entities + Unicode chars to Helvetica-safe ASCII.

    fpdf2's built-in Helvetica is Latin-1 only. Em dashes, smart
    quotes, etc. must be down-converted or the PDF renders garbage.
    """
    html_entity_replacements = {
        "&mdash;": " - ",
        "&ndash;": "-",
        "&lsquo;": "'",
        "&rsquo;": "'",
        "&ldquo;": '"',
        "&rdquo;": '"',
        "&hellip;": "...",
        "&bull;": "*",
    }
    for entity, replacement in html_entity_replacements.items():
        html = html.replace(entity, replacement)

    unicode_replacements = {
        "—": " - ",
        "–": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        "•": "*",
        " ": " ",
    }
    for char, replacement in unicode_replacements.items():
        html = html.replace(char, replacement)

    return html


def _letter_date_strings(now: datetime | None = None) -> tuple[str, str]:
    """Header + signature dates from DisplayLocaleProfile (#1597 D).

    ``now`` is injectable for tests; production always uses UTC wall clock
    converted to the tenant display timezone.
    """
    profile = get_display_locale()
    clock = now if now is not None else datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    local = profile.to_display_datetime(clock)
    header = profile.format_long_date(local)
    signed = profile.format_letter_datetime(clock)
    return header, signed


def generate_pdf(
    letter_html: str,
    signer_name: str,
    branding: PdfBranding,
    signature_png_bytes: bytes | None = None,
) -> bytes:
    """Render an HTML letter to a signed-ready PDF.

    The output is an unsigned PDF; pass it to ``sign_pdf`` to apply the
    PKCS#7 digital signature.

    Letter dates use the request/tenant :class:`DisplayLocaleProfile`
    (#1597 D) — not a hard-coded UTC ``strftime``.
    """
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise SigningError(
            "fpdf2 is not installed. Install with `pip install dazzle-dsl[signing]`."
        ) from exc

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, branding.organisation, new_x="LMARGIN", new_y="NEXT")
    if branding.organisation_tagline:
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(
            0,
            5,
            branding.organisation_tagline,
            new_x="LMARGIN",
            new_y="NEXT",
        )
    pdf.ln(5)

    pdf.set_font("Helvetica", "", 10)
    header_date, signed_date = _letter_date_strings()
    pdf.cell(0, 6, f"Date: {header_date}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    pdf.set_font("Helvetica", "", 10)
    pdf.write_html(_sanitize_html_for_pdf(letter_html))

    pdf.ln(15)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Signed:", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    if signature_png_bytes:
        sig_stream = io.BytesIO(signature_png_bytes)
        pdf.image(sig_stream, x=pdf.get_x(), y=pdf.get_y(), w=60)
        pdf.ln(25)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Name: {signer_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        6,
        f"Date: {signed_date}",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    if branding.footer_text:
        pdf.ln(20)
        pdf.set_font("Helvetica", "", 7)
        pdf.cell(
            0,
            4,
            branding.footer_text,
            new_x="LMARGIN",
            new_y="NEXT",
            align="C",
        )

    return bytes(pdf.output())


@functools.cache
def _get_signer() -> SimpleSigner:
    """Load and cache the PKCS#12 signer from env.

    `functools.cache` memoises the loaded signer (one-time, thread-safe) with no
    module-level `global` (ADR-0005). A raised `SigningError` is not cached, so a
    later call retries once the env is configured. Tests that mutate the signing env
    call `_get_signer.cache_clear()` to force a re-load.
    """
    pfx_b64 = os.environ.get("SIGNING_CERT_PFX_B64", "")
    password = os.environ.get("SIGNING_CERT_PASSWORD", "")

    if not pfx_b64:
        raise SigningError("SIGNING_CERT_PFX_B64 not configured")

    try:
        from pyhanko.sign.signers import SimpleSigner
    except ImportError as exc:
        raise SigningError(
            "pyhanko is not installed. Install with `pip install dazzle-dsl[signing]`."
        ) from exc

    try:
        pfx_bytes = base64.b64decode(pfx_b64)
        signer: SimpleSigner = SimpleSigner.load_pkcs12_data(
            pkcs12_bytes=pfx_bytes,
            other_certs=(),
            passphrase=password.encode() if password else None,
        )
    except Exception as exc:
        raise SigningError(f"Failed to load signing certificate: {exc}") from exc

    return signer


def _build_signing_inputs(
    *,
    pdf_bytes: bytes,
    signer_name: str,
    signer_email: str,
    branding: PdfBranding,
    use_tsa: bool,
    tsa_url: str,
) -> tuple[Any, Any, Any, Any]:
    """Lift the shared pyhanko object graph used by both sign paths."""
    try:
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import fields as sig_fields
        from pyhanko.sign import signers
    except ImportError as exc:
        raise SigningError(
            "pyhanko is not installed. Install with `pip install dazzle-dsl[signing]`."
        ) from exc

    signer = _get_signer()

    timestamper: Any = None
    if use_tsa:
        try:
            from pyhanko.sign import timestamps

            HTTPTimeStamper: Any = timestamps.HTTPTimeStamper
            timestamper = HTTPTimeStamper(tsa_url)
        except Exception:
            log.warning("TSA unavailable, signing without timestamp")

    writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))
    sig_fields.append_signature_field(
        writer, sig_fields.SigFieldSpec("Signature", box=(30, 50, 250, 120))
    )

    meta = signers.PdfSignatureMetadata(
        field_name="Signature",
        md_algorithm="sha256",
        reason=f"Signed by {signer_name} ({signer_email})",
        location=branding.location,
    )

    return writer, meta, signer, timestamper


def sign_pdf(
    pdf_bytes: bytes,
    signer_name: str,
    signer_email: str,
    branding: PdfBranding,
    use_tsa: bool = True,
    tsa_url: str = DEFAULT_TSA_URL,
) -> bytes:
    """Apply a PKCS#7 digital signature + optional RFC 3161 timestamp.

    Achieves PAdES B-T conformance when ``use_tsa=True`` and the TSA is
    reachable. Falls back to PAdES B-B (no timestamp) if the TSA is
    unreachable, logging a warning.

    Synchronous entry point — uses pyhanko's blocking
    ``signers.sign_pdf`` under the hood (which calls ``asyncio.run``
    internally). For use from async code (e.g. FastAPI route handlers),
    prefer :func:`async_sign_pdf` to avoid the nested-event-loop error.
    """
    writer, meta, signer, timestamper = _build_signing_inputs(
        pdf_bytes=pdf_bytes,
        signer_name=signer_name,
        signer_email=signer_email,
        branding=branding,
        use_tsa=use_tsa,
        tsa_url=tsa_url,
    )
    from pyhanko.sign import signers

    result = signers.sign_pdf(writer, meta, signer=signer, timestamper=timestamper)
    return bytes(result.read())


async def async_sign_pdf(
    pdf_bytes: bytes,
    signer_name: str,
    signer_email: str,
    branding: PdfBranding,
    use_tsa: bool = True,
    tsa_url: str = DEFAULT_TSA_URL,
) -> bytes:
    """Async variant of :func:`sign_pdf` — safe to call from async code.

    pyhanko's modern API is async-first; the sync ``sign_pdf`` wraps
    ``async_sign_pdf`` with ``asyncio.run``, which fails when called
    from inside a running event loop. Route handlers and other
    in-loop callers must use this variant.
    """
    writer, meta, signer, timestamper = _build_signing_inputs(
        pdf_bytes=pdf_bytes,
        signer_name=signer_name,
        signer_email=signer_email,
        branding=branding,
        use_tsa=use_tsa,
        tsa_url=tsa_url,
    )
    from pyhanko.sign import signers

    result = await signers.async_sign_pdf(writer, meta, signer=signer, timestamper=timestamper)
    return bytes(result.read())
