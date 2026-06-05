"""AES-GCM secret-at-rest encryption for connections (auth Plan 4a)."""

import base64
import os

import pytest

from dazzle.back.runtime.auth.connection_crypto import (
    ConnectionSecretError,
    decrypt_secret,
    encrypt_secret,
)

_KEY = base64.b64encode(b"0" * 32).decode()  # 32-byte key, base64


def test_round_trip(monkeypatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY)
    token = encrypt_secret("client-secret-xyz")
    assert token != "client-secret-xyz"  # not plaintext
    assert decrypt_secret(token) == "client-secret-xyz"


def test_distinct_ciphertexts_random_nonce(monkeypatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY)
    assert encrypt_secret("x") != encrypt_secret("x")  # random 96-bit nonce


def test_tamper_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY)
    token = encrypt_secret("secret")
    raw = bytearray(base64.b64decode(token))
    raw[-1] ^= 0x01  # flip a ciphertext/tag bit
    tampered = base64.b64encode(bytes(raw)).decode()
    with pytest.raises(ConnectionSecretError):
        decrypt_secret(tampered)


def test_missing_key_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET", raising=False)
    with pytest.raises(ConnectionSecretError, match="DAZZLE_CONNECTION_SECRET"):
        encrypt_secret("secret")


def test_wrong_length_key_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"short").decode())
    with pytest.raises(ConnectionSecretError, match="32 bytes"):
        encrypt_secret("secret")


def test_decrypt_with_different_key_fails(monkeypatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY)
    token = encrypt_secret("secret")
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(os.urandom(32)).decode())
    with pytest.raises(ConnectionSecretError):
        decrypt_secret(token)
