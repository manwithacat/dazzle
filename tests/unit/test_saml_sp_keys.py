"""SP keypair generation for SAML request signing (#1342)."""

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509.oid import NameOID

from dazzle.back.runtime.auth.saml_sp_keys import generate_sp_keypair


def test_generate_sp_keypair_shapes() -> None:
    key_pem, cert_pem = generate_sp_keypair("https://app.test/auth/saml/acs")
    key = load_pem_private_key(key_pem.encode(), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    assert key.key_size == 2048
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    assert cert.issuer == cert.subject  # self-signed
    cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    assert cn == "https://app.test/auth/saml/acs"


def test_generate_sp_keypair_unique() -> None:
    k1, _ = generate_sp_keypair("x")
    k2, _ = generate_sp_keypair("x")
    assert k1 != k2  # fresh key each call
