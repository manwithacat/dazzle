"""SP keypair generation for SAML SP-signed AuthnRequests / encrypted assertions (#1342).

A per-connection RSA-2048 keypair + self-signed X.509 cert. The IdP imports the cert (SP
certs are conventionally self-signed — no CA chain). Pure + onelogin-free (uses
``cryptography``, the [sso] dep already used for secret-at-rest), so it's locally testable
without libxmlsec1. The private key PEM is unencrypted in memory; the caller encrypts it at
rest (connection secrets, AES-256-GCM).
"""

from __future__ import annotations

import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_VALIDITY_DAYS = 3650  # ~10 years; re-issue via disable→enable


def generate_sp_keypair(common_name: str) -> tuple[str, str]:
    """Return ``(private_key_pem, cert_pem)``: an RSA-2048 key + a self-signed cert whose
    subject/issuer CN is ``common_name`` (the SP entityId)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=_VALIDITY_DAYS))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    return key_pem, cert_pem
