"""Unit tests for dazzle.signing.service (#1283).

Full PDF + PKCS#7 flow needs fpdf2 + pyhanko (the `[signing]` extra),
so most assertions are guarded by ``pytest.importorskip``. The
``deps-missing`` paths are tested unconditionally — those are the
friendly-error guardrails the framework promises when a project
declares ``signable: true`` without installing the extra.
"""

from __future__ import annotations

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

# -- Pure-Python helpers (no deps) ------------------------------------


def test_sanitize_html_strips_em_dash():
    assert "—" not in _sanitize_html_for_pdf("hello—world")
    assert " - " in _sanitize_html_for_pdf("hello—world")


def test_sanitize_html_handles_entities():
    out = _sanitize_html_for_pdf("&mdash;&hellip;&bull;")
    assert "&mdash;" not in out
    assert "..." in out
    assert "*" in out


def test_sanitize_html_idempotent_on_clean_input():
    clean = "<p>Plain ASCII only.</p>"
    assert _sanitize_html_for_pdf(clean) == clean


def test_pdf_branding_defaults_minimal():
    b = PdfBranding(organisation="Acme Ltd")
    assert b.organisation == "Acme Ltd"
    assert b.organisation_tagline == ""
    assert b.footer_text == ""
    assert b.location == "United Kingdom"


# -- Deps-missing guard paths -----------------------------------------


def test_generate_pdf_raises_friendly_error_when_fpdf2_missing():
    """When fpdf2 is not installed, generate_pdf must raise SigningError
    with an explicit install hint, not an ImportError leaking the
    module name."""
    with patch.dict("sys.modules", {"fpdf": None}):
        with pytest.raises(SigningError, match=r"\[signing\]"):
            generate_pdf("body", "Alice", PdfBranding(organisation="Acme"))


def test_sign_pdf_raises_friendly_error_when_pyhanko_missing(monkeypatch):
    monkeypatch.setenv("SIGNING_CERT_PFX_B64", "irrelevant")
    _get_signer.cache_clear()
    with patch.dict(
        "sys.modules",
        {"pyhanko": None, "pyhanko.sign": None, "pyhanko.sign.signers": None},
    ):
        with pytest.raises(SigningError, match=r"\[signing\]"):
            sign_pdf(b"%PDF-1.4", "Alice", "a@example.com", PdfBranding("Acme"))


def test_sign_pdf_raises_when_cert_env_missing(monkeypatch):
    monkeypatch.delenv("SIGNING_CERT_PFX_B64", raising=False)
    _get_signer.cache_clear()
    pyhanko = pytest.importorskip("pyhanko")
    del pyhanko
    with pytest.raises(SigningError, match="SIGNING_CERT_PFX_B64"):
        sign_pdf(b"%PDF-1.4", "Alice", "a@example.com", PdfBranding("Acme"))


# -- Full path (requires [signing] extra) -----------------------------


def test_generate_pdf_produces_pdf_bytes():
    pytest.importorskip("fpdf")
    out = generate_pdf(
        "<h1>Hello</h1><p>This is a test letter.</p>",
        "Alice Signer",
        PdfBranding(organisation="Acme Ltd", footer_text="Acme Ltd"),
    )
    assert out.startswith(b"%PDF-")
    assert len(out) > 100


def test_letter_date_strings_follow_display_locale():
    """#1597 D: letter header/signature dates use tenant TZ profile."""
    from datetime import UTC, datetime

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
        assert header == "16 July 2026"
        assert signed == "16 July 2026 at 01:30"
    finally:
        reset_display_locale(token)


def test_generate_pdf_grows_with_signature_image():
    pytest.importorskip("fpdf")
    import io as _io

    from PIL import Image

    img = Image.new("RGB", (200, 60), color="white")
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    sig_png = buf.getvalue()

    base = generate_pdf("<p>Body</p>", "Alice", PdfBranding(organisation="Acme"))
    with_sig = generate_pdf(
        "<p>Body</p>",
        "Alice",
        PdfBranding(organisation="Acme"),
        signature_png_bytes=sig_png,
    )
    assert len(with_sig) > len(base)


def test_sign_pdf_round_trip(monkeypatch, tmp_path):
    pytest.importorskip("fpdf")
    pytest.importorskip("pyhanko")
    from dazzle.signing.cert import generate_cert_chain_b64

    b64, password = generate_cert_chain_b64("Acme Ltd")
    monkeypatch.setenv("SIGNING_CERT_PFX_B64", b64)
    monkeypatch.setenv("SIGNING_CERT_PASSWORD", password)
    _get_signer.cache_clear()

    branding = PdfBranding(organisation="Acme Ltd")
    pdf = generate_pdf("<p>Body</p>", "Alice", branding)
    signed = sign_pdf(pdf, "Alice", "alice@example.com", branding, use_tsa=False)
    assert signed.startswith(b"%PDF-")
    # Signed PDF must be larger (sig field + PKCS#7 envelope added).
    assert len(signed) > len(pdf)
