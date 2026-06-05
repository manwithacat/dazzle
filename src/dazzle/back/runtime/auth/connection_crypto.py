"""Secret-at-rest encryption for enterprise connections (auth Plan 4a).

Connection secrets (OIDC ``client_secret``, SCIM bearer) are encrypted with
AES-256-GCM (authenticated encryption) under a 32-byte key from the
``DAZZLE_CONNECTION_SECRET`` env var (base64). Fail-closed: an absent or
malformed key raises ``ConnectionSecretError`` — there is no plaintext fallback,
so a misconfigured deployment cannot silently store secrets in the clear.

``cryptography`` is an enterprise-connections (``[sso]`` extra) dependency and is
imported lazily, so core installs without it are unaffected until a connection
secret is actually encrypted/decrypted.
"""

from __future__ import annotations

import base64
import os

_ENV_KEY = "DAZZLE_CONNECTION_SECRET"


class ConnectionSecretError(RuntimeError):
    """Encryption/decryption of a connection secret failed — key missing/invalid,
    or ciphertext tampered."""


def _load_key() -> bytes:
    raw = os.environ.get(_ENV_KEY, "").strip()
    if not raw:
        raise ConnectionSecretError(
            f"{_ENV_KEY} is not set — required to encrypt connection secrets at rest"
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001 — any decode failure is a config error
        raise ConnectionSecretError(f"{_ENV_KEY} is not valid base64") from exc
    if len(key) != 32:
        raise ConnectionSecretError(f"{_ENV_KEY} must decode to 32 bytes (AES-256), got {len(key)}")
    return key


def encrypt_secret(plaintext: str) -> str:
    """Encrypt ``plaintext`` → base64(nonce ‖ ciphertext+tag). Raises on key error."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _load_key()
    nonce = os.urandom(12)  # 96-bit GCM nonce
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Decrypt a token from :func:`encrypt_secret`.

    Raises ``ConnectionSecretError`` on a wrong key or tampered ciphertext (the
    AES-GCM authentication tag fails).
    """
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _load_key()
    try:
        blob = base64.b64decode(token, validate=True)
        nonce, ct = blob[:12], blob[12:]
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    except InvalidTag as exc:
        raise ConnectionSecretError(
            "connection secret authentication failed (tampered or wrong key)"
        ) from exc
    except ConnectionSecretError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ConnectionSecretError("connection secret could not be decrypted") from exc
