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
import logging
import os

_logger = logging.getLogger(__name__)

_ENV_KEY = "DAZZLE_CONNECTION_SECRET"
# Optional previous key, set only during an encryption-key rotation. Decryption tries
# the primary key first, then this; encryption ALWAYS uses the primary. This gives a
# zero-downtime rotation window: set the new key as primary + the old key here, restart,
# then `dazzle auth rotate-encryption-key` re-wraps everything onto the new key — and a
# mid-rotation crash is safe because both keys still decrypt until this one is removed.
_ENV_KEY_OLD = "DAZZLE_CONNECTION_SECRET_OLD"


class ConnectionSecretError(RuntimeError):
    """Encryption/decryption of a connection secret failed — key missing/invalid,
    or ciphertext tampered."""


def _load_key() -> bytes:
    raw = os.environ.get(_ENV_KEY, "").strip()
    if not raw:
        raise ConnectionSecretError(
            f"{_ENV_KEY} is not set — required to encrypt enterprise-connection "
            "secrets at rest. Generate a 32-byte key and set it in the deployment "
            "environment (Heroku config var / AWS Secrets Manager / Azure Key "
            'Vault):  python -c "import os,base64;print(base64.b64encode('
            'os.urandom(32)).decode())"'
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001 — any decode failure is a config error
        raise ConnectionSecretError(f"{_ENV_KEY} is not valid base64") from exc
    if len(key) != 32:
        raise ConnectionSecretError(f"{_ENV_KEY} must decode to 32 bytes (AES-256), got {len(key)}")
    return key


def _decode_key(raw: str, env_name: str) -> bytes:
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001 — any decode failure is a config error
        raise ConnectionSecretError(f"{env_name} is not valid base64") from exc
    if len(key) != 32:
        raise ConnectionSecretError(f"{env_name} must decode to 32 bytes (AES-256), got {len(key)}")
    return key


def _load_keys() -> list[bytes]:
    """Decryption keys, primary first: ``DAZZLE_CONNECTION_SECRET`` then the optional
    ``DAZZLE_CONNECTION_SECRET_OLD`` (present only during a key rotation)."""
    keys = [_load_key()]  # primary — required (raises if absent)
    old = os.environ.get(_ENV_KEY_OLD, "").strip()
    if old:
        try:
            keys.append(_decode_key(old, _ENV_KEY_OLD))
        except ConnectionSecretError as exc:
            # Resilience: a malformed rotation key must NOT break decryption of valid
            # primary-key ciphertexts. Skip it (live traffic stays up); the operator
            # still sees the rotation is incomplete — secrets the bad key would have
            # decrypted land in the rewrap's `failed` list, which exits the CLI non-zero.
            _logger.warning("ignoring malformed %s during rotation: %s", _ENV_KEY_OLD, exc)
    return keys


def encrypt_secret(plaintext: str) -> str:
    """Encrypt ``plaintext`` → base64(nonce ‖ ciphertext+tag). Raises on key error."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _load_key()
    nonce = os.urandom(12)  # 96-bit GCM nonce
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret_with_key_index(token: str) -> tuple[str, int]:
    """Decrypt a token, returning ``(plaintext, key_index)`` where ``key_index`` is the
    position of the key that verified (0 = primary). The rewrap command uses the index to
    skip ciphertexts already on the primary key (idempotency).

    Tries each configured key (primary first); raises ``ConnectionSecretError`` if NONE
    decrypt it (wrong/rotated key, or tampered ciphertext) — fail-closed, no plaintext leak.
    """
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    keys = _load_keys()
    try:
        blob = base64.b64decode(token, validate=True)
    except Exception as exc:  # noqa: BLE001 — bad base64 is a format error, not a key issue
        raise ConnectionSecretError("connection secret is not valid base64") from exc
    nonce, ct = blob[:12], blob[12:]
    for index, key in enumerate(keys):
        try:
            return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8"), index
        except InvalidTag:
            continue  # wrong key — try the next configured key
        except Exception as exc:  # noqa: BLE001 — a non-tag failure is unrecoverable
            raise ConnectionSecretError("connection secret could not be decrypted") from exc
    raise ConnectionSecretError(
        "connection secret authentication failed — no configured key decrypts it "
        f"(tampered, or wrong/rotated key? set {_ENV_KEY_OLD} to the previous key)"
    )


def decrypt_secret(token: str) -> str:
    """Decrypt a token from :func:`encrypt_secret` (tries primary then rotation key)."""
    return decrypt_secret_with_key_index(token)[0]
