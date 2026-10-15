"""ECDSA P-256 signing certificate chain (#1283)."""

from __future__ import annotations

import base64
import datetime
from collections.abc import Callable
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12

from dazzle.signing.cert import (
    CA_VALIDITY_DAYS,
    SIGNING_CERT_VALIDITY_DAYS,
    generate_cert_chain,
    generate_cert_chain_b64,
)

OID = x509.NameOID


def _load(pfx: bytes, password: str) -> Any:
    return pkcs12.load_key_and_certificates(pfx, password.encode())


@pytest.fixture(scope="module")
def acme() -> tuple[Any, Any, Any, str]:
    pfx, password = generate_cert_chain("Acme Ltd")
    key, cert, chain = _load(pfx, password)
    return key, cert, chain, password


def _attr(cert: x509.Certificate, oid: x509.ObjectIdentifier) -> str:
    return cert.subject.get_attributes_for_oid(oid)[0].value  # type: ignore[return-value]


def _days(cert: x509.Certificate) -> int:
    return round(
        (cert.not_valid_after_utc - cert.not_valid_before_utc) / datetime.timedelta(days=1)
    )


CHAIN_CASES = [
    # (extract from (key, signing cert, CA chain, password), expected)
    pytest.param(
        lambda k, c, ch, p: (k is not None, len(ch)), (True, 1), id="pkcs12-loads-with-one-ca"
    ),
    pytest.param(
        lambda k, c, ch, p: _attr(c, OID.ORGANIZATION_NAME), "Acme Ltd", id="signing-cert-org"
    ),
    pytest.param(
        lambda k, c, ch, p: _attr(c, OID.COMMON_NAME),
        "Acme Ltd Document Signing",
        id="signing-cert-cn",
    ),
    pytest.param(
        lambda k, c, ch, p: _attr(ch[0], OID.COMMON_NAME), "Acme Ltd Signing CA", id="ca-cn"
    ),
    pytest.param(lambda k, c, ch, p: _attr(c, OID.COUNTRY_NAME), "GB", id="country-defaults-to-GB"),
    pytest.param(
        lambda k, c, ch, p: c.issuer == ch[0].subject, True, id="signing-cert-issued-by-ca"
    ),
    pytest.param(
        lambda k, c, ch, p: (
            ch[0].extensions.get_extension_for_class(x509.BasicConstraints).value.ca
        ),
        True,
        id="ca-basic-constraints-ca-true",
    ),
    pytest.param(
        lambda k, c, ch, p: c.extensions.get_extension_for_class(x509.BasicConstraints).value.ca,
        False,
        id="signing-cert-basic-constraints-ca-false",
    ),
    pytest.param(
        lambda k, c, ch, p: _days(c), SIGNING_CERT_VALIDITY_DAYS, id="signing-cert-validity"
    ),
    pytest.param(lambda k, c, ch, p: _days(ch[0]), CA_VALIDITY_DAYS, id="ca-validity"),
    # token_urlsafe(32) yields ~43 chars
    pytest.param(lambda k, c, ch, p: len(p) >= 32, True, id="generated-password-is-strong"),
]


@pytest.mark.parametrize(("extract", "expected"), CHAIN_CASES)
def test_generated_chain(
    acme: tuple[Any, Any, Any, str], extract: Callable[..., Any], expected: Any
) -> None:
    assert extract(*acme) == expected


def test_country_is_overridable() -> None:
    _, cert, _ = _load(*generate_cert_chain("Acme Ltd", country="US"))
    assert _attr(cert, OID.COUNTRY_NAME) == "US"


def test_explicit_password_round_trips() -> None:
    pfx, password = generate_cert_chain("Acme Ltd", password=b"hunter2-secret")
    assert password == "hunter2-secret"
    assert _load(pfx, password)[0] is not None


def test_b64_wrapper_decodes_to_loadable_pkcs12() -> None:
    b64, password = generate_cert_chain_b64("Acme Ltd")
    key, cert, _ = _load(base64.b64decode(b64), password)
    assert _attr(cert, OID.ORGANIZATION_NAME) == "Acme Ltd"
    assert key is not None
