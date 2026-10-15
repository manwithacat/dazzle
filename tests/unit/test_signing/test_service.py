"""PDF generation and PAdES signing service (#1283).

The full PDF + PKCS#7 flow needs fpdf2 + pyhanko (the ``[signing]`` extra)
and is guarded by ``importorskip``. The deps-missing rows run
unconditionally: they are the friendly-error guardrails promised to a
project that declares ``signable: true`` without installing the extra.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from dazzle.signing.service import (
    PdfBranding,
    _get_signer,
    _letter_date_strings,
    _sanitize_html_for_pdf,
    generate_pdf,
    sign_pdf,
)
from dazzle.signing.tokens import SigningError

ACME = PdfBranding(organisation="Acme Ltd")


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        pytest.param("hello—world", "hello - world", id="em-dash-to-ascii"),
        pytest.param("&mdash;&hellip;&bull;", " - ...*", id="named-entities-to-ascii"),
        pytest.param(
            "<p>Plain ASCII only.</p>", "<p>Plain ASCII only.</p>", id="clean-input-unchanged"
        ),
    ],
)
def test_sanitize_html_for_core_pdf_fonts(html: str, expected: str) -> None:
    assert _sanitize_html_for_pdf(html) == expected


def _without_fpdf(mp: pytest.MonkeyPatch) -> Callable[[], object]:
    def call() -> object:
        with patch.dict("sys.modules", {"fpdf": None}):
            return generate_pdf("body", "Alice", ACME)

    return call


def _without_pyhanko(mp: pytest.MonkeyPatch) -> Callable[[], object]:
    mp.setenv("SIGNING_CERT_PFX_B64", "irrelevant")
    _get_signer.cache_clear()

    def call() -> object:
        modules = {"pyhanko": None, "pyhanko.sign": None, "pyhanko.sign.signers": None}
        with patch.dict("sys.modules", modules):
            return sign_pdf(b"%PDF-1.4", "Alice", "a@example.com", ACME)

    return call


def _without_cert_env(mp: pytest.MonkeyPatch) -> Callable[[], object]:
    pytest.importorskip("pyhanko")
    mp.delenv("SIGNING_CERT_PFX_B64", raising=False)
    _get_signer.cache_clear()
    return lambda: sign_pdf(b"%PDF-1.4", "Alice", "a@example.com", ACME)


@pytest.mark.parametrize(
    ("arrange", "message"),
    [
        # An install hint, never an ImportError leaking the module name.
        pytest.param(_without_fpdf, r"\[signing\]", id="fpdf2-missing-names-the-extra"),
        pytest.param(_without_pyhanko, r"\[signing\]", id="pyhanko-missing-names-the-extra"),
        pytest.param(
            _without_cert_env, "SIGNING_CERT_PFX_B64", id="cert-env-missing-names-the-var"
        ),
    ],
)
def test_missing_prerequisite_raises_signing_error(
    arrange: Callable[[pytest.MonkeyPatch], Callable[[], object]],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call = arrange(monkeypatch)
    with pytest.raises(SigningError, match=message):
        call()


def test_letter_date_strings_follow_display_locale() -> None:
    """#1597 D: letter header/signature dates use the tenant TZ profile."""
    from dazzle.i18n.display_locale import (
        DisplayLocaleProfile,
        reset_display_locale,
        set_display_locale,
    )

    token = set_display_locale(
        DisplayLocaleProfile(timezone="Europe/London", date_format="D MMM YYYY")
    )
    try:
        header, signed = _letter_date_strings(datetime(2026, 7, 16, 0, 30, tzinfo=UTC))
    finally:
        reset_display_locale(token)
    assert (header, signed) == ("16 July 2026", "16 July 2026 at 01:30")


def test_generate_pdf_embeds_signature_image() -> None:
    pytest.importorskip("fpdf")
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (200, 60), color="white").save(buf, format="PNG")
    base = generate_pdf("<p>Body</p>", "Alice", ACME)
    with_sig = generate_pdf("<p>Body</p>", "Alice", ACME, signature_png_bytes=buf.getvalue())
    assert len(with_sig) > len(base)


def test_generate_then_sign_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fpdf")
    pytest.importorskip("pyhanko")
    from dazzle.signing.cert import generate_cert_chain_b64

    b64, password = generate_cert_chain_b64("Acme Ltd")
    monkeypatch.setenv("SIGNING_CERT_PFX_B64", b64)
    monkeypatch.setenv("SIGNING_CERT_PASSWORD", password)
    _get_signer.cache_clear()

    branding = PdfBranding(organisation="Acme Ltd", footer_text="Acme Ltd")
    pdf = generate_pdf("<h1>Hello</h1><p>This is a test letter.</p>", "Alice", branding)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 100
    signed = sign_pdf(pdf, "Alice", "alice@example.com", branding, use_tsa=False)
    assert signed.startswith(b"%PDF-")
    assert len(signed) > len(pdf)  # signature field + PKCS#7 envelope
