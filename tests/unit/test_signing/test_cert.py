"""Unit tests for dazzle.signing.cert — ECDSA P-256 cert chain (#1283)."""

from __future__ import annotations

import base64
import datetime

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12

from dazzle.signing.cert import (
    CA_VALIDITY_DAYS,
    SIGNING_CERT_VALIDITY_DAYS,
    generate_cert_chain,
    generate_cert_chain_b64,
)


def _load(pfx_bytes: bytes, password: str):
    return pkcs12.load_key_and_certificates(pfx_bytes, password.encode())


def test_generate_returns_loadable_pkcs12():
    pfx_bytes, password = generate_cert_chain("Acme Ltd")
    key, cert, chain = _load(pfx_bytes, password)
    assert key is not None
    assert cert is not None
    assert len(chain) == 1


def test_cert_subject_uses_project_name():
    pfx_bytes, password = generate_cert_chain("Acme Ltd")
    _, cert, _ = _load(pfx_bytes, password)
    org = cert.subject.get_attributes_for_oid(x509.NameOID.ORGANIZATION_NAME)
    assert org[0].value == "Acme Ltd"
    cn = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    assert cn[0].value == "Acme Ltd Document Signing"


def test_ca_subject_uses_project_name():
    pfx_bytes, password = generate_cert_chain("Acme Ltd")
    _, _, chain = _load(pfx_bytes, password)
    ca = chain[0]
    cn = ca.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    assert cn[0].value == "Acme Ltd Signing CA"


def test_country_attribute_default_gb():
    pfx_bytes, password = generate_cert_chain("Acme Ltd")
    _, cert, _ = _load(pfx_bytes, password)
    country = cert.subject.get_attributes_for_oid(x509.NameOID.COUNTRY_NAME)
    assert country[0].value == "GB"


def test_country_attribute_overridable():
    pfx_bytes, password = generate_cert_chain("Acme Ltd", country="US")
    _, cert, _ = _load(pfx_bytes, password)
    country = cert.subject.get_attributes_for_oid(x509.NameOID.COUNTRY_NAME)
    assert country[0].value == "US"


def test_signing_cert_validity_window():
    pfx_bytes, password = generate_cert_chain("Acme Ltd")
    _, cert, _ = _load(pfx_bytes, password)
    span = cert.not_valid_after_utc - cert.not_valid_before_utc
    # Allow a 1-day fudge for leap-second / wall-clock drift around boundaries
    assert (
        datetime.timedelta(days=SIGNING_CERT_VALIDITY_DAYS - 1)
        <= span
        <= datetime.timedelta(days=SIGNING_CERT_VALIDITY_DAYS + 1)
    )


def test_ca_validity_window():
    pfx_bytes, password = generate_cert_chain("Acme Ltd")
    _, _, chain = _load(pfx_bytes, password)
    span = chain[0].not_valid_after_utc - chain[0].not_valid_before_utc
    assert (
        datetime.timedelta(days=CA_VALIDITY_DAYS - 1)
        <= span
        <= datetime.timedelta(days=CA_VALIDITY_DAYS + 1)
    )


def test_signing_cert_issued_by_ca():
    pfx_bytes, password = generate_cert_chain("Acme Ltd")
    _, cert, chain = _load(pfx_bytes, password)
    assert cert.issuer == chain[0].subject


def test_explicit_password_round_trips():
    pfx_bytes, password = generate_cert_chain("Acme Ltd", password=b"hunter2-secret")
    assert password == "hunter2-secret"
    key, _, _ = _load(pfx_bytes, password)
    assert key is not None


def test_generated_password_is_strong():
    _, password = generate_cert_chain("Acme Ltd")
    assert len(password) >= 32  # token_urlsafe(32) yields ~43 chars


def test_b64_wrapper_decodes_to_same_pkcs12():
    b64, password = generate_cert_chain_b64("Acme Ltd")
    pfx_bytes = base64.b64decode(b64)
    key, cert, chain = _load(pfx_bytes, password)
    assert key is not None
    assert cert is not None


def test_ca_has_basic_constraints_ca_true():
    pfx_bytes, password = generate_cert_chain("Acme Ltd")
    _, _, chain = _load(pfx_bytes, password)
    bc = chain[0].extensions.get_extension_for_class(x509.BasicConstraints)
    assert bc.value.ca is True


def test_signing_cert_has_basic_constraints_ca_false():
    pfx_bytes, password = generate_cert_chain("Acme Ltd")
    _, cert, _ = _load(pfx_bytes, password)
    bc = cert.extensions.get_extension_for_class(x509.BasicConstraints)
    assert bc.value.ca is False
