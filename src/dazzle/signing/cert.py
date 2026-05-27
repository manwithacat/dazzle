"""ECDSA P-256 cert chain generator for native document signing (#1283).

Produces a project-level CA (10-year validity) + signing cert (1-year
validity), both ECDSA P-256, packaged as a PKCS#12 bundle protected by
a random URL-safe password. The bundle is intended to be base64-encoded
and stored in the ``SIGNING_CERT_PFX_B64`` env var; the password lives
in ``SIGNING_CERT_PASSWORD``.

This implementation lifts the cert builder from cyfuture's
``scripts/generate_signing_cert.py`` and parameterises project identity
so any Dazzle downstream can mint its own CA via ``dazzle signing init``.

Per the locked design (issue #1283):
    * One CA per Dazzle project. The cert subject reflects project
      identity. Tenant identity (e.g. the school in AegisMark) lives
      in the signed document body, not in the PKCS#7 envelope.
    * No per-tenant CAs at phase 1.
    * No HSM-backed CSP at phase 1, but the env-var shape is forward-
      compatible: a future ``SIGNING_CERT_SOURCE`` selector can swap
      the PKCS#12 source without breaking the entity contract.
"""

from __future__ import annotations

import base64
import datetime
import secrets

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    pkcs12,
)
from cryptography.x509.oid import NameOID

CA_VALIDITY_DAYS = 3650
SIGNING_CERT_VALIDITY_DAYS = 365


def generate_cert_chain(
    project_name: str,
    *,
    country: str = "GB",
    password: bytes | None = None,
) -> tuple[bytes, str]:
    """Generate a CA + signing certificate chain as PKCS#12.

    Args:
        project_name: Organisation name on the cert (e.g. "AegisMark Ltd").
            Used as the X.509 Organization Name attribute on both certs.
        country: Two-letter ISO 3166-1 alpha-2 country code. Default "GB".
        password: PKCS#12 encryption password. If ``None`` a random
            URL-safe 32-byte token is generated and returned.

    Returns:
        Tuple of ``(pkcs12_bytes, password_str)``. The PKCS#12 bundle
        contains: signing cert + private key + CA cert (chain).
    """
    if password is None:
        password_str = secrets.token_urlsafe(32)
        password = password_str.encode()
    else:
        password_str = password.decode()

    now = datetime.datetime.now(datetime.UTC)

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, f"{project_name} Signing CA"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, project_name),
            x509.NameAttribute(NameOID.COUNTRY_NAME, country),
        ]
    )
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=CA_VALIDITY_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    sign_key = ec.generate_private_key(ec.SECP256R1())
    sign_name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, f"{project_name} Document Signing"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, project_name),
            x509.NameAttribute(NameOID.COUNTRY_NAME, country),
        ]
    )
    sign_cert = (
        x509.CertificateBuilder()
        .subject_name(sign_name)
        .issuer_name(ca_cert.subject)
        .public_key(sign_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=SIGNING_CERT_VALIDITY_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    pfx_bytes = pkcs12.serialize_key_and_certificates(
        f"{project_name} Signing".encode(),
        sign_key,
        sign_cert,
        [ca_cert],
        BestAvailableEncryption(password),
    )

    return pfx_bytes, password_str


def generate_cert_chain_b64(
    project_name: str,
    *,
    country: str = "GB",
    password: bytes | None = None,
) -> tuple[str, str]:
    """Convenience wrapper: returns ``(base64_pkcs12, password_str)``.

    The base64 string is suitable for ``heroku config:set
    SIGNING_CERT_PFX_B64=…`` without further encoding.
    """
    pfx_bytes, password_str = generate_cert_chain(project_name, country=country, password=password)
    return base64.b64encode(pfx_bytes).decode(), password_str
