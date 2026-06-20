"""AES-GCM secret-at-rest encryption for connections (auth Plan 4a)."""

import base64
import os

import pytest

from dazzle.http.runtime.auth.connection_crypto import (
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


_KEY_A = base64.b64encode(b"a" * 32).decode()
_KEY_B = base64.b64encode(b"b" * 32).decode()


def test_decrypts_with_rotation_old_key(monkeypatch) -> None:
    # Encrypt under key A, then rotate: primary=B, old=A. Decryption still works via the
    # old key, and reports key_index 1 (not the primary).
    from dazzle.http.runtime.auth.connection_crypto import decrypt_secret_with_key_index

    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY_A)
    token = encrypt_secret("rotate-me")
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY_B)
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET_OLD", _KEY_A)
    plaintext, idx = decrypt_secret_with_key_index(token)
    assert plaintext == "rotate-me" and idx == 1  # decrypted by the rotation key


def test_primary_key_reports_index_0(monkeypatch) -> None:
    from dazzle.http.runtime.auth.connection_crypto import decrypt_secret_with_key_index

    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY_B)
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET_OLD", _KEY_A)
    token = encrypt_secret("fresh")  # encryption always uses the primary
    plaintext, idx = decrypt_secret_with_key_index(token)
    assert plaintext == "fresh" and idx == 0


def test_fails_when_no_configured_key_decrypts(monkeypatch) -> None:
    # Encrypt under A; rotate to primary=B with the WRONG old key → neither decrypts.
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY_A)
    token = encrypt_secret("orphan")
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY_B)
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET_OLD", base64.b64encode(b"c" * 32).decode())
    with pytest.raises(ConnectionSecretError, match="no configured key decrypts"):
        decrypt_secret(token)


def test_encrypt_always_uses_primary_not_old(monkeypatch) -> None:
    # With both keys set, a fresh ciphertext is on the primary — removing OLD still decrypts.
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY_B)
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET_OLD", _KEY_A)
    token = encrypt_secret("primary-only")
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET_OLD", raising=False)
    assert decrypt_secret(token) == "primary-only"


def test_malformed_old_key_is_skipped_not_fatal(monkeypatch) -> None:
    # A typo'd DAZZLE_CONNECTION_SECRET_OLD must not break decryption of a valid
    # primary-key ciphertext (resilience during rotation).
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY_B)
    token = encrypt_secret("primary-secret")  # on the primary key
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET_OLD", "not-valid-base64!!!")
    assert decrypt_secret(token) == "primary-secret"  # primary still decrypts


def test_primary_key_with_non_base64_chars_is_rejected(monkeypatch) -> None:
    # A primary key string carrying a non-alphabet char (here a newline) that would
    # decode to a valid 32-byte key under lax base64 must still be rejected — pins
    # `validate=True` on the primary-key decode (a mutation-audit survivor, #1342 #5).
    # Under validate=False the char is silently discarded and the bad config "works".
    bad_key = _KEY[:4] + "\n" + _KEY[4:]
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", bad_key)
    with pytest.raises(ConnectionSecretError, match="not valid base64"):
        encrypt_secret("x")


def test_token_with_non_base64_chars_is_rejected(monkeypatch) -> None:
    # Same for the ciphertext decode path: a token with a non-alphabet char must be
    # rejected as bad base64, not silently de-mangled and decrypted.
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY)
    token = encrypt_secret("x")
    bad_token = token[:4] + "\n" + token[4:]
    with pytest.raises(ConnectionSecretError, match="not valid base64"):
        decrypt_secret(bad_token)
